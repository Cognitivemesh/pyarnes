"""Cap tool-call frequency with a per-tool sliding window.

Each guardrail hook invocation runs in a short-lived process, so state
must live on disk. We keep a single JSON file — ``state_path`` — and
trim timestamps outside the current window on every ``check``.

**Fail-closed on tampering.** If the state file is present but cannot be
parsed as the expected shape, the guardrail raises ``UserFixableError``
rather than silently resetting the counter — otherwise an agent could
zero its own rate limit by writing malformed JSON through any ``Write``
or ``Bash`` tool. Writes go through
:func:`pyarnes_core.atomic_write.write_private` so the file is created
``0o600`` and a crash mid-write cannot produce a truncated state file.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyarnes_core.atomic_write import write_private
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
        write_private(path, json.dumps(state))

    def _resolve_path(self) -> Path:
        """Return the effective state file path."""
        if self.state_path is not None:
            return self.state_path
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir:
            return Path(project_dir) / _DEFAULT_STATE_PATH
        return _DEFAULT_STATE_PATH


def _load(path: Path) -> dict[str, list[float]]:
    """Read the timestamp map; fail closed on a tampered file.

    Returns an empty dict when the file does not yet exist (first-run).
    Raises :class:`UserFixableError` when the file exists but cannot be
    parsed or has the wrong shape — silently resetting to ``{}`` would
    let a malicious tool call clear its own rate limit by writing
    garbage.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise UserFixableError(
            message=(
                f"Rate-limit state at {path} is corrupt ({type(exc).__name__}). "
                "Refusing to reset the counter automatically."
            ),
            prompt_hint="Inspect the file and delete it only if you trust its origin.",
        ) from exc
    if not isinstance(raw, dict):
        raise UserFixableError(
            message=f"Rate-limit state at {path} has the wrong shape; expected an object.",
            prompt_hint="Inspect the file and delete it only if you trust its origin.",
        )
    result: dict[str, list[float]] = {}
    for tool, timestamps in raw.items():
        if not isinstance(tool, str) or not isinstance(timestamps, list):
            raise UserFixableError(
                message=f"Rate-limit state at {path} has malformed entries.",
                prompt_hint="Inspect the file and delete it only if you trust its origin.",
            )
        result[tool] = [float(t) for t in timestamps if isinstance(t, (int, float))]
    return result
