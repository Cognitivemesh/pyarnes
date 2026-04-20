"""JSONL tool-call logger — persists every tool invocation to disk.

Every call that flows through the agent loop is appended as a single JSON
line to a ``.jsonl`` file inside the workspace.  Each entry records:

* **tool** — name of the tool that was called
* **arguments** — the full argument dict passed to the tool
* **result** — stringified return value *or* error description
* **is_error** — ``True`` when the call failed
* **started_at** — ISO-8601 timestamp when execution began
* **finished_at** — ISO-8601 timestamp when execution ended
* **duration_seconds** — wall-clock time

The file is opened in append mode and flushed after every write so that
partial runs are never lost.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

__all__ = [
    "ToolCallEntry",
    "ToolCallLogger",
]


def _iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class ToolCallEntry:
    """Immutable record of a single tool invocation.

    Attributes:
        tool: Name of the tool that was called.
        arguments: Key-value arguments passed to the tool.
        result: Return value (native JSON types kept verbatim) or an
            error-description string. Non-native types fall through to
            ``str()`` at the JSON write site.
        is_error: ``True`` when the call ended in failure.
        started_at: ISO-8601 timestamp when execution began.
        finished_at: ISO-8601 timestamp when execution ended.
        duration_seconds: Wall-clock execution time.
    """

    tool: str
    arguments: dict[str, Any]
    result: Any
    is_error: bool
    started_at: str
    finished_at: str
    duration_seconds: float

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (one JSON line)."""
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "result": self.result,
            "is_error": self.is_error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }


class ToolCallLogger:
    """Append-only JSONL logger that persists tool calls to a file.

    Usage::

        logger = ToolCallLogger(path=Path("/workspace/.harness/tool_calls.jsonl"))
        entry = logger.log_call("read_file", {"path": "a.py"}, result="contents…")
        logger.close()

    The logger can also be used as a context manager::

        with ToolCallLogger(path=Path("calls.jsonl")) as log:
            log.log_call("echo", {"text": "hi"}, result="hi")
    """

    def __init__(self, path: Path) -> None:
        """Open (or create) the JSONL file for appending.

        Args:
            path: Filesystem path where tool-call entries will be written.
                  Parent directories are created automatically.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._file: TextIO = path.open("a", encoding="utf-8")

    # ── public API ─────────────────────────────────────────────────────

    def log_call(  # noqa: PLR0913
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        result: Any,
        is_error: bool = False,
        started_at: str | None = None,
        finished_at: str | None = None,
        duration_seconds: float | None = None,
    ) -> ToolCallEntry:
        """Record a tool invocation and flush to disk.

        Args:
            tool: Name of the tool that was called.
            arguments: Arguments passed to the tool.
            result: Return value (native JSON types kept verbatim) or
                error description.
            is_error: Whether the call ended in failure.
            started_at: ISO-8601 start timestamp (auto-filled when ``None``).
            finished_at: ISO-8601 end timestamp (auto-filled when ``None``).
            duration_seconds: Execution duration (auto-filled when ``None``).

        Returns:
            The immutable ``ToolCallEntry`` that was written.
        """
        now = _iso_now()
        entry = ToolCallEntry(
            tool=tool,
            arguments=arguments,
            result=result,
            is_error=is_error,
            started_at=started_at or now,
            finished_at=finished_at or now,
            duration_seconds=duration_seconds or 0.0,
        )
        self._write(entry)
        return entry

    @staticmethod
    def start_timer() -> tuple[str, float]:
        """Capture the start timestamp and monotonic clock.

        Returns:
            A tuple of ``(iso_timestamp, monotonic_ns)`` to pass into
            :meth:`log_call` later.
        """
        return _iso_now(), time.monotonic()

    @staticmethod
    def stop_timer(start_mono: float) -> tuple[str, float]:
        """Capture the end timestamp and compute duration.

        Args:
            start_mono: The monotonic time returned by :meth:`start_timer`.

        Returns:
            A tuple of ``(iso_timestamp, duration_seconds)``.
        """
        return _iso_now(), time.monotonic() - start_mono

    # ── lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        """Flush and close the underlying file."""
        if not self._file.closed:
            self._file.close()

    @property
    def path(self) -> Path:
        """Return the path to the JSONL file."""
        return self._path

    def __enter__(self) -> ToolCallLogger:
        """Support ``with`` statement."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close on context-manager exit."""
        self.close()

    def __repr__(self) -> str:  # noqa: D105
        return f"ToolCallLogger(path={self._path!r})"

    # ── internals ──────────────────────────────────────────────────────

    def _write(self, entry: ToolCallEntry) -> None:
        """Serialise and append one JSON line, then flush."""
        line = json.dumps(entry.as_dict(), default=str, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
