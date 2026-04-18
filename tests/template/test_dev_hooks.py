"""Dev-hook behaviour tests — run the shipped hooks against synthetic events.

The pre-tool-use hook must block dangerous tool calls with exit code 2.
The post-tool-use hook must append a JSONL record to
``.pyarnes/agent_tool_calls.jsonl``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def hooks_project(run_copy, tmp_path: Path) -> Path:
    return run_copy(
        tmp_path / "hooks-project",
        project_name="hooks-project",
        project_description="hooks project",
        adopter_shape="rtm-toggl-agile",
        enable_dev_hooks=True,
    )


def _run_hook(script: Path, event: dict, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — test-controlled invocation
        [sys.executable, str(script)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def test_pre_tool_hook_blocks_command_guardrail(hooks_project: Path) -> None:
    """A ``rm -rf /`` invocation is blocked by ``CommandGuardrail``."""
    script = hooks_project / ".claude" / "hooks" / "pyarnes_pre_tool.py"
    result = _run_hook(
        script,
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
        cwd=hooks_project,
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert "dangerous" in payload["reason"].lower() or "command" in payload["reason"].lower()


def test_pre_tool_hook_blocks_disallowed_tool(hooks_project: Path) -> None:
    """An unknown tool name is blocked by ``ToolAllowlistGuardrail``."""
    script = hooks_project / ".claude" / "hooks" / "pyarnes_pre_tool.py"
    result = _run_hook(
        script,
        {"tool_name": "RmRfRoot", "tool_input": {}},
        cwd=hooks_project,
    )
    assert result.returncode == 2, result.stderr


def test_pre_tool_hook_allows_safe_call(hooks_project: Path) -> None:
    """A ``Read`` within the project root passes the chain."""
    script = hooks_project / ".claude" / "hooks" / "pyarnes_pre_tool.py"
    result = _run_hook(
        script,
        {
            "tool_name": "Read",
            "tool_input": {"file_path": str(hooks_project / "pyproject.toml")},
        },
        cwd=hooks_project,
    )
    assert result.returncode == 0, result.stderr


def test_post_tool_hook_appends_jsonl(hooks_project: Path) -> None:
    """The post-tool hook writes one JSONL record with the expected fields."""
    script = hooks_project / ".claude" / "hooks" / "pyarnes_post_tool.py"
    event = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "foo.py"},
        "tool_response": "ok",
        "is_error": False,
        "started_at": 1.0,
        "finished_at": 1.5,
    }
    result = _run_hook(script, event, cwd=hooks_project)
    assert result.returncode == 0, result.stderr

    log_file = hooks_project / ".pyarnes" / "agent_tool_calls.jsonl"
    assert log_file.is_file()
    record = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert record["tool"] == "Edit"
    assert record["is_error"] is False
    assert record["duration_seconds"] == pytest.approx(0.5)
