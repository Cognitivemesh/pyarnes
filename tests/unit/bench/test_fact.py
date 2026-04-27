"""Tests for :mod:`pyarnes_bench.fact`."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from pyarnes_bench import (
    CitationClaim,
    FactEvaluator,
    FactMetrics,
    effective_citations_across,
)
from pyarnes_core.errors import UserFixableError


class ScriptedFactJudge:
    """Scripted model for FACT: fixed claim list + deterministic verifier."""

    def __init__(
        self,
        *,
        claims: list[tuple[str, str]],
        verify_fn: object = None,
    ) -> None:
        self._claims = claims
        self._verify_fn = verify_fn or (lambda statement, url, source: (True, "ok"))
        self.calls = 0

    async def judge(self, prompt: str) -> str:
        self.calls += 1
        if "Extract every cited claim" in prompt:
            return json.dumps({"claims": [{"statement": s, "url": u} for s, u in self._claims]})
        # Parse statement + url back out of the verification prompt.
        # Prompt contains "Claim: {statement}\nURL: {url}\n\nSource:\n{source}"
        marker = prompt.index("Claim: ") + len("Claim: ")
        url_idx = prompt.index("\nURL: ", marker)
        statement = prompt[marker:url_idx]
        url_start = url_idx + len("\nURL: ")
        source_idx = prompt.index("\n\nSource:\n", url_start)
        url = prompt[url_start:source_idx]
        source = prompt[source_idx + len("\n\nSource:\n") :]
        supported, reason = self._verify_fn(statement, url, source)  # type: ignore[misc]
        return json.dumps({"supported": supported, "reason": reason})


class TestFactEvaluator:
    @pytest.mark.asyncio
    async def test_all_supported(self) -> None:
        judge = ScriptedFactJudge(
            claims=[("A", "https://x.org/a"), ("B", "https://x.org/b")],
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(
            report="some report",
            sources={"https://x.org/a": "src-a", "https://x.org/b": "src-b"},
        )
        assert metrics.total == 2
        assert metrics.supported == 2
        assert metrics.citation_accuracy == 1.0
        assert metrics.effective_citations == 2

    @pytest.mark.asyncio
    async def test_unsupported_drags_accuracy(self) -> None:
        def verify(statement: str, url: str, source: str) -> tuple[bool, str]:
            return (statement == "A", "ok")

        judge = ScriptedFactJudge(
            claims=[("A", "https://x.org/a"), ("B", "https://x.org/b")],
            verify_fn=verify,
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(
            report="r",
            sources={"https://x.org/a": "src-a", "https://x.org/b": "src-b"},
        )
        assert metrics.total == 2
        assert metrics.supported == 1
        assert metrics.citation_accuracy == 0.5

    @pytest.mark.asyncio
    async def test_missing_source_excluded_from_denominator(self) -> None:
        judge = ScriptedFactJudge(
            claims=[("A", "https://x.org/a"), ("B", "https://missing.org/b")],
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(
            report="r",
            sources={"https://x.org/a": "src-a"},
        )
        assert metrics.total == 1
        assert metrics.supported == 1
        assert metrics.citation_accuracy == 1.0
        missing_claim = next(c for c in metrics.claims if c.url == "https://missing.org/b")
        assert missing_claim.supported is None
        assert missing_claim.reason == "source_not_provided"

    @pytest.mark.asyncio
    async def test_exact_duplicates_collapse(self) -> None:
        judge = ScriptedFactJudge(
            claims=[
                ("A", "https://x.org/a"),
                ("A", "https://x.org/a"),
                ("A", "https://x.org/a"),
            ],
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(report="r", sources={"https://x.org/a": "s"})
        assert metrics.total == 1

    @pytest.mark.asyncio
    async def test_near_duplicates_collapse(self) -> None:
        judge = ScriptedFactJudge(
            claims=[
                ("The Earth orbits the Sun.", "https://x.org/a"),
                ("The Earth orbits the Sun", "https://x.org/a"),  # ratio > 0.97
            ],
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(report="r", sources={"https://x.org/a": "s"})
        assert metrics.total == 1

    @pytest.mark.asyncio
    async def test_different_urls_do_not_collapse(self) -> None:
        judge = ScriptedFactJudge(
            claims=[
                ("same statement", "https://x.org/a"),
                ("same statement", "https://y.org/b"),
            ],
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(
            report="r",
            sources={"https://x.org/a": "s1", "https://y.org/b": "s2"},
        )
        assert metrics.total == 2

    @pytest.mark.asyncio
    async def test_empty_report_raises(self) -> None:
        evaluator = FactEvaluator(client=ScriptedFactJudge(claims=[]))
        with pytest.raises(UserFixableError):
            await evaluator.evaluate(report="", sources={})

    @pytest.mark.asyncio
    async def test_no_claims_yields_zero_accuracy(self) -> None:
        judge = ScriptedFactJudge(claims=[])
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(report="r", sources={})
        assert metrics.total == 0
        assert metrics.citation_accuracy == 0.0

    @pytest.mark.asyncio
    async def test_to_eval_result_threshold(self) -> None:
        judge = ScriptedFactJudge(
            claims=[("A", "https://x.org/a"), ("B", "https://x.org/b")],
            verify_fn=lambda s, u, src: (s == "A", "ok"),
        )
        evaluator = FactEvaluator(client=judge)
        metrics = await evaluator.evaluate(
            report="r",
            sources={"https://x.org/a": "s1", "https://x.org/b": "s2"},
        )
        result = metrics.to_eval_result(scenario="citations", threshold=0.8)
        assert result.scenario == "citations"
        assert result.score == 0.5
        assert result.passed is False


class TestFactMetricsValidation:
    def test_supported_cannot_exceed_total(self) -> None:
        with pytest.raises(ValidationError):
            FactMetrics(claims=(), total=1, supported=2, citation_accuracy=1.0)

    def test_effective_citations_is_derived(self) -> None:
        metrics = FactMetrics(claims=(), total=3, supported=2, citation_accuracy=2 / 3)
        assert metrics.effective_citations == 2
        # Derived fields appear in model_dump; explicit assignment is rejected.
        assert metrics.model_dump()["effective_citations"] == 2

    def test_citation_claim_requires_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            CitationClaim(statement="", url="https://x.org")
        with pytest.raises(ValidationError):
            CitationClaim(statement="x", url="")


class TestAcrossTask:
    def test_mean_across_tasks(self) -> None:
        m1 = FactMetrics(claims=(), total=3, supported=3, citation_accuracy=1.0)
        m2 = FactMetrics(claims=(), total=2, supported=1, citation_accuracy=0.5)
        m3 = FactMetrics(claims=(), total=2, supported=2, citation_accuracy=1.0)
        assert effective_citations_across([m1, m2, m3]) == pytest.approx(2.0)

    def test_empty_returns_zero(self) -> None:
        assert effective_citations_across([]) == 0.0
