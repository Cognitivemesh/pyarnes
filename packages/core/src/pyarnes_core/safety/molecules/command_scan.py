"""Command-scan molecule — regex match across all configured argument keys.

Composes :func:`walk_values_for_keys` and :func:`walk_strings` with
regex matching so ``CommandGuardrail`` no longer hardcodes the key
``"command"``. Addresses A3 and A4.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from functools import lru_cache

from pyarnes_core.errors import UserFixableError
from pyarnes_core.safety.atoms import walk_strings, walk_values_for_keys

__all__ = [
    "scan_for_patterns",
]


@lru_cache(maxsize=128)
def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patterns)


def scan_for_patterns(
    arguments: dict[str, object],
    *,
    keys: Iterable[str],
    patterns: Iterable[str],
    tool_name: str,
) -> None:
    """Raise ``UserFixableError`` when any pattern matches any command string.

    Collects every string reachable under any key in *keys* (with
    nesting), joins list/tuple values with single spaces to match the
    argv-concatenation convention, and applies each regex in *patterns*.

    Args:
        arguments: The tool's argument dict.
        keys: Argument keys that should be treated as command text.
        patterns: Regex patterns to reject. Compiled once per unique
            tuple and cached so the hot path pays the compile cost only
            the first time a given guardrail is used.
        tool_name: Tool name for the error message (kept for parity with
            other guardrails — callers use it in their error payloads).

    Raises:
        UserFixableError: On the first pattern/command match.
    """
    compiled = _compile_patterns(tuple(patterns))
    for raw in walk_values_for_keys(arguments, keys=keys):
        for candidate in _coerce_to_strings(raw):
            for pattern in compiled:
                if pattern.search(candidate):
                    raise UserFixableError(
                        message=(
                            f"Command for tool '{tool_name}' blocked by "
                            f"pattern: {pattern.pattern}"
                        ),
                        prompt_hint="Review and approve this command manually.",
                    )


def _coerce_to_strings(raw: object) -> Iterable[str]:
    """Join list/tuple shells into space-separated strings; walk nested dicts."""
    if isinstance(raw, (list, tuple)):
        parts = list(walk_strings(raw))
        return [" ".join(parts)] if parts else []
    return list(walk_strings(raw))
