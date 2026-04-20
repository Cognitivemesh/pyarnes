"""Safety domain — guardrail primitives (pure, no I/O).

Flat-layout convention: files named after their concept live directly
in this package. The composability layer (atom vs molecule) is stated
in each module's docstring rather than in the folder tree.

* Atoms: ``path_canon``, ``path_parts``, ``arg_walker``.
* Molecules: ``sandbox_check``, ``command_scan``.
* Port: ``ports.GuardrailPort``.
"""

from __future__ import annotations

from pyarnes_core.safety.arg_walker import walk_strings, walk_values_for_keys
from pyarnes_core.safety.command_scan import scan_for_patterns
from pyarnes_core.safety.path_canon import canonicalize, has_traversal
from pyarnes_core.safety.path_parts import is_within_roots
from pyarnes_core.safety.sandbox_check import assert_within_roots

__all__ = [
    "assert_within_roots",
    "canonicalize",
    "has_traversal",
    "is_within_roots",
    "scan_for_patterns",
    "walk_strings",
    "walk_values_for_keys",
]
