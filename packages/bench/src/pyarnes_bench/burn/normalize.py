"""Tool-name and model-alias normalisation for codeburn analytics.

Different agentic harnesses log the same logical tool under different
names (``Bash`` vs ``exec_command`` vs ``str_replace_editor``). KPIs and
detectors compare across harnesses, so every consumer reduces a raw
name to a canonical label first.

Model aliases solve the same problem for proxies: when a deployment
advertises ``my-proxy-opus`` instead of ``claude-opus-4-7``, pricing and
comparison must collapse the alias before lookup.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "CANONICAL_TOOLS",
    "MODEL_ALIASES",
    "ModelAlias",
    "normalize_tool",
    "resolve_model",
]


# Each canonical label is the verb the *user* recognises ("Read a file",
# "Edit a file") rather than the implementation name. MCP tools all
# collapse to ``MCP`` because their analytical weight (network call,
# extra context) is identical regardless of which server is on the
# other end — detectors that need server granularity inspect the raw
# name themselves.
CANONICAL_TOOLS: Final[dict[str, str]] = {
    # Shell / exec
    "bash": "Bash",
    "bashtool": "Bash",
    "exec_command": "Bash",
    # File reads
    "read": "Read",
    "view": "Read",
    "open_file": "Read",
    # File edits
    "edit": "Edit",
    "str_replace_editor": "Edit",
    "apply_patch": "Edit",
    "multiedit": "Edit",
    # File writes
    "write": "Write",
    "create_file": "Write",
    # Search
    "grep": "Grep",
    "search": "Grep",
    "ripgrep": "Grep",
    "glob": "Glob",
    "find": "Glob",
    # Web
    "webfetch": "WebFetch",
    "fetch": "WebFetch",
    "websearch": "WebSearch",
    # Agentic
    "task": "Task",
    "agent": "Task",
    "todowrite": "TodoWrite",
    "todoread": "TodoRead",
    "exitplanmode": "ExitPlanMode",
    # Notebooks
    "notebookedit": "NotebookEdit",
}


def normalize_tool(name: str) -> str:
    """Return the canonical label for *name*.

    Falls through to the original name for unknown tools so detectors
    can still group by raw label and so MCP tools (``mcp__server__op``)
    keep their server identifier intact.
    """
    if not name:
        return name
    lowered = name.lower()
    if lowered.startswith("mcp__"):
        return "MCP"
    return CANONICAL_TOOLS.get(lowered, name)


@dataclass(frozen=True, slots=True)
class ModelAlias:
    """One alias entry: deployment-facing id → canonical model id.

    ``family`` is denormalised so a comparison or KPI step can group by
    family without re-deriving it from the canonical id; we already
    know it at registration time.
    """

    alias: str
    canonical: str
    family: str


# Pre-seeded with proxy-style aliases that show up in real deployments.
# Callers extend this map with their own deployment names — the
# resolver is order-independent so additions never collide with the
# defaults.
MODEL_ALIASES: Final[dict[str, ModelAlias]] = {
    "my-proxy-opus": ModelAlias("my-proxy-opus", "claude-opus-4-7", "claude"),
    "my-proxy-sonnet": ModelAlias("my-proxy-sonnet", "claude-sonnet-4-6", "claude"),
    "my-proxy-haiku": ModelAlias("my-proxy-haiku", "claude-haiku-4-5", "claude"),
}


def resolve_model(model_id: str, aliases: Mapping[str, ModelAlias] | None = None) -> str:
    """Return the canonical model id for *model_id*.

    Args:
        model_id: Raw identifier (possibly a proxy alias) from a
            session line.
        aliases: Optional override of the default alias map. Keys are
            the alias strings; values are :class:`ModelAlias` records.
    """
    if not model_id:
        return model_id
    table = aliases if aliases is not None else MODEL_ALIASES
    entry = table.get(model_id)
    if entry is None:
        return model_id
    return entry.canonical
