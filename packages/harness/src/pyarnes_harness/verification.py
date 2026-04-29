"""Sequential quality-gate pipeline that verifies agent output before acceptance.

The pipeline enforces a fixed stage order — GENERATE → GUARDRAIL_CHECK → TEST →
BENCHMARK — so callers get a deterministic, auditable quality guarantee.  Any
gate failure triggers a fix cycle (the caller's ``generate`` callable is
responsible for producing a different result on retry).  If all fix attempts
are exhausted the loop escalates via ``UserFixableError``.

Key design choices
------------------
* **Immutable result** — ``VerificationResult`` is a frozen dataclass so the
  caller can safely pass it around without defensive copies.
* **Guardrail short-circuit** — ``UserFixableError`` from the guardrail chain
  propagates immediately (no retry) because it signals a human-fixable
  policy violation, not a quality issue that generate can resolve.
* **Score is only set on success** — ``VerificationResult.score`` reflects
  the benchmark score of the *accepted* output, not the last attempted score.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pyarnes_core.errors import LLMRecoverableError, UserFixableError
from pyarnes_core.observability import log_event, log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_guardrails.guardrails import GuardrailChain

__all__ = [
    "VerificationLoop",
    "VerificationResult",
]

logger = get_logger(__name__)


# ── Result ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The outcome of a completed verification loop.

    Attributes:
        output: The generated output that passed all quality gates.
        passed: ``True`` when every enabled gate accepted the output.
        fix_attempts: Number of fix/generate cycles that ran.  ``0`` means
            the first generated output passed every gate without a retry.
        score: Benchmark score of the accepted output, or ``0.0`` if no
            benchmark callable was provided.
    """

    output: Any
    passed: bool
    fix_attempts: int
    score: float


# ── Loop ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class VerificationLoop:
    """Sequential quality-gate pipeline for verifying agent-generated outputs.

    Stages run in order: GENERATE → GUARDRAIL_CHECK → TEST → BENCHMARK.
    On any gate failure the loop increments ``fix_attempts`` and returns to
    GENERATE, up to ``max_fix_attempts`` times.  When the budget is exhausted
    the loop escalates by raising ``UserFixableError``.

    Attributes:
        guardrail_chain: Optional chain of safety guardrails.  When ``None``
            the GUARDRAIL_CHECK stage is skipped entirely.  Concrete guardrails
            that scan specific argument keys (``PathGuardrail``,
            ``CommandGuardrail``) will be no-ops here because the check is
            called with ``{"output": str(output)}``.  Use ``SemanticGuardrail``
            or a custom ``AsyncGuardrail`` subclass to enforce output-level
            policies.
        max_fix_attempts: Maximum number of fix/generate cycles before
            escalation.  Default is ``3`` (four total generate calls).
    """

    guardrail_chain: GuardrailChain | None = None
    max_fix_attempts: int = 3

    async def run(
        self,
        task: str,
        generate: Callable[[], Awaitable[Any]],
        test: Callable[[Any], Awaitable[bool]],
        benchmark: Callable[[Any], Awaitable[float]] | None = None,
        benchmark_threshold: float = 0.0,
    ) -> VerificationResult:
        """Drive output through all quality gates and return a verification result.

        Args:
            task: Human-readable description of the task being verified.
                Used in escalation messages and log events.
            generate: Async callable that produces candidate output.  On retry
                cycles the callable is invoked again; it is the caller's
                responsibility to produce a different result on each call.
            test: Async callable that receives the candidate output and returns
                ``True`` if it is correct, ``False`` otherwise.
            benchmark: Optional async callable that scores the output as a
                float.  When provided, the score must reach
                ``benchmark_threshold`` to pass.
            benchmark_threshold: Minimum acceptable benchmark score.
                Ignored when ``benchmark`` is ``None``.

        Returns:
            A :class:`VerificationResult` describing the accepted output.

        Raises:
            UserFixableError: When a guardrail raises ``UserFixableError``
                (propagated immediately), or when all fix attempts are
                exhausted without passing every gate.

        Note:
            ``generate``, ``test``, and ``benchmark`` callables must handle
            ``LLMRecoverableError`` and ``TransientError`` internally — the
            pipeline does not wrap callable invocations in the error taxonomy.
            Unhandled exceptions propagate directly to the caller.
        """
        log_event(logger, "verification.start", task=task, max_fix_attempts=self.max_fix_attempts)
        fix_attempts = 0
        last_reason = ""

        while True:
            result, last_reason = await self._attempt(generate, test, benchmark, benchmark_threshold, fix_attempts)
            if result is not None:
                log_event(
                    logger,
                    "verification.passed",
                    task=task,
                    fix_attempts=fix_attempts,
                    score=result.score,
                )
                return result

            # Gate failed — decide whether to fix or escalate.
            fix_attempts += 1
            if fix_attempts > self.max_fix_attempts:
                self._escalate(task, fix_attempts, last_reason)
            log_event(logger, "verification.fix", fix_attempts=fix_attempts, reason=last_reason)

    def _escalate(self, task: str, fix_attempts: int, reason: str) -> None:
        """Log and raise ``UserFixableError`` after all fix attempts are exhausted.

        Args:
            task: Task description for the error message.
            fix_attempts: Total number of fix cycles that ran.
            reason: Human-readable description of the last failure.

        Raises:
            UserFixableError: Always.
        """
        log_warning(
            logger,
            "verification.escalated",
            task=task,
            fix_attempts=fix_attempts,
            reason=reason,
        )
        raise UserFixableError(
            message=(f"Verification failed for task {task!r} after {fix_attempts} fix attempt(s): {reason}"),
            prompt_hint=(f"Review and fix the output for task {task!r}. Reason: {reason}"),
        )

    async def _attempt(
        self,
        generate: Callable[[], Awaitable[Any]],
        test: Callable[[Any], Awaitable[bool]],
        benchmark: Callable[[Any], Awaitable[float]] | None,
        benchmark_threshold: float,
        fix_attempts: int,
    ) -> tuple[VerificationResult | None, str]:
        """Run one generate-check-test-benchmark cycle.

        Returns:
            ``(VerificationResult, "")`` on success, or ``(None, reason)`` on
            any gate failure.  ``UserFixableError`` from the guardrail chain
            propagates immediately.
        """
        log_event(logger, "verification.generate", fix_attempts=fix_attempts)
        output = await generate()

        # GUARDRAIL_CHECK
        failure = await self._check_guardrail(output)
        if failure:
            return None, failure

        # TEST
        passed = await test(output)
        if not passed:
            log_warning(logger, "verification.test_failed", fix_attempts=fix_attempts)
            return None, "test returned False"

        # BENCHMARK
        score, failure = await self._check_benchmark(output, benchmark, benchmark_threshold, fix_attempts)
        if failure:
            return None, failure

        return VerificationResult(output=output, passed=True, fix_attempts=fix_attempts, score=score), ""

    async def _check_guardrail(self, output: Any) -> str:
        """Check the guardrail chain; return a failure reason or empty string.

        Raises:
            UserFixableError: Immediately when the chain raises one.
        """
        if self.guardrail_chain is None:
            return ""
        try:
            await self.guardrail_chain.check("verification", {"output": str(output)})
        except UserFixableError:
            log_warning(logger, "verification.guardrail_user_fixable")
            raise
        except LLMRecoverableError:
            log_warning(logger, "verification.guardrail_blocked")
            return "guardrail blocked output"
        return ""

    @staticmethod
    async def _check_benchmark(
        output: Any,
        benchmark: Callable[[Any], Awaitable[float]] | None,
        threshold: float,
        fix_attempts: int,
    ) -> tuple[float, str]:
        """Evaluate the optional benchmark; return ``(score, failure_reason)``.

        Returns:
            ``(score, "")`` on pass or when no benchmark is supplied.
            ``(score, reason)`` when score is below threshold.
        """
        if benchmark is None:
            return 0.0, ""
        score = await benchmark(output)
        if score < threshold:
            log_warning(
                logger,
                "verification.benchmark_below_threshold",
                score=score,
                threshold=threshold,
                fix_attempts=fix_attempts,
            )
            return score, f"benchmark score {score} below threshold {threshold}"
        return score, ""
