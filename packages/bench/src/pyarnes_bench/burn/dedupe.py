"""Drop replayed/duplicate tool calls from a CC session stream.

Claude Code's resume flow occasionally re-emits already-seen messages.
KPIs and cost roll-ups must dedupe these so a resumed session is not
billed twice.

Dedup key is ``(started_at, normalized_tool, canonical_arguments)`` -
two calls with identical timestamps and arguments are considered the
same call. Output preserves the original order.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from pyarnes_bench.burn.normalize import normalize_tool
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = ["dedupe"]


def _canon_args(args: dict[str, Any]) -> str:
    """Return a stable string key for *args*.

    ``sort_keys=True`` makes dict ordering irrelevant; ``default=str``
    falls back to ``repr`` for any value that isn't JSON-native, so the
    serialiser cannot raise.
    """
    return json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)


def dedupe(entries: Iterable[ToolCallEntry]) -> Iterator[ToolCallEntry]:
    """Yield each unique :class:`ToolCallEntry` once, in original order."""
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = (entry.started_at, normalize_tool(entry.tool), _canon_args(entry.arguments))
        if key in seen:
            continue
        seen.add(key)
        yield entry
