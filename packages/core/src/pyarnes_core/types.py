"""Shared Protocol re-exports — backward-compatible surface.

The canonical definitions for ``ToolHandler`` and ``ModelClient``
live in ``pyarnes_core.dispatch.ports``. This module preserves the
historical import path ``from pyarnes_core.types import ToolHandler``.
"""

from __future__ import annotations

from pyarnes_core.dispatch.ports import ModelClient, ToolHandler

__all__ = [
    "ModelClient",
    "ToolHandler",
]
