"""Safety domain — guardrail primitives (pure, no I/O).

Flat-layout convention: files named after their concept live directly
in this package. The composability layer (atom vs molecule) is stated
in each module's docstring rather than in the folder tree.

* Atoms: ``path_canon``, ``path_parts``, ``arg_walker``, ``semantic_judge``.
* Molecules: ``sandbox_check``, ``command_scan``.
* Port: ``ports.GuardrailPort``.
"""

from __future__ import annotations

from pyarnes_core.safety.arg_walker import walk_strings, walk_values_for_keys
from pyarnes_core.safety.command_scan import scan_for_patterns
from pyarnes_core.safety.injection import detect_injection, walk_for_injection
from pyarnes_core.safety.path_canon import canonicalize, has_traversal
from pyarnes_core.safety.path_parts import is_within_roots
from pyarnes_core.safety.redact import REDACTED, redact, redact_dict
from pyarnes_core.safety.sandbox_check import assert_within_roots
from pyarnes_core.safety.sanitize import sanitize_messages, sanitize_str
from pyarnes_core.safety.semantic_judge import Finding, analyse_code, scan_code_arguments

__all__ = [
    "REDACTED",
    "Finding",
    "analyse_code",
    "assert_within_roots",
    "canonicalize",
    "detect_injection",
    "has_traversal",
    "is_within_roots",
    "redact",
    "redact_dict",
    "sanitize_messages",
    "sanitize_str",
    "scan_code_arguments",
    "scan_for_patterns",
    "walk_for_injection",
    "walk_strings",
    "walk_values_for_keys",
]  # sorted: capital letters before lowercase per isort
