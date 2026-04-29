"""Observability domain — structured event recording primitives.

Flat-layout convention: the composability layer is documented in each
module's docstring.

* Atoms: ``clock``, ``jsonable``.
* Molecule: ``bound_logger``.
* Port: ``ports.LoggerPort``.
"""

from __future__ import annotations

from pyarnes_core.observability.bound_logger import log_error, log_event, log_warning
from pyarnes_core.observability.clock import iso_now, monotonic_duration, start_timer
from pyarnes_core.observability.events import (
    log_guardrail_violation,
    log_lifecycle_transition,
    log_tool_call,
)
from pyarnes_core.observability.jsonable import dumps, to_jsonable
from pyarnes_core.observability.tokens import estimate_tokens

__all__ = [
    "dumps",
    "estimate_tokens",
    "iso_now",
    "log_error",
    "log_event",
    "log_guardrail_violation",
    "log_lifecycle_transition",
    "log_tool_call",
    "log_warning",
    "monotonic_duration",
    "start_timer",
    "to_jsonable",
]
