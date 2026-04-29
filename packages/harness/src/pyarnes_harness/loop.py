"""Async agent loop with structured error handling.

The loop runs tool calls dispatched by an LLM, captures every output,
and routes failures through the four-error taxonomy defined in
``pyarnes_core.errors``.

Key design choices
------------------
* **Async-first** — non-blocking I/O so tool calls that await network
  or subprocess work don't stall the loop. Tool dispatch is serial
  by design; batch parallelism is out of scope.
* **Retry policy** — ``LoopConfig.max_retries`` sets the floor; a
  ``TransientError`` may raise the cap or extend the delay. The
  effective policy is the per-attempt ``max`` of both sources.
* **LLM feedback** — recoverable errors are fed back as ``ToolMessage``
  results so the model can self-correct. Malformed actions
  (unknown type, empty tool name) also become recoverable error
  messages instead of silent ``"Unknown tool: "`` dispatches.
* **Full capture** — every step is logged as structured JSONL via the
  observe layer. Retry duration is measured across all attempts,
  not per-attempt.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.dispatch import (
    ActionKind,
    classify,
    merge_retry_caps,
    next_delay,
)
from pyarnes_core.error_registry import ErrorHandlerRegistry
from pyarnes_core.errors import (
    HarnessError,
    LLMRecoverableError,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.observability import (
    log_event,
    log_warning,
    monotonic_duration,
    start_timer,
)
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.safety.redact import redact
from pyarnes_core.safety.sanitize import sanitize_messages
from pyarnes_core.sandbox import SandboxHook
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_guardrails.guardrails import GuardrailChain
from pyarnes_harness.budget import IterationBudget
from pyarnes_harness.capture.tool_log import ToolCallLogger
from pyarnes_harness.context import AgentContext
from pyarnes_harness.hooks import HookChain
from pyarnes_harness.parallel import execute_batch
from pyarnes_harness.steering import SteeringQueue
from pyarnes_harness.transform import TransformChain

__all__ = [
    "AgentLoop",
    "LoopConfig",
    "ToolMessage",
]

logger = get_logger(__name__)


# ── Data ───────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ToolMessage:
    """Result fed back to the model after a tool call.

    Attributes:
        tool_call_id: Identifier linking this result to the original call.
        content: Stringified tool output or error description.
        is_error: ``True`` when the content describes a failure.
        raw_result: The original, unstringified return value (``None`` for
            errors). Kept for audit-log structured persistence so
            ``ToolCallEntry.result`` can retain dict/list shape (D18).
    """

    tool_call_id: str
    content: str
    is_error: bool = False
    raw_result: Any = None
    terminate: bool = False


@dataclass(slots=True)
class LoopConfig:
    """Tunables for the agent loop.

    Attributes:
        max_iterations: Hard ceiling on loop cycles before forced stop.
        max_retries: Cap on transient-error retries (Stripe-style, default 2).
            A ``TransientError`` raised by a tool may *raise* this cap via
            its own ``max_retries`` attribute — the effective cap is the
            maximum of both.
        retry_base_delay: Seconds before the first retry. Likewise, a
            ``TransientError.retry_delay_seconds`` may raise this floor.
        reflection_interval: Inject a reflection checkpoint every N iterations.
            ``0`` (the default) disables reflection.
    """

    max_iterations: int = 50
    max_retries: int = 2
    retry_base_delay: float = 1.0
    reflection_interval: int = 0
    budget: IterationBudget | None = None

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_iterations < 1:
            msg = "max_iterations must be >= 1"
            raise ValueError(msg)
        if self.max_retries < 0:
            msg = "max_retries must be >= 0"
            raise ValueError(msg)
        if self.reflection_interval < 0:
            msg = "reflection_interval must be >= 0"
            raise ValueError(msg)


# ── Loop ───────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class AgentLoop:
    """Core agentic harness loop.

    Not safe for concurrent mutation. Expect a single task to own the
    ``AgentLoop`` instance for the duration of a session; concurrent
    dispatch would race on the message history.

    Attributes:
        tools: Mapping of tool names to their handlers.
        model: The backing LLM client.
        config: Loop tunables.
        tool_call_logger: Optional JSONL logger that persists every tool
            invocation to disk.  When ``None`` (the default), file-based
            logging is skipped.
        guardrail_chain: Optional chain of guardrails checked before each
            tool execution. ``None`` skips all guardrail checks.
        agent_context: Optional domain-specific guidance injected into the
            system message before the first iteration.
        error_registry: Optional registry of custom async recovery handlers.
            When set, the registry is consulted in the ``HarnessError``
            catch-all branch before falling through to ``UnexpectedError``.
        sandbox: Optional sandbox hook called around each tool execution.
            ``enter()`` is awaited before the tool runs; ``exit(exc)`` is
            awaited after, receiving the exception or ``None`` on success.
        hook_chain: Optional chain of pre/post middleware hooks. Pre-hooks
            run before guardrails and may mutate arguments; post-hooks
            transform the result after successful execution.
        steering: Optional queue of mid-execution user notes. Notes are
            drained and prepended to messages at the start of each iteration.
        transform_chain: Optional pipeline of message transformers applied
            before each ``model.next_action()`` call. Runs before
            ``sanitize_messages`` so summaries produced by transformers are
            also sanitized.
    """

    tools: dict[str, ToolHandler]
    model: ModelClient
    config: LoopConfig = field(default_factory=LoopConfig)
    tool_call_logger: ToolCallLogger | None = None
    guardrail_chain: GuardrailChain | None = None
    agent_context: AgentContext | None = None
    error_registry: ErrorHandlerRegistry | None = None
    sandbox: SandboxHook | None = None
    hook_chain: HookChain | None = None
    steering: SteeringQueue | None = None
    transform_chain: TransformChain | None = None

    async def run(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:  # noqa: C901
        """Execute the agent loop until completion or limit.

        Args:
            messages: Initial conversation messages.

        Returns:
            The full message history including tool results.

        Raises:
            UserFixableError: When human intervention is required.
            UnexpectedError: On unrecoverable internal failures.
        """
        if self.agent_context is not None and messages and messages[0].get("role") == "system":
            ctx_fragment = self.agent_context.to_system_prompt()
            messages = [
                {**messages[0], "content": f"{messages[0]['content']}\n\n{ctx_fragment}"},
                *messages[1:],
            ]

        for iteration in range(self.config.max_iterations):
            log_event(logger, "loop.iteration", iteration=iteration)

            if self.steering is not None:
                notes = await self.steering.drain()
                messages.extend(notes)

            if self.config.budget is not None:  # noqa: SIM102
                if not await self.config.budget.consume():
                    log_warning(logger, "loop.budget_exhausted", iteration=iteration)
                    return messages

            if (
                self.config.reflection_interval > 0
                and iteration > 0
                and iteration % self.config.reflection_interval == 0
            ):
                reflection = await self._request_reflection(messages)
                messages.append(reflection)

            transformed = await self.transform_chain.apply(messages) if self.transform_chain else messages
            action = await self.model.next_action(sanitize_messages(transformed))

            if action.get("type") == "tool_calls":
                batch_results = await self._call_batch(action.get("calls", []))
                messages.append(action)
                for r in batch_results:
                    messages.append(self._as_tool_entry(r))
                continue

            kind = classify(action)

            if kind is ActionKind.FINAL_ANSWER:
                log_event(logger, "loop.completed", iteration=iteration)
                messages.append(action)
                return messages

            if kind is ActionKind.UNKNOWN:
                result = ToolMessage(
                    tool_call_id=action.get("id", ""),
                    content=f"Unrecognized action type: {action.get('type')!r}",
                    is_error=True,
                )
                messages.append(action)
                messages.append(self._as_tool_entry(result))
                continue

            tool_name = action["tool"]
            tool_call_id = action.get("id", "")
            arguments = action.get("arguments", {})

            result = await self._call_tool(tool_name, tool_call_id, arguments)
            messages.append(action)
            messages.append(self._as_tool_entry(result))

            if result.terminate:
                log_event(logger, "loop.tool_terminated", tool=tool_name, iteration=iteration)
                return messages

        log_warning(
            logger,
            "loop.max_iterations_reached",
            limit=self.config.max_iterations,
        )
        return messages

    async def _call_batch(self, calls: list[dict[str, Any]]) -> list[ToolMessage]:
        """Dispatch a batch of tool calls, parallelizing when path-independent."""

        async def dispatch(name: str, call_id: str, arguments: dict[str, Any]) -> ToolMessage:
            return await self._call_tool(name, call_id, arguments)

        return await execute_batch(calls, dispatch)  # type: ignore[return-value]

    async def _call_tool(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self,
        name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> ToolMessage:
        """Dispatch a single tool call with full error routing.

        The retry timer is hoisted above the attempt loop so the JSONL
        entry records the total wall-clock span, not the final attempt
        alone (B7).
        """
        handler = self.tools.get(name)
        started_at, start_mono = start_timer()

        if handler is None:
            msg = ToolMessage(
                tool_call_id=tool_call_id,
                content=f"Unknown tool: {name}",
                is_error=True,
            )
            await self._log_tool_call(
                name,
                arguments,
                msg,
                started_at=started_at,
                start_mono=start_mono,
            )
            return msg

        if self.hook_chain is not None:
            try:
                arguments = await self.hook_chain.run_pre(name, arguments)
            except LLMRecoverableError as exc:
                msg = self._recoverable_error_message(tool_call_id, exc)
                await self._log_tool_call(name, arguments, msg, started_at=started_at, start_mono=start_mono)
                return msg

        guard_result = await self._check_guardrails(name, tool_call_id, arguments, started_at, start_mono)
        if guard_result is not None:
            return guard_result

        attempt = 0
        max_attempts = self.config.max_retries + 1
        while attempt < max_attempts:
            _sandbox_exc: BaseException | None = None
            try:
                if self.sandbox is not None:
                    await self.sandbox.enter()
                try:
                    result = await handler.execute(arguments)
                except BaseException as _exc:
                    _sandbox_exc = _exc
                    raise
                finally:
                    if self.sandbox is not None:
                        await self.sandbox.exit(_sandbox_exc)
            except TransientError as exc:
                policy = merge_retry_caps(
                    self.config.max_retries,
                    self.config.retry_base_delay,
                    error_max=exc.max_retries,
                    error_delay=exc.retry_delay_seconds,
                )
                # Re-expand in case TransientError raised the cap mid-loop.
                max_attempts = policy.max_retries + 1
                if attempt >= policy.max_retries:
                    logger.exception(
                        "tool.transient_exhausted tool={tool} attempts={attempts}",
                        tool=name,
                        attempts=attempt + 1,
                    )
                    msg = ToolMessage(
                        tool_call_id=tool_call_id,
                        content=f"Transient failure after {attempt + 1} attempts: {exc}",
                        is_error=True,
                    )
                    await self._log_tool_call(
                        name,
                        arguments,
                        msg,
                        started_at=started_at,
                        start_mono=start_mono,
                    )
                    return msg
                delay = next_delay(policy, attempt)
                log_warning(
                    logger,
                    "tool.transient_retry",
                    tool=name,
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            except LLMRecoverableError as exc:
                log_warning(logger, "tool.llm_recoverable", tool=name, error=str(exc))
                msg = self._recoverable_error_message(tool_call_id, exc)
                await self._log_tool_call(
                    name,
                    arguments,
                    msg,
                    started_at=started_at,
                    start_mono=start_mono,
                )
                return msg

            except UserFixableError:
                raise

            except HarnessError as exc:
                if self.error_registry is not None:
                    # Handler raises propagate uncaught — the original error context is lost.
                    # Handlers must not raise; wrap side-effects in try/except internally.
                    custom_result = await self.error_registry.dispatch(exc)
                    if custom_result is not None:
                        if not isinstance(custom_result, ToolMessage):
                            raise UnexpectedError(
                                message=(
                                    f"Error registry handler for {type(exc).__name__!r} returned "
                                    f"{type(custom_result).__name__!r}, expected ToolMessage"
                                ),
                                original=exc,
                            ) from exc
                        await self._log_tool_call(
                            name, arguments, custom_result, started_at=started_at, start_mono=start_mono
                        )
                        return custom_result
                raise UnexpectedError(
                    message=f"Unexpected harness error in tool '{name}': {exc}",
                    original=exc,
                ) from exc

            except Exception as exc:
                raise UnexpectedError(
                    message=f"Unexpected error in tool '{name}': {exc}",
                    original=exc,
                ) from exc

            else:
                log_event(logger, "tool.success", tool=name, attempt=attempt)
                if self.hook_chain is not None:
                    result = await self.hook_chain.run_post(name, arguments, result, is_error=False)
                terminate = isinstance(result, dict) and bool(result.get("terminate"))
                content = redact(
                    str(result.get("content", result) if isinstance(result, dict) and terminate else result)
                )  # noqa: E501
                msg = ToolMessage(
                    tool_call_id=tool_call_id,
                    content=content,
                    raw_result=result,
                    terminate=terminate,
                )
                await self._log_tool_call(
                    name,
                    arguments,
                    msg,
                    started_at=started_at,
                    start_mono=start_mono,
                )
                return msg

        msg = "Retry loop exited without returning — this should be unreachable"  # pragma: no cover
        raise AssertionError(msg)  # pragma: no cover

    # ── internals ──────────────────────────────────────────────────────

    async def _check_guardrails(
        self,
        name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        started_at: str,
        start_mono: float,
    ) -> ToolMessage | None:
        """Run the guardrail chain before tool execution.

        Returns a ``ToolMessage`` error on recoverable violations, re-raises
        ``UserFixableError`` for human-intervention cases, and returns
        ``None`` when all guardrails pass.
        """
        if self.guardrail_chain is None:
            return None
        try:
            await self.guardrail_chain.check(name, arguments)
        except UserFixableError:
            raise
        except LLMRecoverableError as exc:
            # Guardrail blocks the call; surface the error to the model via the
            # standard recoverable-error ToolMessage rather than raising, so the
            # model can adjust and retry.  _log_tool_call is async, so await is
            # required — omitting it silently discards the audit-log coroutine.
            msg = self._recoverable_error_message(tool_call_id, exc)
            await self._log_tool_call(name, arguments, msg, started_at=started_at, start_mono=start_mono)
            return msg
        return None

    async def _request_reflection(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Ask the model to reflect on progress so far.

        A probe message is appended to a temporary copy of the history so
        the probe itself is not permanently recorded. The model's response
        is returned as an assistant turn.
        """
        probe = {
            "role": "user",
            "content": (
                "REFLECTION CHECKPOINT: Briefly review your progress. "
                "Are you on track? Have you made any mistakes? "
                "Should you backtrack or adjust your approach?"
            ),
        }
        response = await self.model.next_action([*messages, probe])
        return {"role": "assistant", "content": response.get("content", "")}

    @staticmethod
    def _recoverable_error_message(tool_call_id: str, exc: Exception) -> ToolMessage:
        """Build a ToolMessage that feeds a recoverable error back to the model."""
        return ToolMessage(
            tool_call_id=tool_call_id,
            content=f"Error (model can retry): {exc}",
            is_error=True,
        )

    @staticmethod
    def _as_tool_entry(result: ToolMessage) -> dict[str, Any]:
        """Shape a ``ToolMessage`` as a tool-role message dict."""
        return {
            "role": "tool",
            "tool_call_id": result.tool_call_id,
            "content": result.content,
            "is_error": result.is_error,
        }

    async def _log_tool_call(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: ToolMessage,
        *,
        started_at: str,
        start_mono: float,
    ) -> None:
        """Persist a tool call entry to the JSONL log (if configured)."""
        if self.tool_call_logger is None:
            return
        finished_at, duration = monotonic_duration(start_mono)
        # Errors carry a human-readable string; successes carry the raw
        # structured return value so ToolCallEntry.result keeps shape.
        payload: Any = result.raw_result if not result.is_error else result.content
        await asyncio.to_thread(
            self.tool_call_logger.log_call,
            tool,
            arguments,
            result=payload,
            is_error=result.is_error,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
        )
