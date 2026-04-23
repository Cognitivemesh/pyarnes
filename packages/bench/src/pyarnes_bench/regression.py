"""Cross-version regression tracking for eval suites."""

from __future__ import annotations

from dataclasses import dataclass

from pyarnes_bench.eval import EvalSuite

__all__ = ["RegressionReport"]


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """Compare harness pass rates across two evaluation runs.

    Scenario comparison is set-based — duplicate scenario IDs within a
    suite collapse silently. Enforce unique IDs upstream (in
    ``EvalSuite.add`` or in the test harness) if scenario-level diffs
    must be exact.

    Attributes:
        baseline_suite: The reference evaluation run.
        current_suite: The candidate evaluation run being compared.
        baseline_version: Label for the baseline (e.g. ``"v0.1.0"``).
        harness_version: Label for the current run (e.g. ``"v0.2.0"``).
    """

    baseline_suite: EvalSuite
    current_suite: EvalSuite
    baseline_version: str
    harness_version: str

    def _passed_sets(self) -> tuple[set[str], set[str]]:
        """Return (baseline_passed, current_passed) scenario ID sets."""
        return (
            {r.scenario for r in self.baseline_suite.results if r.passed},
            {r.scenario for r in self.current_suite.results if r.passed},
        )

    @property
    def regressions(self) -> list[str]:
        """Scenario IDs that passed in the baseline but fail now."""
        baseline_passed, current_passed = self._passed_sets()
        return sorted(baseline_passed - current_passed)

    @property
    def improvements(self) -> list[str]:
        """Scenario IDs that failed in the baseline but pass now."""
        baseline_passed, current_passed = self._passed_sets()
        return sorted(current_passed - baseline_passed)

    @property
    def score_delta(self) -> float:
        """Change in average score (current - baseline)."""
        return self.current_suite.average_score - self.baseline_suite.average_score

    def to_markdown(self) -> str:
        """Render a markdown report suitable for CI comments or PR descriptions."""
        b, c = self.baseline_suite, self.current_suite
        reg_lines = "\n".join(f"- {s}" for s in self.regressions) or "None"
        imp_lines = "\n".join(f"- {s}" for s in self.improvements) or "None"
        return (
            f"# Regression Report: {self.baseline_version} → {self.harness_version}\n\n"
            f"| Metric | Baseline | Current | Delta |\n"
            f"|--------|----------|---------|-------|\n"
            f"| Pass rate | {b.pass_rate:.2%} | {c.pass_rate:.2%}"
            f" | {c.pass_rate - b.pass_rate:+.2%} |\n"
            f"| Avg score | {b.average_score:.3f} | {c.average_score:.3f}"
            f" | {self.score_delta:+.3f} |\n\n"
            f"## Regressions ({len(self.regressions)})\n{reg_lines}\n\n"
            f"## Improvements ({len(self.improvements)})\n{imp_lines}\n"
        )
