"""BDD step definitions for user acceptance test scenarios."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from pyarnes_bench import EvalResult, EvalSuite, ExactMatchScorer
from pyarnes_core.errors import UserFixableError
from pyarnes_core.lifecycle import Lifecycle
from pyarnes_core.types import ModelClient, ToolHandler
from pyarnes_guardrails import PathGuardrail
from pyarnes_harness.loop import AgentLoop, LoopConfig

# ── Scenarios ──────────────────────────────────────────────────────────────


@scenario("../acceptance.feature", "Agent loop executes a tool and returns a final answer")
def test_agent_loop_acceptance() -> None:
    """Agent loop acceptance scenario."""


@scenario("../acceptance.feature", "Guardrails block a dangerous path")
def test_guardrails_acceptance() -> None:
    """Guardrails acceptance scenario."""


@scenario("../acceptance.feature", "Lifecycle tracks a full session")
def test_lifecycle_acceptance() -> None:
    """Lifecycle acceptance scenario."""


@scenario("../acceptance.feature", "Evaluation suite scores scenarios correctly")
def test_eval_acceptance() -> None:
    """Eval suite acceptance scenario."""


# ── Helpers ────────────────────────────────────────────────────────────────


@dataclass
class _EchoTool(ToolHandler):
    async def execute(self, arguments: dict[str, Any]) -> Any:
        return arguments.get("text", "echo")


@dataclass
class _ScriptedModel(ModelClient):
    actions: list[dict[str, Any]]
    _idx: int = 0

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        action = self.actions[self._idx]
        self._idx += 1
        return action


# ── Agent loop steps ───────────────────────────────────────────────────────


@given("a registered echo tool and a model that calls it once", target_fixture="loop_ctx")
def _given_echo_loop() -> dict[str, Any]:
    model = _ScriptedModel(
        actions=[
            {"type": "tool_call", "tool": "echo", "id": "c1", "arguments": {"text": "hello"}},
            {"type": "final_answer", "content": "done"},
        ]
    )
    loop = AgentLoop(
        tools={"echo": _EchoTool()},
        model=model,
        config=LoopConfig(max_iterations=10),
    )
    return {"loop": loop, "result": None}


@when("I run the agent loop")
def _when_run_loop(loop_ctx: dict[str, Any]) -> None:
    loop_ctx["result"] = asyncio.run(loop_ctx["loop"].run([]))


@then("the result contains the tool output and a final answer")
def _then_result_has_answer(loop_ctx: dict[str, Any]) -> None:
    result = loop_ctx["result"]
    tool_msgs = [m for m in result if m.get("role") == "tool"]
    assert len(tool_msgs) >= 1
    assert tool_msgs[0]["content"] == "hello"
    assert any(m.get("type") == "final_answer" for m in result)


# ── Guardrail steps ───────────────────────────────────────────────────────


@given('a path guardrail with allowed root "/workspace"', target_fixture="guard_ctx")
def _given_path_guardrail() -> dict[str, Any]:
    return {"guardrail": PathGuardrail(allowed_roots=("/workspace",)), "exc": None}


@when('I check a tool call with path "/etc/shadow"')
def _when_check_blocked(guard_ctx: dict[str, Any]) -> None:
    try:
        guard_ctx["guardrail"].check("read_file", {"path": "/etc/shadow"})
    except UserFixableError as e:
        guard_ctx["exc"] = e


@then("the guardrail raises a UserFixableError")
def _then_guardrail_blocked(guard_ctx: dict[str, Any]) -> None:
    assert isinstance(guard_ctx["exc"], UserFixableError)


# ── Lifecycle steps ────────────────────────────────────────────────────────


@given("a new lifecycle session", target_fixture="lc_ctx")
def _given_lifecycle() -> dict[str, Any]:
    return {"lc": Lifecycle()}


@when("I start, pause, resume, and complete the session")
def _when_lifecycle_flow(lc_ctx: dict[str, Any]) -> None:
    lc = lc_ctx["lc"]
    lc.start()
    lc.pause()
    lc.resume()
    lc.complete()


@then(parsers.parse('the lifecycle phase is "{phase}"'))
def _then_phase(lc_ctx: dict[str, Any], phase: str) -> None:
    assert lc_ctx["lc"].phase.value == phase


@then(parsers.parse("the history has {count:d} transitions"))
def _then_history_count(lc_ctx: dict[str, Any], count: int) -> None:
    assert len(lc_ctx["lc"].history) == count


# ── Eval suite steps ──────────────────────────────────────────────────────


@given("an eval suite with one correct and one incorrect scenario", target_fixture="eval_ctx")
def _given_eval_suite() -> dict[str, Any]:
    return {
        "scenarios": [
            ("correct", "hello", "hello"),
            ("wrong", "hello", "bye"),
        ],
        "suite": None,
    }


@when("I score the suite with exact match")
def _when_score(eval_ctx: dict[str, Any]) -> None:
    scorer = ExactMatchScorer(case_sensitive=False)
    suite = EvalSuite(name="acceptance")
    for name, expected, actual in eval_ctx["scenarios"]:
        score = scorer.score(expected, actual)
        suite.add(EvalResult(scenario=name, expected=expected, actual=actual, score=score, passed=score >= 1.0))
    eval_ctx["suite"] = suite


@then(parsers.parse("the pass rate is {rate:g}"))
def _then_pass_rate(eval_ctx: dict[str, Any], rate: float) -> None:
    assert eval_ctx["suite"].pass_rate == pytest.approx(rate)


@then(parsers.parse("the average score is {score:g}"))
def _then_average_score(eval_ctx: dict[str, Any], score: float) -> None:
    assert eval_ctx["suite"].average_score == pytest.approx(score)
