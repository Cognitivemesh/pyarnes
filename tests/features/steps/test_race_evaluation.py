"""BDD step definitions for RACE evaluation scenarios."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pytest_bdd import given, scenario, then, when

from pyarnes_bench import EvalSuite, RaceDimension, RaceEvaluator
from pyarnes_core.errors import UserFixableError


@scenario("../race_evaluation.feature", "Identical target and reference yield a final score of 0.5")
def test_identical_half() -> None:
    """Identical target and reference yield a final score of 0.5."""


@scenario("../race_evaluation.feature", "Better target beats the reference")
def test_better_target() -> None:
    """Better target beats the reference."""


@scenario("../race_evaluation.feature", "Empty target is rejected")
def test_empty_target() -> None:
    """Empty target is rejected."""


class _ScriptedJudge:
    def __init__(self, score_fn: object) -> None:
        self._score_fn = score_fn

    async def judge(self, prompt: str) -> str:
        if "importance weights" in prompt:
            return json.dumps({"weights": {d.value: 0.25 for d in RaceDimension}})
        if "sub-criteria" in prompt:
            dim = next(d.value for d in RaceDimension if f'"{d.value}"' in prompt)
            return json.dumps(
                {
                    "criteria": [
                        {"dimension": dim, "text": f"{dim}_a", "weight": 0.5},
                        {"dimension": dim, "text": f"{dim}_b", "weight": 0.5},
                    ]
                }
            )
        return json.dumps({"score": self._score_fn(prompt), "reason": "ok"})


@given("a scripted judge with uniform weights and a constant score", target_fixture="race_ctx")
def _given_constant() -> dict[str, Any]:
    return {"judge": _ScriptedJudge(score_fn=lambda _p: 0.7), "result": None, "exc": None}


@given("a scripted judge that rates the target higher than the reference", target_fixture="race_ctx")
def _given_target_higher() -> dict[str, Any]:
    def scorer(prompt: str) -> float:
        return 0.9 if "MARK_TGT" in prompt else 0.2

    return {"judge": _ScriptedJudge(score_fn=scorer), "result": None, "exc": None}


@given("a scripted judge", target_fixture="race_ctx")
def _given_scripted_judge() -> dict[str, Any]:
    return {"judge": _ScriptedJudge(score_fn=lambda _p: 0.5), "result": None, "exc": None}


@when("the RACE evaluator scores an identical target and reference")
def _when_identical(race_ctx: dict[str, Any]) -> None:
    evaluator = RaceEvaluator(client=race_ctx["judge"], trials=1)
    race_ctx["result"] = asyncio.run(
        evaluator.evaluate(task_prompt="task", target_report="same", reference_report="same")
    )


@when("the RACE evaluator runs")
def _when_runs(race_ctx: dict[str, Any]) -> None:
    evaluator = RaceEvaluator(client=race_ctx["judge"], trials=1)
    race_ctx["result"] = asyncio.run(
        evaluator.evaluate(
            task_prompt="task",
            target_report="MARK_TGT body",
            reference_report="baseline body",
        )
    )


@when("the RACE evaluator is called with an empty target report")
def _when_empty_target(race_ctx: dict[str, Any]) -> None:
    evaluator = RaceEvaluator(client=race_ctx["judge"], trials=1)
    try:
        asyncio.run(evaluator.evaluate(task_prompt="task", target_report="", reference_report="r"))
    except UserFixableError as exc:
        race_ctx["exc"] = exc


@then("the final score is approximately 0.5")
def _then_half(race_ctx: dict[str, Any]) -> None:
    assert abs(race_ctx["result"].final_score - 0.5) < 1e-6


@then("the criteria weights per dimension sum to 1.0")
def _then_criteria_sum(race_ctx: dict[str, Any]) -> None:
    score = race_ctx["result"]
    for dimension in RaceDimension:
        total = sum(c.weight for c in score.criteria if c.dimension == dimension)
        assert abs(total - 1.0) < 1e-6


@then("the final score is greater than 0.5")
def _then_gt_half(race_ctx: dict[str, Any]) -> None:
    assert race_ctx["result"].final_score > 0.5


@then("the EvalSuite records the result as passed")
def _then_suite_passed(race_ctx: dict[str, Any]) -> None:
    suite = EvalSuite(name="race-bdd")
    suite.add(race_ctx["result"].to_eval_result(scenario="bdd", threshold=0.5))
    assert suite.pass_rate == 1.0


@then("a UserFixableError is raised")
def _then_user_fixable(race_ctx: dict[str, Any]) -> None:
    assert isinstance(race_ctx["exc"], UserFixableError)
