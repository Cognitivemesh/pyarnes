"""Catalog of ``Scorer`` implementations for agent trajectory grading.

Each scorer consumes the same ``Iterable[ToolCallEntry]`` shape that
``pyarnes_harness.ToolCallLogger`` emits (and that
``pyarnes_harness.read_cc_session`` materialises from a Claude Code
transcript) — so a single scorer instance can grade runs coming from
the in-process ``AgentLoop``, from Claude Code, or from any other CLI
whose hooks persist ``ToolCallEntry`` records.

All three scorers satisfy the :class:`Scorer` protocol — ``score`` takes
the *expected* (reference / rubric) and *actual* (observed trajectory)
and returns a float in ``[0.0, 1.0]``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyarnes_bench.scorer import Scorer
from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = [
    "GuardrailComplianceScorer",
    "ToolUseCorrectnessScorer",
    "TrajectoryLengthScorer",
]


@dataclass(frozen=True, slots=True)
class ToolUseCorrectnessScorer(Scorer):
    """Compare the observed tool sequence against an expected sequence.

    ``expected`` is a sequence of tool names (``["Read", "Bash", "Write"]``)
    and ``actual`` is an iterable of :class:`ToolCallEntry`. The score is
    the longest-common-subsequence ratio, so the scorer tolerates extra
    tool calls and out-of-order steps without collapsing to zero.

    Attributes:
        ignore_errors: When ``True`` (the default), tool calls flagged
            ``is_error`` are skipped before comparison — a failed
            attempt does not count as a step towards the rubric.
    """

    ignore_errors: bool = True

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Score the trajectory by longest-common-subsequence ratio.

        Compares *expected* tool-name sequence against the tool names
        extracted from *actual* (:class:`ToolCallEntry` iterable).
        """
        del scenario, metadata
        expected_seq = _as_name_tuple(expected)
        observed_seq = tuple(
            entry.tool for entry in _iter_entries(actual) if not (self.ignore_errors and entry.is_error)
        )
        if not expected_seq:
            return 1.0 if not observed_seq else 0.0
        return _lcs_len(expected_seq, observed_seq) / len(expected_seq)


@dataclass(frozen=True, slots=True)
class TrajectoryLengthScorer(Scorer):
    """Penalise trajectories that run past the budgeted length.

    Attributes:
        target_length: Expected number of successful tool calls for this
            scenario. Overridden by ``expected`` when a scenario passes
            an int / tuple explicitly.
        tolerance: Half-width of the no-penalty window around
            ``target_length``. Calls inside the window score 1.0.
    """

    target_length: int = 10
    tolerance: int = 2

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Return 1.0 when the trajectory length is within tolerance.

        Longer trajectories decay linearly to 0.0 once they pass
        ``target + tolerance`` by the same number of calls again
        (i.e. 2x the tolerance band). Shorter trajectories decay the
        same way.
        """
        del scenario, metadata
        target = _target_length_from(expected, self.target_length)
        observed = sum(1 for entry in _iter_entries(actual) if not entry.is_error)
        delta = abs(observed - target)
        if delta <= self.tolerance:
            return 1.0
        excess = delta - self.tolerance
        window = max(self.tolerance, 1)
        return max(0.0, 1.0 - excess / window)


@dataclass(frozen=True, slots=True)
class GuardrailComplianceScorer(Scorer):
    """Score a session by the ratio of clean tool calls to blocked ones.

    *expected* is the path to the sidecar violation log
    (``.claude/pyarnes/violations.jsonl`` by default); *actual* is the
    iterable of :class:`ToolCallEntry` objects (from
    :func:`~pyarnes_harness.read_cc_session` or ``ToolCallLogger``).

    Returns ``1.0`` when the call count is zero and the log is absent or
    empty — no-op sessions are trivially compliant. Otherwise returns
    ``max(0, 1 - violations / calls)``.

    Attributes:
        session_id: When set, only violations whose ``session_id`` field
            matches are counted. Useful when multiple sessions share one
            log file.
    """

    session_id: str | None = None

    def score(
        self,
        expected: Any,
        actual: Any,
        *,
        scenario: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Return the compliance ratio (1.0 = clean, 0.0 = all-blocked)."""
        del scenario, metadata
        calls = sum(1 for _ in _iter_entries(actual))
        violations = self._count_violations(expected)
        if calls == 0:
            return 1.0
        return max(0.0, 1.0 - violations / calls)

    def _count_violations(self, log_path: Any) -> int:
        """Count matching records in the violation log at *log_path*."""
        if log_path is None:
            return 0
        path = Path(log_path)
        if not path.is_file():
            return 0
        count = 0
        for raw in path.read_text().splitlines():
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if self.session_id is not None and record.get("session_id") != self.session_id:
                continue
            count += 1
        return count


# ── helpers ────────────────────────────────────────────────────────────────


def _iter_entries(value: Any) -> Iterable[ToolCallEntry]:
    """Yield every :class:`ToolCallEntry` in *value*; tolerate None."""
    if value is None:
        return
    for item in value:
        if isinstance(item, ToolCallEntry):
            yield item


def _as_name_tuple(expected: Any) -> tuple[str, ...]:
    """Normalise *expected* to a tuple of tool-name strings."""
    if expected is None:
        return ()
    if isinstance(expected, str):
        return (expected,)
    if isinstance(expected, Sequence):
        return tuple(str(item) for item in expected)
    return ()


def _target_length_from(expected: Any, fallback: int) -> int:
    """Extract the target length for TrajectoryLengthScorer."""
    if isinstance(expected, bool):
        return fallback
    if isinstance(expected, int):
        return expected
    if isinstance(expected, Sequence) and not isinstance(expected, str):
        return len(expected)
    return fallback


def _lcs_len(a: Sequence[str], b: Sequence[str]) -> int:
    """Longest common subsequence length — O(m*n) classic DP."""
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            if a[i] == b[j]:
                dp[i + 1][j + 1] = dp[i][j] + 1
            else:
                dp[i + 1][j + 1] = max(dp[i][j + 1], dp[i + 1][j])
    return dp[m][n]
