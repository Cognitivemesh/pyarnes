"""ClaudeCodeProvider — field-name mapping for Claude Code JSONL sessions.

This module contains only the mapping from Claude Code's on-disk schema to
the generic burn types. All parsing logic lives in JsonlProvider.

Invariant: if this file grows beyond field mappings and tool/provider
identifiers, that is a sign that parsing logic has leaked from JsonlProvider.

Session files live at::

    ~/.claude/projects/<project-slug>/*.jsonl

Each file is a newline-delimited sequence of JSON objects. Only entries
where ``type == "assistant"`` and ``message.usage`` is present are parsed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pyarnes_bench.burn.provider import JsonlProvider
from pyarnes_bench.burn.types import TokenUsage

__all__ = [
    "ClaudeCodeProvider",
]


class ClaudeCodeProvider(JsonlProvider):
    """Maps Claude Code's JSONL schema to the generic burn types.

    Only this class knows Claude Code's field names. JsonlProvider owns
    all parsing logic. Contradiction: any parsing logic here is a bug.
    """

    DEFAULT_BASE: ClassVar[Path] = Path.home() / ".claude" / "projects"

    @property
    def tool_name(self) -> str:
        """Return the CLI identifier used in session metadata."""
        return "claude-code"

    @property
    def ai_provider_name(self) -> str:
        """Return the model provider name."""
        return "anthropic"

    @property
    def session_glob(self) -> str:
        """Return the glob pattern that matches Claude Code session files."""
        return "*/*.jsonl"

    def is_model_turn(self, entry: dict[str, Any]) -> bool:
        """Return True for assistant-turn entries that may carry usage data."""
        return entry.get("type") == "assistant"

    def extract_usage(self, entry: dict[str, Any]) -> TokenUsage | None:
        """Extract token counts from a Claude Code assistant-turn entry."""
        raw = entry.get("message", {}).get("usage")
        if not isinstance(raw, dict):
            return None
        return TokenUsage(
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            cache_creation_tokens=raw.get("cache_creation_input_tokens", 0),
            cache_read_tokens=raw.get("cache_read_input_tokens", 0),
        )

    def extract_model_id(self, entry: dict[str, Any]) -> str:
        """Return the model identifier string from the entry."""
        return entry.get("message", {}).get("model", "")

    def extract_timestamp(self, entry: dict[str, Any]) -> str | None:
        """Return the ISO 8601 timestamp string, or None if absent."""
        return entry.get("timestamp")

    def infer_model_family(self, model_id: str) -> str:
        """Return the family prefix (e.g. 'claude') from a model ID string."""
        # "some-family-version" → "some"; empty string when model_id unknown
        return model_id.split("-", maxsplit=1)[0] if model_id else ""
