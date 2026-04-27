"""Append guardrail violations to a sidecar JSONL file.

The file lives next to the Claude Code project settings so the bench
:class:`~pyarnes_bench.GuardrailComplianceScorer` can pick it up without
parsing the CC transcript itself — hooks know which guardrail fired;
the transcript does not.

Default location is ``$CLAUDE_PROJECT_DIR/.claude/pyarnes/violations.jsonl``;
when the env var is unset we fall back to the same relative path.

**Permissions.** Appends go through
:func:`pyarnes_core.atomic_write.append_private` so the file is created
``0o600``. The log may contain high-signal strings (which tool was
attempted, which guardrail tripped, a human-readable reason) — never
the matched secret itself. Callers who build the ``reason`` field are
responsible for keeping the matched text out of it; the shipped
``SecretLeakGuardrail`` does so by design.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pyarnes_core.atomic_write import append_private

__all__ = ["Violation", "append_violation", "default_violation_log_path"]

_DEFAULT_REL_PATH = Path(".claude/pyarnes/violations.jsonl")


@dataclass(frozen=True, slots=True)
class Violation:
    """Immutable record of one guardrail block.

    Attributes:
        guardrail: Class name of the guardrail that fired.
        tool: Name of the tool the agent tried to call.
        reason: Human-readable description copied from the error.
            **Must not contain the secret itself** — the shipped
            ``SecretLeakGuardrail`` enforces this by emitting a generic
            message.
        hook: Which CC hook detected the violation (``PreToolUse`` /
            ``PostToolUse``).
        session_id: CC session identifier, when available.
        timestamp: Epoch seconds at detection time.
    """

    guardrail: str
    tool: str
    reason: str
    hook: str
    session_id: str | None = None
    timestamp: float = field(default_factory=time.time)


def default_violation_log_path() -> Path:
    """Return the default path, honouring ``CLAUDE_PROJECT_DIR`` when set."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir) / _DEFAULT_REL_PATH
    return _DEFAULT_REL_PATH


def append_violation(violation: Violation, *, path: Path | None = None) -> Path:
    """Append *violation* as one JSON line and return the path written to."""
    target = path or default_violation_log_path()
    append_private(target, json.dumps(asdict(violation)) + "\n")
    return target
