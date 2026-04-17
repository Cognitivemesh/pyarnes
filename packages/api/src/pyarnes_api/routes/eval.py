"""Evaluation endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from pyarnes_api.schemas import (
    EvalResultResponse,
    EvalSuiteRequest,
    EvalSuiteResponse,
)
from pyarnes_bench import EvalResult, EvalSuite, ExactMatchScorer

router = APIRouter(tags=["eval"])


@router.post(
    "/eval",
    response_model=EvalSuiteResponse,
    summary="Run an evaluation suite",
)
async def run_eval(body: EvalSuiteRequest) -> EvalSuiteResponse:
    """Score a batch of evaluation scenarios using exact-match.

    Each scenario compares ``expected`` vs ``actual`` and returns a score
    (1.0 for match, 0.0 otherwise).  The response includes per-scenario
    results and aggregate statistics.
    """
    scorer = ExactMatchScorer(case_sensitive=False)
    suite = EvalSuite(name=body.suite_name)

    results: list[EvalResultResponse] = []
    for sc in body.scenarios:
        score = scorer.score(sc.expected, sc.actual)
        passed = score >= body.pass_threshold
        suite.add(
            EvalResult(
                scenario=sc.scenario,
                expected=sc.expected,
                actual=sc.actual,
                score=score,
                passed=passed,
            )
        )
        results.append(
            EvalResultResponse(
                scenario=sc.scenario,
                expected=sc.expected,
                actual=sc.actual,
                score=score,
                passed=passed,
            )
        )

    summary = suite.summary()
    return EvalSuiteResponse(
        suite=summary["suite"],
        total=summary["total"],
        passed=summary["passed"],
        failed=summary["failed"],
        pass_rate=summary["pass_rate"],
        average_score=summary["average_score"],
        results=results,
    )
