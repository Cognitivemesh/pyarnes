"""Cap tool-call frequency with a per-tool sliding window.

Each guardrail hook invocation runs in a short-lived process, so state
must live on disk. We keep a single JSON file — ``state_path`` — and
trim timestamps outside the current window on every ``check``.

The guardrail is intentionally a dumb counter: it does not know which
CLI is calling it. A single file persists across sessions so rate
limits survive a Claude Code restart.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_guardrails.guardrails import Guardrail

__all__ = ["RateLimitGuardrail"]

logger = get_logger(__name__)

_DEFAULT_STATE_PATH = Path(".claude/pyarnes/rate_limit.json")


@dataclass(frozen=True, slots=True)
class RateLimitGuardrail(Guardrail):
    """Deny further tool calls when the per-tool window is exhausted.

    Attributes:
        max_calls: Upper bound on calls allowed inside *window_seconds*.
        window_seconds: Width of the sliding window, in seconds.
        state_path: File that persists per-tool timestamps between
            hook invocations. Defaults to
            ``$CLAUDE_PROJECT_DIR/.claude/pyarnes/rate_limit.json`` and
            falls back to a relative path when the env var is unset.
    """

    max_calls: int = 60
    window_seconds: float = 60.0
    state_path: Path | None = None

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:  # noqa: ARG002
        """Record this call and raise when the window is full."""
        path = self._resolve_path()
        state = _load(path)
        now = time.time()
        horizon = now - self.window_seconds
        recent = [ts for ts in state.get(tool_name, []) if ts >= horizon]
        if len(recent) >= self.max_calls:
            log_warning(
                logger,
                "guardrail.rate_limit_blocked",
                tool=tool_name,
                calls=len(recent),
                max_calls=self.max_calls,
                window_seconds=self.window_seconds,
            )
            raise UserFixableError(
                message=(
                    f"Rate limit exceeded for '{tool_name}': "
                    f"{len(recent)} calls in {self.window_seconds:g}s "
                    f"(cap: {self.max_calls})."
                ),
                prompt_hint="Wait for the window to clear or raise max_calls.",
            )
        recent.append(now)
        state[tool_name] = recent
        _save(path, state)

    def _resolve_path(self) -> Path:
        """Return the effective state file path."""
        if self.state_path is not None:
            return self.state_path
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir:
            return Path(project_dir) / _DEFAULT_STATE_PATH
        return _DEFAULT_STATE_PATH


def _load(path: Path) -> dict[str, list[float]]:
    """Read the timestamp map; return an empty dict on first run."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[float]] = {}
    for tool, timestamps in raw.items():
        if isinstance(tool, str) and isinstance(timestamps, list):
            result[tool] = [float(t) for t in timestamps if isinstance(t, (int, float))]
    return result


def _save(path: Path, state: dict[str, list[float]]) -> None:
    """Persist the timestamp map, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
