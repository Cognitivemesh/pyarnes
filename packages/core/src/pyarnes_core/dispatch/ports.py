"""Dispatch domain ports — re-export of the canonical Protocols.

``ToolHandler`` and ``ModelClient`` live in ``pyarnes_core.types`` for
backward compatibility with existing imports. This module exposes them
under the DDD path so new code can import from the domain folder:

    from pyarnes_core.dispatch.ports import ToolHandler, ModelClient
"""

from __future__ import annotations

from pyarnes_core.types import ModelClient, ToolHandler

__all__ = [
    "ModelClient",
    "ToolHandler",
]
