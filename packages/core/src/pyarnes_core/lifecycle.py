"""Lifecycle management for harness sessions.

Tracks phases (INIT → RUNNING → PAUSED → COMPLETED / FAILED) and emits
structured events so every state transition is visible and debuggable.

Not safe for concurrent mutation: ``transition`` does a classic
check-then-mutate sequence. Callers are expected to own a single
``Lifecycle`` instance per session; concurrent dispatch is not part
of the current design (see the serial loop in ``pyarnes_harness.loop``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pyarnes_core.observability.molecules import log_event
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
    """

    phase: Phase = Phase.INIT
    metadata: dict[str, Any] = field(default_factory=dict)
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
