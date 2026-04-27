"""Tests for task-kind classification."""

from __future__ import annotations

from typing import Any

from pyarnes_bench.burn.classify import TaskKind, classify, classify_window
from pyarnes_harness.capture.tool_log import ToolCallEntry


def _entry(
    tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    is_error: bool = False,
    result: Any = None,
) -> ToolCallEntry:
    return ToolCallEntry(
        tool=tool,
        arguments=arguments or {},
        result=result,
        is_error=is_error,
        started_at="2026-04-21T10:00:00Z",
        finished_at="2026-04-21T10:00:01Z",
        duration_seconds=0.0,
    )


class TestClassify:
    def test_task_tool_is_delegation(self) -> None:
        assert classify(_entry("Task", {"subagent_type": "Explore"})) == TaskKind.DELEGATION

    def test_todowrite_is_planning(self) -> None:
        assert classify(_entry("TodoWrite", {"todos": []})) == TaskKind.PLANNING

    def test_websearch_is_exploration(self) -> None:
        assert classify(_entry("WebSearch", {"query": "x"})) == TaskKind.EXPLORATION

    def test_read_is_exploration(self) -> None:
        assert classify(_entry("Read", {"file_path": "/x"})) == TaskKind.EXPLORATION

    def test_grep_is_exploration(self) -> None:
        assert classify(_entry("Grep", {"pattern": "foo"})) == TaskKind.EXPLORATION

    def test_write_is_feature_dev(self) -> None:
        assert classify(_entry("Write", {"file_path": "/x", "content": "y"})) == TaskKind.FEATURE_DEV

    def test_edit_is_coding(self) -> None:
        assert classify(_entry("Edit", {"file_path": "/x", "old_string": "a"})) == TaskKind.CODING

    def test_edit_with_refactor_keyword_is_refactor(self) -> None:
        entry = _entry("Edit", {"file_path": "/x", "old_string": "rename get_cwd"})
        assert classify(entry) == TaskKind.REFACTOR

    def test_bash_git_is_git_ops(self) -> None:
        assert classify(_entry("Bash", {"command": "git status"})) == TaskKind.GIT_OPS

    def test_bash_pytest_is_testing(self) -> None:
        assert classify(_entry("Bash", {"command": "uv run pytest -k foo"})) == TaskKind.TESTING

    def test_bash_docker_is_build_deploy(self) -> None:
        assert classify(_entry("Bash", {"command": "docker build ."})) == TaskKind.BUILD_DEPLOY

    def test_bash_other_is_coding(self) -> None:
        assert classify(_entry("Bash", {"command": "ls -la"})) == TaskKind.CODING

    def test_unknown_tool_is_general(self) -> None:
        assert classify(_entry("WeirdNewTool", {})) == TaskKind.GENERAL


class TestClassifyWindow:
    def test_baseline_matches_per_call(self) -> None:
        entries = [
            _entry("Read", {"file_path": "/a"}),
            _entry("Edit", {"file_path": "/a", "old_string": "x"}),
        ]
        assert classify_window(entries) == [TaskKind.EXPLORATION, TaskKind.CODING]

    def test_edit_failing_bash_edit_becomes_debugging(self) -> None:
        entries = [
            _entry("Edit", {"file_path": "/a", "old_string": "x"}),
            _entry("Bash", {"command": "uv run pytest"}, is_error=True),
            _entry("Edit", {"file_path": "/a", "old_string": "y"}),
        ]
        result = classify_window(entries)
        assert result == [TaskKind.DEBUGGING, TaskKind.DEBUGGING, TaskKind.DEBUGGING]

    def test_failing_bash_without_following_edit_stays_testing(self) -> None:
        entries = [
            _entry("Edit", {"file_path": "/a", "old_string": "x"}),
            _entry("Bash", {"command": "pytest"}, is_error=True),
            _entry("Read", {"file_path": "/a"}),
        ]
        result = classify_window(entries)
        # First Edit stays CODING, Bash failing is TESTING, Read is EXPLORATION
        assert result[0] == TaskKind.CODING
        assert result[1] == TaskKind.TESTING
        assert result[2] == TaskKind.EXPLORATION

    def test_bucket_coverage_includes_brainstorm_and_conversation(self) -> None:
        # These two buckets are reachable only via callers that override
        # the classifier; ensure the enum still includes them so the
        # 13-bucket promise holds.
        assert {TaskKind.BRAINSTORM, TaskKind.CONVERSATION} <= set(TaskKind)
