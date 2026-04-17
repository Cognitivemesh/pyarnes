"""Async agent loop with structured error handling.

The loop runs tool calls dispatched by an LLM, captures every output, and
routes failures through the four-error taxonomy defined in ``errors.py``.

Key design choices
------------------
* **Async-first** — avoids GIL contention; tool calls can overlap via
  ``asyncio.TaskGroup`` on Python 3.13+.
* **Retry cap** — transient errors are retried at most *twice* (Stripe pattern).
* **LLM feedback** — recoverable errors are fed back as ``ToolMessage`` results
  so the model can self-correct (Anthropic pattern).
* **Full capture** — every step is logged as structured JSONL via the observe layer.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from pyarnes.harness.errors import (
    HarnessError,
    LLMRecoverableError,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes.observe.logger import get_logger
from pyarnes.types import ModelClient, ToolHandler

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
    """

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass(slots=True)
class LoopConfig:
    """Tunables for the agent loop.

    Attributes:
        max_iterations: Hard ceiling on loop cycles before forced stop.
        max_retries: Cap on transient-error retries (Stripe-style, default 2).
        retry_base_delay: Seconds before the first retry (doubles each attempt).
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

    Attributes:
        tools: Mapping of tool names to their handlers.
        model: The backing LLM client.
        config: Loop tunables.
    """

    tools: dict[str, ToolHandler]
    model: ModelClient
    config: LoopConfig = field(default_factory=LoopConfig)

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
            logger.info("loop.iteration", iteration=iteration)

            action = await self.model.next_action(messages)

            if action.get("type") == "final_answer":
                logger.info("loop.completed", iteration=iteration)
                messages.append(action)
                return messages

            tool_name = action.get("tool", "")
            tool_call_id = action.get("id", "")
            arguments = action.get("arguments", {})

            result = await self._call_tool(tool_name, tool_call_id, arguments)
            messages.append(action)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
            )

        logger.warning("loop.max_iterations_reached", limit=self.config.max_iterations)
        return messages

    async def _call_tool(
        self,
        name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> ToolMessage:
        """Dispatch a single tool call with full error routing."""
        handler = self.tools.get(name)
        if handler is None:
            return ToolMessage(
                tool_call_id=tool_call_id,
                content=f"Unknown tool: {name}",
                is_error=True,
            )

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await handler.execute(arguments)
                logger.info("tool.success", tool=name, attempt=attempt)
                return ToolMessage(tool_call_id=tool_call_id, content=str(result))

            except TransientError as exc:
                if attempt >= self.config.max_retries:
                    logger.exception("tool.transient_exhausted", tool=name, error=str(exc))
                    return ToolMessage(
                        tool_call_id=tool_call_id,
                        content=f"Transient failure after {attempt + 1} attempts: {exc}",
                        is_error=True,
                    )
                delay = self.config.retry_base_delay * (2**attempt)
                logger.warning("tool.transient_retry", tool=name, attempt=attempt, delay=delay)
                await asyncio.sleep(delay)

            except LLMRecoverableError as exc:
                logger.warning("tool.llm_recoverable", tool=name, error=str(exc))
                return ToolMessage(
                    tool_call_id=tool_call_id,
                    content=f"Error (model can retry): {exc}",
                    is_error=True,
                )

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

        msg = "Retry loop exited without returning — this should be unreachable"  # pragma: no cover
        raise AssertionError(msg)  # pragma: no cover
