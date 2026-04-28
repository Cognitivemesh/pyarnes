"""Single entry-point that wires configure_logging, Lifecycle, and AgentLoop.

Adopters currently must assemble these three components manually. ``AgentRuntime``
does that wiring so calling code is reduced to constructing the dataclass and
invoking ``run()``.

Concurrency note
----------------
``configure_logging`` modifies the global loguru sink set. Calling ``run()``
concurrently from two ``AgentRuntime`` instances in the same process will race
on those sinks (one call's ``logger.remove()`` silences the other mid-run).
For process-level concurrent agent execution, configure logging once outside
the runtime and pass ``log_json=False``/``log_level`` adjustments via the
``configure_logging`` call before constructing any runtime instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pyarnes_core.error_registry import ErrorHandlerRegistry
from pyarnes_core.lifecycle import Lifecycle, Phase
from pyarnes_core.observability import log_lifecycle_transition
from pyarnes_core.observe.logger import configure_logging
from pyarnes_core.telemetry import configure_tracing, session_span, tracing_endpoint_from_env
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_guardrails.guardrails import GuardrailChain
from pyarnes_harness.capture.tool_log import ToolCallLogger
from pyarnes_harness.compaction import CompactionConfig
from pyarnes_harness.compressor import ContextCompressor
from pyarnes_harness.context import AgentContext
from pyarnes_harness.hooks import HookChain
from pyarnes_harness.loop import AgentLoop, LoopConfig
from pyarnes_harness.steering import SteeringQueue
from pyarnes_harness.tools.registry import global_registry
from pyarnes_harness.transform import TransformChain

__all__ = ["AgentRuntime"]


@dataclass(slots=True)
class AgentRuntime:
    """Wires configure_logging, Lifecycle, and AgentLoop into a single entry-point.

    Attributes:
        tools: Mapping of tool names to their handlers.
        model: The backing LLM client.
        config: Loop tunables (defaults to ``LoopConfig()``).
        guardrail_chain: Optional chain of guardrails evaluated before each tool call.
        agent_context: Optional domain-specific guidance injected into the system message.
        tool_call_logger: Optional JSONL logger for persisting every tool invocation.
        error_registry: Optional registry of custom async error recovery handlers.
        session_id: Identifier for this agent session. Auto-generated (12 hex chars) when
            ``None``; written back to the attribute after generation so callers can read it.
        trace_id: Distributed-trace identifier. Auto-generated (32 hex chars from uuid4)
            when ``None``; written back after generation.
        log_level: Minimum log level name passed to ``configure_logging``.
        log_json: When ``True`` (default) emit JSONL; ``False`` for human-readable output.
        lifecycle: Holds the ``Lifecycle`` instance created during ``run()``.
            ``None`` before the first call.
    """

    tools: dict[str, ToolHandler]
    model: ModelClient
    config: LoopConfig = field(default_factory=LoopConfig)
    guardrail_chain: GuardrailChain | None = None
    agent_context: AgentContext | None = None
    tool_call_logger: ToolCallLogger | None = None
    error_registry: ErrorHandlerRegistry | None = None
    hook_chain: HookChain | None = None
    steering: SteeringQueue | None = None
    transform_chain: TransformChain | None = None
    session_id: str | None = None
    trace_id: str | None = None
    log_level: str = "INFO"
    log_json: bool = True
    use_global_registry: bool = False
    lifecycle: Lifecycle | None = field(default=None, init=False)

    async def run(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute the agent loop for the given message history.

        Steps:
        1. Auto-generate ``session_id`` and ``trace_id`` when not provided.
        2. Configure logging for the session.
        3. Create a ``Lifecycle`` and transition it to ``RUNNING``.
        4. Run the ``AgentLoop``.
        5. Transition lifecycle to ``COMPLETED`` on success, ``FAILED`` on any exception.

        Args:
            messages: Initial conversation messages.

        Returns:
            Full message history including tool results.

        Raises:
            UserFixableError: When human intervention is required.
            UnexpectedError: On unrecoverable internal failures.
            Exception: Any other exception raised by the loop is re-raised after
                transitioning the lifecycle to ``FAILED``.
        """
        if self.session_id is None:
            self.session_id = uuid4().hex[:12]
        if self.trace_id is None:
            self.trace_id = uuid4().hex

        configure_logging(level=self.log_level, json=self.log_json)

        otel_endpoint = tracing_endpoint_from_env()
        if otel_endpoint:
            configure_tracing(
                endpoint=otel_endpoint,
                service_name="pyarnes-agent",
            )

        from pyarnes_core.observe.logger import get_logger  # noqa: PLC0415 — deferred to avoid init-time side effects
        _log = get_logger(__name__)

        lifecycle = Lifecycle()
        self.lifecycle = lifecycle
        lifecycle.transition(Phase.RUNNING)
        log_lifecycle_transition(
            _log,
            from_phase=Phase.INIT.value,
            to_phase=Phase.RUNNING.value,
            session_id=self.session_id,
            trace_id=self.trace_id,
            step=0,
        )

        tools = {**global_registry().as_dict(), **self.tools} if self.use_global_registry else self.tools

        loop = AgentLoop(
            tools=tools,
            model=self.model,
            config=self.config,
            guardrail_chain=self.guardrail_chain,
            agent_context=self.agent_context,
            tool_call_logger=self.tool_call_logger,
            error_registry=self.error_registry,
            hook_chain=self.hook_chain,
            steering=self.steering,
            transform_chain=self.transform_chain,
        )

        with session_span("agent-session", session_id=self.session_id, trace_id=self.trace_id):
            try:
                result = await loop.run(messages)
            except Exception:
                lifecycle.transition(Phase.FAILED)
                log_lifecycle_transition(
                    _log,
                    from_phase=Phase.RUNNING.value,
                    to_phase=Phase.FAILED.value,
                    session_id=self.session_id,
                    trace_id=self.trace_id,
                    step=len(messages),
                )
                raise

        lifecycle.transition(Phase.COMPLETED)
        log_lifecycle_transition(
            _log,
            from_phase=Phase.RUNNING.value,
            to_phase=Phase.COMPLETED.value,
            session_id=self.session_id,
            trace_id=self.trace_id,
            step=len(result),
        )
        return result

    @classmethod
    def with_compressor(
        cls,
        tools: dict[str, Any],
        model: ModelClient,
        context_window: int,
        *,
        capacity_threshold: float = 0.75,
        compaction_config: CompactionConfig | None = None,
        **kwargs: Any,
    ) -> AgentRuntime:
        """Build an ``AgentRuntime`` with a ``ContextCompressor`` pre-wired.

        The compressor is prepended to a new ``TransformChain`` (or merged into
        an existing one passed via *kwargs*).

        Args:
            tools: Tool name → handler mapping.
            model: The backing LLM client.
            context_window: Model's maximum token capacity.
            capacity_threshold: Fraction at which compaction fires (default 0.75).
            compaction_config: Compaction tunables; defaults to ``CompactionConfig()``.
            **kwargs: Forwarded verbatim to ``AgentRuntime.__init__``.

        Returns:
            A fully configured ``AgentRuntime`` instance.
        """
        cfg = compaction_config or CompactionConfig()
        compressor = ContextCompressor(
            model=model,
            context_window=context_window,
            capacity_threshold=capacity_threshold,
            config=cfg,
        )
        existing: TransformChain | None = kwargs.pop("transform_chain", None)
        stages = [compressor, *(existing.stages if existing is not None else [])]
        return cls(tools=tools, model=model, transform_chain=TransformChain(stages=stages), **kwargs)
