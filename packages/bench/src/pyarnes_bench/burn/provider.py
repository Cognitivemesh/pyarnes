"""Provider ABC hierarchy and BurnTracker orchestrator.

Three-level hierarchy rationale:

- ``Provider`` (root ABC): decouples storage format from BurnTracker.
  Alternative (single class with format flag) would require modifying
  existing code to add each new format — violates open/closed.

- ``JsonlProvider`` (intermediate ABC): owns all JSONL parsing logic so
  it is not duplicated across providers. Alternative considered: mixin —
  rejected because Python MRO complexity outweighs the benefit at this
  scale.

- ``BurnTracker``: separate from Provider because providers are stateless
  file parsers; the tracker owns session caching and orchestration.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import replace
from decimal import Decimal
from functools import reduce
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyarnes_bench.burn.types import Cost, SessionBurn, SessionMetadata, TokenUsage

if TYPE_CHECKING:
    from pyarnes_bench.burn.costing import CostCalculator

__all__ = [
    "BurnTracker",
    "JsonlProvider",
    "Provider",
]


class Provider(ABC):
    """Root abstract contract for any AI coding session source.

    Subclass directly for non-JSONL storage (e.g. SQLite for Cursor).
    Subclass ``JsonlProvider`` for any JSONL-based tool.
    """

    @property
    @abstractmethod
    def tool_name(self) -> str:
        """Short coding-tool identifier, e.g. 'cursor'."""

    @property
    @abstractmethod
    def ai_provider_name(self) -> str:
        """Short API-provider identifier, e.g. 'openai'."""

    @abstractmethod
    def discover_sessions(self, base: Path) -> list[Path]:
        """Return all session file paths under ``base``.

        Args:
            base: Root directory to search.

        Returns:
            Sorted list of file paths, one per session.
        """

    @abstractmethod
    def parse_session(self, path: Path) -> SessionBurn | None:
        """Parse one session file into a ``SessionBurn``.

        Args:
            path: Path to a single session file.

        Returns:
            A populated ``SessionBurn``, or ``None`` if the file is
            empty, unreadable, or contains no model turns.
        """

    def burn_report(self, base: Path) -> list[SessionBurn]:
        """Template method: discover → parse → drop None.

        Args:
            base: Root directory passed to ``discover_sessions``.
        """
        return [burn for path in self.discover_sessions(base) if (burn := self.parse_session(path)) is not None]


class JsonlProvider(Provider, ABC):
    """Intermediate ABC for JSONL-based session storage.

    All parsing logic (file I/O, JSON decoding, accumulation, and
    ``SessionBurn`` construction) lives here. Subclasses implement only
    the six field-mapping hooks below.

    Invariant: any parsing logic in a subclass is a duplication bug.
    """

    @property
    @abstractmethod
    def session_glob(self) -> str:
        """Glob relative to ``base``, e.g. ``'*/*.jsonl'``."""

    @abstractmethod
    def is_model_turn(self, entry: dict[str, Any]) -> bool:
        """Return ``True`` if this JSONL entry is a model response."""

    @abstractmethod
    def extract_usage(self, entry: dict[str, Any]) -> TokenUsage | None:
        """Map entry fields → ``TokenUsage``; ``None`` if usage is absent."""

    @abstractmethod
    def extract_model_id(self, entry: dict[str, Any]) -> str:
        """Extract the model identifier string from this entry."""

    @abstractmethod
    def extract_timestamp(self, entry: dict[str, Any]) -> str | None:
        """Extract an ISO-8601 timestamp, or ``None`` if absent."""

    @abstractmethod
    def infer_model_family(self, model_id: str) -> str:
        """Derive a family name from a model identifier string."""

    # ── Concrete — do not override in subclasses ──────────────────────

    def discover_sessions(self, base: Path) -> list[Path]:
        """Return all session file paths under base matching session_glob."""
        return sorted(base.glob(self.session_glob))

    def parse_session(self, path: Path) -> SessionBurn | None:
        """Read ``path``, aggregate model turns into a ``SessionBurn``.

        Returns:
            A ``SessionBurn`` when at least one model turn is found;
            ``None`` for empty, unreadable, or turn-free files.
        """
        project = path.parent.name
        turns: list[tuple[str | None, TokenUsage, str]] = []

        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not self.is_model_turn(entry):
                continue
            usage = self.extract_usage(entry)
            if usage is None:
                continue
            turns.append(
                (
                    self.extract_timestamp(entry),
                    usage,
                    self.extract_model_id(entry),
                )
            )

        if not turns:
            return None

        timestamps = [t for t, _, _ in turns if t]
        total_usage: TokenUsage = reduce(lambda a, b: a + b, (u for _, u, _ in turns))
        model_id = next((m for _, _, m in reversed(turns) if m), "")

        return SessionBurn(
            session_id=path.stem,
            project=project,
            metadata=SessionMetadata(
                tool=self.tool_name,
                ai_provider=self.ai_provider_name,
                model_id=model_id,
                model_family=self.infer_model_family(model_id),
            ),
            start_time=min(timestamps) if timestamps else "",
            end_time=max(timestamps) if timestamps else "",
            turns=len(turns),
            usage=total_usage,
        )


class BurnTracker:
    """Orchestrates providers; single entry point for all token audits.

    Providers are stateless file parsers. BurnTracker owns the session
    cache and cost attachment. Results are cached after the first
    ``report()`` call; create a new instance to re-read from disk.

    Usage::

        tracker = BurnTracker(
            SomeProvider(),
            calculator=SomeCostCalculator(currency="EUR"),
        )
        report = tracker.report()
        usage = tracker.total_usage()
        cost = tracker.total_cost()
    """

    def __init__(
        self,
        *providers: Provider,
        calculator: CostCalculator | None = None,
    ) -> None:
        """Initialise with one or more providers and an optional cost calculator."""
        self._providers = providers
        self._calculator = calculator
        self._cache: dict[str, list[SessionBurn]] | None = None

    def report(self, base: Path | None = None) -> dict[str, list[SessionBurn]]:
        """Run all providers; results keyed by ``provider.tool_name``.

        Args:
            base: Override the default discovery base for all providers.
                  Each provider uses its own ``DEFAULT_BASE`` when ``None``.
        """
        if self._cache is not None:
            return self._cache

        result: dict[str, list[SessionBurn]] = {}
        for provider in self._providers:
            effective_base = base or getattr(provider, "DEFAULT_BASE", Path.home())
            sessions = provider.burn_report(effective_base)
            if self._calculator is not None:
                sessions = [_attach_cost(s, self._calculator) for s in sessions]
            result[provider.tool_name] = sessions

        self._cache = result
        return result

    def total_usage(self, tool: str | None = None) -> TokenUsage:
        """Sum ``TokenUsage`` across all providers (or one named tool).

        Args:
            tool: Filter by ``tool_name``; ``None`` means all providers.

        Returns:
            Accumulated ``TokenUsage``, or an all-zero instance when
            no sessions exist.
        """
        rep = self.report()
        usages = [s.usage for t, sessions in rep.items() if tool is None or t == tool for s in sessions]
        if not usages:
            return TokenUsage()
        return reduce(lambda a, b: a + b, usages)

    def total_cost(self, tool: str | None = None) -> Cost | None:
        """Sum ``Cost`` across all providers (or one named tool).

        Args:
            tool: Filter by ``tool_name``; ``None`` means all providers.

        Returns:
            Summed ``Cost``, or ``None`` when no calculator was supplied,
            no sessions have costs, or sessions span mixed currencies
            (mixed-currency summation would be misleading).
        """
        rep = self.report()
        costs = [
            s.cost for t, sessions in rep.items() if tool is None or t == tool for s in sessions if s.cost is not None
        ]
        if not costs:
            return None

        currencies = {c.currency for c in costs}
        if len(currencies) != 1:
            # Mixed currencies: return None rather than silently combining
            return None

        total = sum((c.amount for c in costs), Decimal(0))
        return Cost(amount=total, currency=costs[0].currency)


def _attach_cost(session: SessionBurn, calculator: CostCalculator) -> SessionBurn:
    """Return a new ``SessionBurn`` with the ``cost`` field populated."""
    cost = calculator.calculate(session.metadata.model_id, session.usage)
    return replace(session, cost=cost)
