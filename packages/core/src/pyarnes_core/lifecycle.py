"""Lifecycle management for harness sessions.

Tracks phases (INIT → RUNNING → PAUSED → COMPLETED / FAILED) and emits
structured events so every state transition is visible and debuggable.

Not safe for concurrent mutation: ``transition`` does a classic
check-then-mutate sequence. Callers are expected to own a single
``Lifecycle`` instance per session; concurrent dispatch is not part
of the current design (see the serial loop in ``pyarnes_harness.loop``).

A ``Lifecycle`` can persist to disk via :meth:`dump` / :meth:`load` so
a Claude Code ``SessionEnd`` hook can write the final state and the
next ``SessionStart`` can restore it — the only mechanism Claude Code
offers for session-to-session continuity.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pyarnes_core.budget import Budget
from pyarnes_core.observability import log_event
from pyarnes_core.observe.logger import get_logger

__all__ = [
    "Lifecycle",
    "Phase",
]

logger = get_logger(__name__)


class Phase(Enum):
    """Harness session phases.

    The lifecycle follows a strict state machine:

    * ``INIT``      → ``RUNNING``, ``FAILED``
    * ``RUNNING``   → ``PAUSED``, ``COMPLETED``, ``FAILED``
    * ``PAUSED``    → ``RUNNING``, ``FAILED``
    * ``COMPLETED`` → (terminal)
    * ``FAILED``    → (terminal)
    """

    INIT = "init"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.INIT: frozenset({Phase.RUNNING, Phase.FAILED}),
    Phase.RUNNING: frozenset({Phase.PAUSED, Phase.COMPLETED, Phase.FAILED}),
    Phase.PAUSED: frozenset({Phase.RUNNING, Phase.FAILED}),
    Phase.COMPLETED: frozenset(),
    Phase.FAILED: frozenset(),
}

_TERMINAL_PHASES: frozenset[Phase] = frozenset({Phase.COMPLETED, Phase.FAILED})


@dataclass(slots=True)
class Lifecycle:
    """Finite-state machine for a harness session.

    Attributes:
        phase: Current lifecycle phase.
        metadata: Arbitrary key-value pairs attached to the session.
        budget: Optional :class:`Budget` attached so it is persisted
            alongside the phase when :meth:`dump` is called.
    """

    phase: Phase = Phase.INIT
    metadata: dict[str, Any] = field(default_factory=dict)
    budget: Budget | None = None
    _history: list[dict[str, Any]] = field(default_factory=list, repr=False)

    # ── transitions ────────────────────────────────────────────────────

    def transition(self, target: Phase) -> None:
        """Move to *target* phase if the transition is valid.

        Args:
            target: The desired next phase.

        Raises:
            ValueError: If the transition from the current phase is not allowed.
        """
        if target not in _VALID_TRANSITIONS[self.phase]:
            msg = f"Invalid transition: {self.phase.value} → {target.value}"
            raise ValueError(msg)

        previous = self.phase
        self.phase = target
        event: dict[str, Any] = {
            "from": previous.value,
            "to": target.value,
            "timestamp": time.time(),
        }
        self._history.append(event)
        log_event(
            logger,
            "lifecycle.transition",
            from_phase=event["from"],
            to_phase=event["to"],
        )

    def start(self) -> None:
        """Transition to RUNNING."""
        self.transition(Phase.RUNNING)

    def pause(self) -> None:
        """Transition to PAUSED."""
        self.transition(Phase.PAUSED)

    def resume(self) -> None:
        """Transition from PAUSED back to RUNNING."""
        self.transition(Phase.RUNNING)

    def complete(self) -> None:
        """Transition to COMPLETED."""
        self.transition(Phase.COMPLETED)

    def fail(self) -> None:
        """Transition to FAILED."""
        self.transition(Phase.FAILED)

    # ── introspection ──────────────────────────────────────────────────

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return a copy of the transition history."""
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        """Check whether the lifecycle has reached a terminal phase."""
        return self.phase in _TERMINAL_PHASES

    # ── persistence ────────────────────────────────────────────────────

    def dump(self, path: Path) -> Path:
        """Serialise the lifecycle to *path* (JSON) and return the path.

        The transition history is NOT persisted — it is a debug aid for
        the current process. Restored instances start with an empty
        history.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "phase": self.phase.value,
            "metadata": self.metadata,
            "budget": self.budget.as_dict() if self.budget is not None else None,
        }
        path.write_text(json.dumps(payload))
        return path

    @classmethod
    def load(cls, path: Path) -> Lifecycle:
        """Inverse of :meth:`dump`."""
        raw = json.loads(path.read_text())
        budget_raw = raw.get("budget")
        budget = Budget.from_dict(budget_raw) if budget_raw is not None else None
        return cls(
            phase=Phase(raw.get("phase", Phase.INIT.value)),
            metadata=dict(raw.get("metadata", {})),
            budget=budget,
        )
