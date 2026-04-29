"""BenchmarkGateGuardrail — gate tool execution on benchmark score.

This guardrail is intended as a post-execution check: before allowing a tool
to run (or within a ``VerificationLoop.benchmark`` callback), it invokes a
user-supplied async factory that returns a scored evaluation suite.  If the
suite's ``average_score`` falls below the configured threshold it raises
``UserFixableError``, interrupting the session for human review.

Usage::

    from pyarnes_bench.eval import EvalSuite, EvalResult
    from pyarnes_guardrails.benchmark_gate import BenchmarkGateGuardrail


    async def run_my_suite() -> EvalSuite:
        suite = EvalSuite(name="smoke")
        suite.add(EvalResult(scenario="s1", score=0.9, passed=True))
        return suite


    gate = BenchmarkGateGuardrail(suite_factory=run_my_suite, threshold=0.8)
    chain = GuardrailChain(guardrails=[gate])
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pyarnes_core.errors import UserFixableError
from pyarnes_guardrails.guardrails import AsyncGuardrail

__all__ = ["BenchmarkGateGuardrail"]


@runtime_checkable
class _HasScore(Protocol):
    """Minimal interface required from the factory return value."""

    @property
    def average_score(self) -> float: ...


@dataclass(frozen=True, slots=True)
class BenchmarkGateGuardrail(AsyncGuardrail):
    """Gate tool calls on a benchmark score threshold.

    The ``suite_factory`` is an async callable that runs evaluations and
    returns any object with an ``average_score: float`` property (e.g.
    :class:`pyarnes_bench.eval.EvalSuite`).  The factory is called each
    time ``check`` is invoked, so it should be cheap or cached externally.

    When ``gate_tools`` is empty (the default) the gate applies to every
    tool.  Pass a non-empty frozenset to restrict gating to specific tools.

    Raises:
        UserFixableError: When ``average_score < threshold``.

    Attributes:
        suite_factory: Async callable returning a scored suite object.
        threshold: Minimum acceptable ``average_score`` (inclusive).
        gate_tools: If non-empty, only gate the listed tool names.
    """

    suite_factory: Callable[[], Awaitable[Any]]
    threshold: float = 0.8
    gate_tools: frozenset[str] = field(default_factory=frozenset)

    async def check(self, tool_name: str, arguments: dict[str, Any]) -> None:  # noqa: ARG002
        """Run the suite and raise if score is below threshold.

        Args:
            tool_name: The name of the tool being invoked.
            arguments: Key-value arguments passed to the tool (unused here).
        """
        if self.gate_tools and tool_name not in self.gate_tools:
            return

        suite = await self.suite_factory()
        score: float = suite.average_score
        if score < self.threshold:
            raise UserFixableError(
                message=(
                    f"Benchmark score {score:.3f} is below threshold {self.threshold:.3f} "
                    f"for tool '{tool_name}'. Review and fix the agent before proceeding."
                ),
            )
