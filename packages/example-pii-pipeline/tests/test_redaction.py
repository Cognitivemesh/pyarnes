"""End-to-end test for the PII-redaction reference adopter.

Proves the library-first contract: the pipeline wires pyarnes's stable
surface together and runs without importing any private symbols.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pii_pipeline.guardrails import PiiLeakGuardrail
from pii_pipeline.pipeline import build_guardrail_chain, build_registry, redact
from pii_pipeline.tools import DetectPii

from pyarnes_core.errors import UserFixableError


async def test_redact_removes_seeded_pii(tmp_path: Path) -> None:
    """The redacted output contains none of the seeded PII literals."""
    src = tmp_path / "sample.txt"
    src.write_text(
        "Please contact alice@example.com or 555-123-4567.\n"
        "Her SSN is 123-45-6789 — keep private.",
    )

    markdown = await redact(str(src))

    assert "alice@example.com" not in markdown
    assert "555-123-4567" not in markdown
    assert "123-45-6789" not in markdown
    assert "[EMAIL]" in markdown
    assert "[PHONE]" in markdown
    assert "[SSN]" in markdown


async def test_detect_pii_finds_all_patterns() -> None:
    """Each regex pattern contributes to the returned span list."""
    handler = DetectPii()
    spans = await handler.execute(
        {"text": "e bob@example.com p 555-111-2222 s 123-45-6789"},
    )
    types = {s["type"] for s in spans}
    assert types == {"email", "phone", "ssn"}


def test_guardrail_blocks_unredacted_markdown() -> None:
    """``PiiLeakGuardrail`` rejects render_markdown with residual PII."""
    guardrail = PiiLeakGuardrail()
    with pytest.raises(UserFixableError, match="still contains PII"):
        guardrail.check("render_markdown", {"text": "mail alice@example.com"})


def test_guardrail_chain_tool_allowlist() -> None:
    """Unknown tool names are rejected by the allowlist guardrail."""
    chain = build_guardrail_chain(allowed_roots=(".",))
    with pytest.raises(UserFixableError):
        chain.check("untrusted_tool", {})


def test_registry_declares_expected_tools() -> None:
    """The four pipeline tools are registered."""
    registry = build_registry()
    assert set(registry.names) == {
        "extract_text",
        "detect_pii",
        "redact_pii",
        "render_markdown",
    }
