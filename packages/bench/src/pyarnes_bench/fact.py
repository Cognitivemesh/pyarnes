"""FACT — Factual Abundance and Citation Trustworthiness.

Post-hoc, sequential evaluator for how many of a finished report's
cited claims are actually supported by their sources (accuracy) and
how many supported citations the agent produced per task (abundance,
aka "effective citations"). Runs after the external agent has emitted
its report and the adopter has fetched the cited pages.

Two-stage pipeline, one ``await`` at a time:

1. **Extraction** — one judge call returns ``(statement, url)`` pairs.
2. **Deduplication** — identical ``(statement, url)`` collapse; near-
   duplicate statements (``difflib.SequenceMatcher`` ratio ≥ 0.97)
   sharing the same URL collapse too.
3. **Verification** — for each remaining pair, one judge call checks
   whether ``sources[url]`` supports the statement. Missing URLs are
   marked ``supported=None`` and excluded from the accuracy denominator
   (matches the paper's semantics).

The evaluator never fetches a URL itself. Callers pass a
``sources: Mapping[str, str]`` they prepared by whatever means
(requests + cache, Playwright, pre-baked fixture, …). This keeps
``pyarnes-bench`` side-effect-free.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from pyarnes_bench._judge import judge_json
from pyarnes_bench.eval import EvalResult
from pyarnes_core.errors import UserFixableError
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.types import ModelClient

__all__ = [
    "CitationClaim",
    "FactEvaluator",
    "FactMetrics",
    "FactPrompts",
    "Sources",
    "effective_citations_across",
]

logger = get_logger(__name__)

Sources = Mapping[str, str]
"""Adopter-prepared ``{url: fetched_content}`` map. FACT never fetches."""

_UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
_DEDUP_SIMILARITY = 0.97
_MISSING_SOURCE_REASON = "source_not_provided"


class CitationClaim(BaseModel):
    """A single cited statement extracted from the report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: str = Field(min_length=1)
    url: str = Field(min_length=1)
    supported: bool | None = None
    reason: str = ""


class FactMetrics(BaseModel):
    """Aggregate verification metrics for one report.

    ``effective_citations`` is derived from ``supported`` — DeepResearch
    Bench names them separately in the paper, but within a single task
    they are the same number. The alias keeps the paper's vocabulary
    intact without storing the value twice.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[CitationClaim, ...]
    total: int = Field(ge=0)
    supported: int = Field(ge=0)
    citation_accuracy: _UnitFloat
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_counts(self) -> FactMetrics:
        if self.supported > self.total:
            raise ValueError("supported count cannot exceed total")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_citations(self) -> int:
        """Supported-claim count — the abundance metric within one task."""
        return self.supported

    def to_eval_result(self, *, scenario: str, threshold: float = 0.8) -> EvalResult:
        """Adapt to :class:`pyarnes_bench.EvalResult` for ``EvalSuite``."""
        return EvalResult(
            scenario=scenario,
            expected=f"citation_accuracy >= {threshold}",
            actual=f"citation_accuracy = {self.citation_accuracy:.4f}",
            score=self.citation_accuracy,
            passed=self.citation_accuracy >= threshold,
            metadata={
                **self.metadata,
                "total": self.total,
                "supported": self.supported,
                "effective_citations": self.effective_citations,
            },
        )


_DEFAULT_EXTRACTION_PROMPT = (
    "Extract every cited claim from the report below. Output ONLY a "
    "JSON object matching "
    '{{"claims": [{{"statement": str, "url": str}}, ...]}} where '
    "each statement is the shortest factual sentence that carries the "
    "citation and each url is the exact URL referenced. Do not "
    "invent URLs.\n\nReport:\n{report}\n"
)
_DEFAULT_VERIFICATION_PROMPT = (
    "Decide whether the source below supports the claim. Output ONLY a "
    "JSON object matching "
    '{{"supported": bool, "reason": str}}.\n\n'
    "Claim: {statement}\nURL: {url}\n\n"
    "Source:\n{source}\n"
)


class FactPrompts(BaseModel):
    """Prompt templates used by the two judge calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    extraction_prompt: str = _DEFAULT_EXTRACTION_PROMPT
    verification_prompt: str = _DEFAULT_VERIFICATION_PROMPT


class _ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")
    statement: str = Field(min_length=1)
    url: str = Field(min_length=1)


class _ClaimsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    claims: list[_ExtractedClaim]


class _VerificationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supported: bool
    reason: str = ""


class FactEvaluator:
    """Post-hoc, sequential FACT evaluator.

    Args:
        client: Any ``ModelClient``; the judge.
        prompts: Overridable prompt templates.
    """

    def __init__(
        self,
        client: ModelClient,
        *,
        prompts: FactPrompts | None = None,
    ) -> None:
        """Configure the evaluator; see class docstring for semantics."""
        self._client = client
        self._prompts = prompts or FactPrompts()

    async def evaluate(
        self,
        *,
        report: str,
        sources: Sources,
    ) -> FactMetrics:
        """Run extraction + verification end-to-end.

        Args:
            report: The finished report containing cited claims.
            sources: Caller-prepared ``{url: fetched_content}`` map.
                URLs absent from the map mark the claim
                ``supported=None`` with reason ``"source_not_provided"``.

        Returns:
            A populated :class:`FactMetrics`.

        Raises:
            UserFixableError: If ``report`` is blank.
            LLMRecoverableError: If extraction or verification persists
                in returning non-JSON.
        """
        if not report.strip():
            raise UserFixableError(
                message="FACT evaluator requires a non-empty report",
                prompt_hint="Provide the finished report to be checked.",
            )

        extracted = await self._extract_claims(report)
        pairs = _dedupe(extracted)
        logger.info(
            "fact.extracted raw={raw} dedup={dedup}",
            raw=len(extracted),
            dedup=len(pairs),
        )

        verified: list[CitationClaim] = []
        for statement, url in pairs:
            source = sources.get(url)
            if source is None:
                verified.append(
                    CitationClaim(
                        statement=statement,
                        url=url,
                        supported=None,
                        reason=_MISSING_SOURCE_REASON,
                    )
                )
                continue
            response = await self._verify_claim(statement, url, source)
            verified.append(
                CitationClaim(
                    statement=statement,
                    url=url,
                    supported=response.supported,
                    reason=response.reason,
                )
            )

        total = sum(1 for c in verified if c.supported is not None)
        supported = sum(1 for c in verified if c.supported is True)
        accuracy = supported / total if total else 0.0
        return FactMetrics(
            claims=tuple(verified),
            total=total,
            supported=supported,
            citation_accuracy=accuracy,
            metadata={"raw_claims": len(extracted), "dedup_claims": len(pairs)},
        )

    async def _extract_claims(self, report: str) -> list[_ExtractedClaim]:
        prompt = self._prompts.extraction_prompt.format(report=report)
        response = await judge_json(self._client, prompt, _ClaimsResponse)
        return response.claims

    async def _verify_claim(
        self,
        statement: str,
        url: str,
        source: str,
    ) -> _VerificationResponse:
        prompt = self._prompts.verification_prompt.format(
            statement=statement,
            url=url,
            source=source,
        )
        return await judge_json(self._client, prompt, _VerificationResponse)


def _dedupe(claims: list[_ExtractedClaim]) -> list[tuple[str, str]]:
    """Collapse identical and near-identical ``(statement, url)`` pairs.

    Two claims collapse when their URLs match and either ``statement``s
    are byte-equal or their similarity ratio is ``>= _DEDUP_SIMILARITY``.
    SequenceMatcher is only invoked within same-URL buckets so the cost
    is quadratic in duplicates-per-URL, not in total claim count.
    """
    kept: list[tuple[str, str]] = []
    seen_by_url: dict[str, list[str]] = {}
    for claim in claims:
        bucket = seen_by_url.setdefault(claim.url, [])
        if any(
            s == claim.statement
            or SequenceMatcher(None, s, claim.statement).ratio() >= _DEDUP_SIMILARITY
            for s in bucket
        ):
            continue
        kept.append((claim.statement, claim.url))
        bucket.append(claim.statement)
    return kept


def effective_citations_across(metrics: Iterable[FactMetrics]) -> float:
    """Average supported-citation count across a batch of tasks.

    DeepResearch Bench reports the across-task mean as the abundance
    metric. This helper lets adopters compute it from a list of per-
    task :class:`FactMetrics` without re-implementing the aggregation.
    """
    counts = [m.effective_citations for m in metrics]
    return sum(counts) / len(counts) if counts else 0.0
