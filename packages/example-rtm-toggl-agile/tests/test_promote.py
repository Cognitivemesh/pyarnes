"""Behavioural tests for the RTM/Toggl → agile pipeline."""

from __future__ import annotations

import pytest
from rtm_toggl_agile.guardrails import ApiQuotaGuardrail, SecretScanGuardrail
from rtm_toggl_agile.pipeline import promote
from rtm_toggl_agile.schema import AgileWorkspace

from pyarnes_core.errors import UserFixableError


async def test_promote_merges_rtm_and_toggl() -> None:
    """RTM tasks become stories; Toggl entries link by story_id."""
    rtm = [
        {"id": "S-1", "name": "Refactor auth", "tags": ["backend"], "due": "2026-05-01"},
        {"id": "S-2", "name": "Draft release notes"},
    ]
    toggl = [
        {"story_id": "S-1", "duration": 3600, "tags": ["deep-work"]},
        {"story_id": "S-1", "duration": 1200},
    ]

    workspace = AgileWorkspace()
    await promote(workspace, rtm_fixture=rtm, toggl_fixture=toggl)

    assert set(workspace.stories) == {"S-1", "S-2"}
    assert workspace.stories["S-1"].tags == ("backend",)
    assert workspace.stories["S-1"].due_date == "2026-05-01"
    assert len(workspace.entries) == 2
    assert all(e.story_id == "S-1" for e in workspace.entries)


async def test_promote_is_lossless_over_empty_sources() -> None:
    """Zero-input sync produces an empty but valid workspace."""
    workspace = AgileWorkspace()
    await promote(workspace)
    assert workspace.stories == {}
    assert workspace.entries == []


def test_secret_scan_guardrail_rejects_credentials() -> None:
    """Credential-shaped values in tool arguments are refused."""
    guardrail = SecretScanGuardrail()
    with pytest.raises(UserFixableError, match="credential-shaped"):
        guardrail.check("upsert_story", {"title": "Bearer abcdef12345"})


def test_api_quota_guardrail_passes_below_budget() -> None:
    """Below the call budget, the guardrail must not block."""
    guardrail = ApiQuotaGuardrail(calls_per_minute=5)
    for _ in range(5):
        guardrail.check("list_rtm_tasks", {"list_id": "inbox"})


def test_api_quota_guardrail_blocks_over_budget() -> None:
    """Exceeding the call budget raises UserFixableError."""
    guardrail = ApiQuotaGuardrail(calls_per_minute=2)
    guardrail.check("list_rtm_tasks", {"list_id": "a"})
    guardrail.check("list_rtm_tasks", {"list_id": "b"})
    with pytest.raises(UserFixableError, match="rate limit exceeded"):
        guardrail.check("list_rtm_tasks", {"list_id": "c"})


def test_api_quota_guardrail_scoped_to_external_tools() -> None:
    """Internal tools (upsert_story, add_time_entry) are not rate-limited."""
    guardrail = ApiQuotaGuardrail(calls_per_minute=1)
    guardrail.check("list_rtm_tasks", {})
    # Additional external call would fail — but internal calls don't count.
    for _ in range(10):
        guardrail.check("upsert_story", {})
