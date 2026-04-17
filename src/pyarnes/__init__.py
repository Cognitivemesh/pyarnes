"""Pyarnes — agentic harness engineering template.

Verification loops, safety enforcement, and lifecycle management
for AI coding tools.

This root package provides a single ``import pyarnes`` entry-point.
All real implementation lives in the workspace packages:

- ``pyarnes_core``       — types, errors, lifecycle, logging
- ``pyarnes_harness``    — agent loop, tools, capture
- ``pyarnes_guardrails`` — composable safety guardrails
- ``pyarnes_bench``      — evaluation and benchmarking
"""

from __future__ import annotations

__all__ = [
    "__version__",
]

__version__ = "0.1.0"
