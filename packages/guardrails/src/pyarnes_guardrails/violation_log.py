"""Append guardrail violations to a sidecar JSONL file.

The file lives next to the Claude Code project settings so the bench
:class:`~pyarnes_bench.GuardrailComplianceScorer` can pick it up without
parsing the CC transcript itself — hooks know which guardrail fired;
the transcript does not.

Default location is ``$CLAUDE_PROJECT_DIR/.claude/pyarnes/violations.jsonl``;
when the env var is unset we fall back to the same relative path. Rotation
is not handled here — adopters who want log rotation can swap in logrotate
or point each session at its own path.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Violation", "append_violation", "default_violation_log_path"]

_DEFAULT_REL_PATH = Path(".claude/pyarnes/violations.jsonl")


@dataclass(frozen=True, slots=True)
class Violation:
    """Immutable record of one guardrail block.

    Attributes:
        guardrail: Class name of the guardrail that fired.
        tool: Name of the tool the agent tried to call.
        reason: Human-readable description copied from the error.
        hook: Which CC hook detected the violation (``PreToolUse`` /
            ``PostToolUse``).
        session_id: CC session identifier, when available.
        timestamp: Epoch seconds at detection time.
        extra: Free-form key-value metadata attached by the hook.
    """

    guardrail: str
    tool: str
    reason: str
    hook: str
    session_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


def default_violation_log_path() -> Path:
    """Return the default path, honouring ``CLAUDE_PROJECT_DIR`` when set."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir) / _DEFAULT_REL_PATH
    return _DEFAULT_REL_PATH


def append_violation(violation: Violation, *, path: Path | None = None) -> Path:
    """Append *violation* as one JSON line and return the path written to."""
    target = path or default_violation_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(violation)) + "\n")
    return target
