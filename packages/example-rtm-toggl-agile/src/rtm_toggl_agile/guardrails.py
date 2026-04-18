"""Guardrails for the RTM/Toggl → agile pipeline.

These match the spec: ``ApiQuotaGuardrail`` rate-limits external calls and
``SecretScanGuardrail`` refuses to emit credential-shaped values via tool
calls (they'd end up in the ToolCallLogger audit trail otherwise).
"""

from __future__ import annotations

import re
import time
from collections import deque

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails import Guardrail

_SECRET_PATTERNS = (
    re.compile(r"api_key=[\w-]+"),
    re.compile(r"Bearer\s+[\w.-]+"),
    re.compile(r"sk-[\w-]+"),
)


class ApiQuotaGuardrail(Guardrail):
    """Block RTM/Toggl tool calls once a sliding-window call budget is exceeded."""

    def __init__(self, calls_per_minute: int = 60) -> None:
        self.calls_per_minute = calls_per_minute
        self._history: deque[float] = deque()

    def check(self, tool_name: str, arguments: dict) -> None:
        if not tool_name.startswith(("list_rtm", "list_toggl")):
            return
        now = time.monotonic()
        window_start = now - 60
        while self._history and self._history[0] < window_start:
            self._history.popleft()
        if len(self._history) >= self.calls_per_minute:
            raise UserFixableError(
                message=f"rate limit exceeded ({self.calls_per_minute} calls/minute)",
                prompt_hint="Back off and retry after the sliding window clears.",
            )
        self._history.append(now)


class SecretScanGuardrail(Guardrail):
    """Refuse tool calls whose arguments contain credential-shaped strings."""

    def check(self, tool_name: str, arguments: dict) -> None:
        for value in arguments.values():
            text = str(value)
            for pattern in _SECRET_PATTERNS:
                if pattern.search(text):
                    raise UserFixableError(
                        message="credential-shaped value in tool arguments",
                        prompt_hint="Strip secrets from tool inputs before dispatch.",
                    )
