"""SWE-bench integration — data model only.

Execution infrastructure (git clone, env setup, containerised test runs)
is deferred to a future milestone. This module defines the typed record
used to describe a single SWE-bench instance so consumers can reference
the type today.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SWEBenchScenario"]


@dataclass(frozen=True, slots=True)
class SWEBenchScenario:
    """A single SWE-bench instance (data record only).

    Attributes:
        instance_id: Unique identifier (e.g. ``"django__django-12345"``).
        repo: GitHub repository slug (e.g. ``"django/django"``).
        issue_description: The bug report or feature request text.
        base_commit: Git commit SHA the agent should start from.
        test_patch: Patch containing tests that must pass after the fix.
        golden_patch: The canonical fix patch (for evaluation only).
    """

    instance_id: str
    repo: str
    issue_description: str
    base_commit: str
    test_patch: str
    golden_patch: str
