"""Pydantic models shared across API routes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── Health ─────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str


# ── Lifecycle ──────────────────────────────────────────────────────────────


class LifecycleState(BaseModel):
    """Current lifecycle state."""

    phase: str
    is_terminal: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


class TransitionRequest(BaseModel):
    """Request to transition the lifecycle to a new phase."""

    action: str = Field(
        ...,
        description="One of: start, pause, resume, complete, fail",
        pattern="^(start|pause|resume|complete|fail)$",
    )


# ── Guardrails ─────────────────────────────────────────────────────────────


class GuardrailCheckRequest(BaseModel):
    """Request to validate a tool call against guardrails."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class GuardrailCheckResponse(BaseModel):
    """Result of a guardrail check."""

    allowed: bool
    violation: str | None = None


# ── Tools ──────────────────────────────────────────────────────────────────


class ToolInfo(BaseModel):
    """Summary of a registered tool."""

    name: str
    handler_type: str


class ToolListResponse(BaseModel):
    """List of all registered tools."""

    tools: list[ToolInfo]
    count: int


# ── Eval ───────────────────────────────────────────────────────────────────


class EvalScenario(BaseModel):
    """A single evaluation scenario to score."""

    scenario: str
    expected: str
    actual: str


class EvalResultResponse(BaseModel):
    """Result of a single evaluation."""

    scenario: str
    expected: str
    actual: str
    score: float
    passed: bool


class EvalSuiteRequest(BaseModel):
    """Request to score a batch of evaluation scenarios."""

    suite_name: str = "api-eval"
    pass_threshold: float = Field(default=1.0, ge=0.0, le=1.0)
    scenarios: list[EvalScenario]


class EvalSuiteResponse(BaseModel):
    """Aggregate results for an evaluation suite."""

    suite: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    average_score: float
    results: list[EvalResultResponse]


# ── Error ──────────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    error: str
    detail: str | None = None
