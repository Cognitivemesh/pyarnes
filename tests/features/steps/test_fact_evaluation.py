"""BDD step definitions for FACT evaluation scenarios."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pytest_bdd import given, scenario, then, when

from pyarnes_bench import FactEvaluator
from pyarnes_core.errors import UserFixableError


@scenario("../fact_evaluation.feature", "All claims supported yields accuracy 1.0")
def test_all_supported() -> None:
    """All claims supported yields accuracy 1.0."""


@scenario("../fact_evaluation.feature", "Missing source is excluded from the accuracy denominator")
def test_missing_source() -> None:
    """Missing source is excluded from the accuracy denominator."""


@scenario("../fact_evaluation.feature", "Empty report is rejected")
def test_empty_report() -> None:
    """Empty report is rejected."""


class _ScriptedFactJudge:
    def __init__(self, *, claims: list[tuple[str, str]], supported: bool = True) -> None:
        self._claims = claims
        self._supported = supported

    async def judge(self, prompt: str) -> str:
        if "Extract every cited claim" in prompt:
            return json.dumps({"claims": [{"statement": s, "url": u} for s, u in self._claims]})
        return json.dumps({"supported": self._supported, "reason": "ok"})


@given("a scripted FACT judge that supports every claim", target_fixture="fact_ctx")
def _given_all_supported() -> dict[str, Any]:
    judge = _ScriptedFactJudge(
        claims=[("A", "https://x.org/a"), ("B", "https://x.org/b")],
        supported=True,
    )
    return {"judge": judge, "sources": None, "result": None, "exc": None}


@given("a scripted FACT judge that extracts two claims", target_fixture="fact_ctx")
def _given_two_claims() -> dict[str, Any]:
    judge = _ScriptedFactJudge(
        claims=[("A", "https://x.org/a"), ("B", "https://missing.org/b")],
        supported=True,
    )
    return {"judge": judge, "sources": None, "result": None, "exc": None}


@given("a scripted FACT judge", target_fixture="fact_ctx")
def _given_scripted_fact() -> dict[str, Any]:
    return {"judge": _ScriptedFactJudge(claims=[]), "sources": None, "result": None, "exc": None}


@given("a sources map covering every URL")
def _given_sources_complete(fact_ctx: dict[str, Any]) -> None:
    fact_ctx["sources"] = {"https://x.org/a": "src-a", "https://x.org/b": "src-b"}


@given("a sources map missing one URL")
def _given_sources_missing(fact_ctx: dict[str, Any]) -> None:
    fact_ctx["sources"] = {"https://x.org/a": "src-a"}


@when("the FACT evaluator runs")
def _when_runs(fact_ctx: dict[str, Any]) -> None:
    evaluator = FactEvaluator(client=fact_ctx["judge"])
    fact_ctx["result"] = asyncio.run(evaluator.evaluate(report="a report", sources=fact_ctx["sources"]))


@when("the FACT evaluator is called with an empty report")
def _when_empty(fact_ctx: dict[str, Any]) -> None:
    evaluator = FactEvaluator(client=fact_ctx["judge"])
    try:
        asyncio.run(evaluator.evaluate(report="", sources={}))
    except UserFixableError as exc:
        fact_ctx["exc"] = exc


@then("the citation accuracy is 1.0")
def _then_accuracy_one(fact_ctx: dict[str, Any]) -> None:
    assert fact_ctx["result"].citation_accuracy == 1.0


@then("the effective citation count equals the supported count")
def _then_effective_equals(fact_ctx: dict[str, Any]) -> None:
    metrics = fact_ctx["result"]
    assert metrics.effective_citations == metrics.supported


@then("the missing-source claim is marked unsupported by provided sources")
def _then_marked_unsupported(fact_ctx: dict[str, Any]) -> None:
    claim = next(c for c in fact_ctx["result"].claims if c.url == "https://missing.org/b")
    assert claim.supported is None
    assert claim.reason == "source_not_provided"


@then("the accuracy denominator excludes the missing claim")
def _then_denom_excludes(fact_ctx: dict[str, Any]) -> None:
    metrics = fact_ctx["result"]
    assert metrics.total == 1
    assert metrics.citation_accuracy == 1.0


@then("a UserFixableError is raised")
def _then_user_fixable(fact_ctx: dict[str, Any]) -> None:
    assert isinstance(fact_ctx["exc"], UserFixableError)
