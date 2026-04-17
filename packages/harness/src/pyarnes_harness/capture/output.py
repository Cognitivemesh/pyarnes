"""Raw output and error capture.

Captures stdout, stderr, return values, and exceptions from tool
executions so that reality (not just the happy path) is fed back
to the model.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.observe.logger import get_logger

__all__ = [
    "CapturedOutput",
    "OutputCapture",
]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CapturedOutput:
    """Immutable record of a single tool execution.

    Attributes:
        tool_name: Name of the tool that was called.
        arguments: Arguments passed to the tool.
        stdout: Standard output captured during execution.
        stderr: Standard error captured during execution.
        return_value: The tool's return value (if successful).
        error: String representation of any exception raised.
        traceback_str: Full traceback (if an exception occurred).
        duration_seconds: Wall-clock time for the execution.
        timestamp: Unix timestamp when capture started.
    """

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    error: str | None = None
    traceback_str: str | None = None
    duration_seconds: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def succeeded(self) -> bool:
        """Return ``True`` when the execution completed without errors."""
        return self.error is None

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (suitable for JSONL logging)."""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_value": str(self.return_value) if self.return_value is not None else None,
            "error": self.error,
            "traceback": self.traceback_str,
            "duration_seconds": self.duration_seconds,
            "timestamp": self.timestamp,
            "succeeded": self.succeeded,
        }


class OutputCapture:
    """Capture tool execution results into ``CapturedOutput`` records.

    Usage::

        capture = OutputCapture()
        record = capture.record_success("my_tool", {"arg": 1}, result="ok", duration=0.5)
        # or
        record = capture.record_failure("my_tool", {"arg": 1}, exc, duration=0.3)

        for entry in capture.history:
            print(entry.as_dict())
    """

    def __init__(self) -> None:
        """Initialise an empty capture history."""
        self._history: list[CapturedOutput] = []

    def record_success(  # noqa: PLR0913
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        result: Any = None,
        stdout: str = "",
        stderr: str = "",
        duration: float = 0.0,
    ) -> CapturedOutput:
        """Record a successful tool execution.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments passed to the tool.
            result: The tool's return value.
            stdout: Captured standard output.
            stderr: Captured standard error.
            duration: Wall-clock execution time in seconds.

        Returns:
            The immutable ``CapturedOutput`` record.
        """
        captured = CapturedOutput(
            tool_name=tool_name,
            arguments=arguments,
            stdout=stdout,
            stderr=stderr,
            return_value=result,
            duration_seconds=duration,
        )
        self._history.append(captured)
        logger.info("capture.success tool={tool}", tool=tool_name)
        return captured

    def record_failure(  # noqa: PLR0913
        self,
        tool_name: str,
        arguments: dict[str, Any],
        exc: BaseException,
        *,
        stdout: str = "",
        stderr: str = "",
        duration: float = 0.0,
    ) -> CapturedOutput:
        """Record a failed tool execution.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Arguments passed to the tool.
            exc: The exception that was raised.
            stdout: Captured standard output.
            stderr: Captured standard error.
            duration: Wall-clock execution time in seconds.

        Returns:
            The immutable ``CapturedOutput`` record.
        """
        captured = CapturedOutput(
            tool_name=tool_name,
            arguments=arguments,
            stdout=stdout,
            stderr=stderr,
            error=str(exc),
            traceback_str="".join(traceback.format_exception(exc)),
            duration_seconds=duration,
        )
        self._history.append(captured)
        logger.error("capture.failure tool={tool} error={error}", tool=tool_name, error=str(exc))
        return captured

    @property
    def history(self) -> list[CapturedOutput]:
        """Return a copy of all captured records."""
        return list(self._history)

    def clear(self) -> None:
        """Discard all captured records."""
        self._history.clear()

    def __len__(self) -> int:  # noqa: D105
        return len(self._history)

    def __repr__(self) -> str:  # noqa: D105
        return f"OutputCapture(records={len(self._history)})"
