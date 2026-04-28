"""Single entry-point that wires together configure_logging, Lifecycle, and AgentLoop.

Adopters currently must assemble these three components manually. ``AgentRuntime``
does that wiring so calling code is reduced to constructing the dataclass and
invoking ``run()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pyarnes_core.lifecycle import Lifecycle, Phase
from pyarnes_core.observe.logger import configure_logging
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_guardrails.guardrails import GuardrailChain
from pyarnes_harness.context import AgentContext
from pyarnes_harness.loop import AgentLoop, LoopConfig

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
        session_id: Identifier for this agent session. Auto-generated (12 hex chars) when
            ``None``; written back to the attribute after generation so callers can read it.
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
    session_id: str | None = None
    log_level: str = "INFO"
    log_json: bool = True
    lifecycle: Lifecycle | None = field(default=None, init=False)

    async def run(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute the agent loop for the given message history.

        Steps:
        1. Auto-generate ``session_id`` when not provided.
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

        configure_logging(level=self.log_level, json=self.log_json)

        lifecycle = Lifecycle()
        lifecycle.transition(Phase.RUNNING)
        self.lifecycle = lifecycle

        loop = AgentLoop(
            tools=self.tools,
            model=self.model,
            config=self.config,
            guardrail_chain=self.guardrail_chain,
            agent_context=self.agent_context,
        )

        try:
            result = await loop.run(messages)
        except Exception:
            lifecycle.transition(Phase.FAILED)
            raise

        lifecycle.transition(Phase.COMPLETED)
        return result
