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
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_harness.capture.tool_log import ToolCallLogger

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
    """

    max_iterations: int = 50
    max_retries: int = 2
    retry_base_delay: float = 1.0

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_iterations < 1:
            msg = "max_iterations must be >= 1"
            raise ValueError(msg)
        if self.max_retries < 0:
            msg = "max_retries must be >= 0"
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
    """

    tools: dict[str, ToolHandler]
    model: ModelClient
    config: LoopConfig = field(default_factory=LoopConfig)
    tool_call_logger: ToolCallLogger | None = None

    async def run(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute the agent loop until completion or limit.

        Args:
            messages: Initial conversation messages.

        Returns:
            The full message history including tool results.

        Raises:
            UserFixableError: When human intervention is required.
            UnexpectedError: On unrecoverable internal failures.
        """
        for iteration in range(self.config.max_iterations):
            log_event(logger, "loop.iteration", iteration=iteration)
            action = await self.model.next_action(messages)
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

        log_warning(
            logger,
            "loop.max_iterations_reached",
            limit=self.config.max_iterations,
        )
        return messages

    async def _call_tool(
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
            self._log_tool_call(
                name, arguments, msg, started_at=started_at, start_mono=start_mono
            )
            return msg

        attempt = 0
        max_attempts = self.config.max_retries + 1
        while attempt < max_attempts:
            try:
                result = await handler.execute(arguments)
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
                    self._log_tool_call(
                        name, arguments, msg,
                        started_at=started_at, start_mono=start_mono,
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
                msg = ToolMessage(
                    tool_call_id=tool_call_id,
                    content=f"Error (model can retry): {exc}",
                    is_error=True,
                )
                self._log_tool_call(
                    name, arguments, msg,
                    started_at=started_at, start_mono=start_mono,
                )
                return msg

            except UserFixableError:
                raise

            except HarnessError as exc:
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
                msg = ToolMessage(
                    tool_call_id=tool_call_id,
                    content=str(result),
                    raw_result=result,
                )
                self._log_tool_call(
                    name, arguments, msg,
                    started_at=started_at, start_mono=start_mono,
                )
                return msg

        msg = "Retry loop exited without returning — this should be unreachable"  # pragma: no cover
        raise AssertionError(msg)  # pragma: no cover

    # ── internals ──────────────────────────────────────────────────────

    @staticmethod
    def _as_tool_entry(result: ToolMessage) -> dict[str, Any]:
        """Shape a ``ToolMessage`` as a tool-role message dict."""
        return {
            "role": "tool",
            "tool_call_id": result.tool_call_id,
            "content": result.content,
            "is_error": result.is_error,
        }

    def _log_tool_call(
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
        self.tool_call_logger.log_call(
            tool,
            arguments,
            result=payload,
            is_error=result.is_error,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
        )
