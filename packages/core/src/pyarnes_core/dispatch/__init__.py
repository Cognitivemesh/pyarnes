"""Dispatch domain — LLM action routing to tool calls.

Flat-layout convention: layer designations live in module docstrings.

* Atoms: ``action_kind``, ``retry_policy``.
* Port: ``ports.ToolHandler`` / ``ports.ModelClient``.

No asyncio scheduling lives here — that's the ``AgentLoop`` system in
``pyarnes_harness``.
"""

from __future__ import annotations

from pyarnes_core.dispatch.action_kind import ActionKind, classify
from pyarnes_core.dispatch.retry_policy import (
    RetryPolicy,
    merge_retry_caps,
    next_delay,
)

__all__ = [
    "ActionKind",
    "RetryPolicy",
    "classify",
    "merge_retry_caps",
    "next_delay",
]
