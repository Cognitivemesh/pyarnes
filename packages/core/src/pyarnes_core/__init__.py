"""pyarnes-core — foundational types, errors, lifecycle, and logging.

This package contains the core abstractions that all other pyarnes
packages depend on:

* **types** — ``ToolHandler`` and ``ModelClient`` ABCs.
* **errors** — four-error taxonomy (transient, LLM-recoverable, user-fixable, unexpected).
* **lifecycle** — ``Phase`` / ``Lifecycle`` finite-state machine.
* **observe** — structured JSONL logging via loguru.
"""

from __future__ import annotations

from pyarnes_core.atomic_write import append_private, write_private
from pyarnes_core.budget import Budget
from pyarnes_core.errors import (
    HarnessError,
    LLMRecoverableError,
    Severity,
    TransientError,
    UnexpectedError,
    UserFixableError,
)
from pyarnes_core.lifecycle import Lifecycle, Phase
from pyarnes_core.observe.logger import LogFormat, configure_logging, get_logger
from pyarnes_core.session_id import safe_session_id
from pyarnes_core.types import ModelClient, ToolHandler

__all__ = [
    "Budget",
    "HarnessError",
    "LLMRecoverableError",
    "Lifecycle",
    "LogFormat",
    "ModelClient",
    "Phase",
    "Severity",
    "ToolHandler",
    "TransientError",
    "UnexpectedError",
    "UserFixableError",
    "append_private",
    "configure_logging",
    "get_logger",
    "safe_session_id",
    "write_private",
]

from pyarnes_core.packaging import version_of

__version__ = version_of("pyarnes-core")
