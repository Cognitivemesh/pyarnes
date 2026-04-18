"""Orchestrates the PII-redaction pipeline using only pyarnes' stable surface."""

from __future__ import annotations

from typing import Any, cast

from pii_pipeline.guardrails import PiiLeakGuardrail
from pii_pipeline.tools import register_tools
from pyarnes_core.observe.logger import get_logger
from pyarnes_guardrails import GuardrailChain, PathGuardrail, ToolAllowlistGuardrail
from pyarnes_harness import ToolRegistry

log = get_logger(__name__)


def build_registry() -> ToolRegistry:
    """Return a registry populated with every PII-pipeline tool."""
    registry = ToolRegistry()
    register_tools(registry)
    return registry


def build_guardrail_chain(
    registry: ToolRegistry, allowed_roots: tuple[str, ...],
) -> GuardrailChain:
    """Return the chain the adopter invokes before each tool dispatch."""
    return GuardrailChain(guardrails=[
        PathGuardrail(allowed_roots=allowed_roots),
        ToolAllowlistGuardrail(allowed_tools=frozenset(registry.names)),
        PiiLeakGuardrail(),
    ])


async def redact(
    input_path: str,
    *,
    title: str | None = None,
    allowed_roots: tuple[str, ...] | None = None,
) -> str:
    """Run the full extract → detect → redact → render sequence.

    Adopters typically drive this loop with ``AgentLoop``. The dispatch is
    spelt out inline here so readers see the three-part contract (register
    → compose → dispatch) without it being hidden behind a helper.

    Args:
        input_path: File to redact.
        title: Optional markdown heading; defaults to the file stem.
        allowed_roots: Roots the ``PathGuardrail`` accepts. Defaults to the
            parent directory of ``input_path``.

    Returns:
        The final redacted markdown document.
    """
    from pathlib import Path  # noqa: PLC0415

    registry = build_registry()
    tools = registry.as_dict()
    roots = allowed_roots or (str(Path(input_path).resolve().parent),)
    chain = build_guardrail_chain(registry, allowed_roots=roots)

    async def invoke(name: str, args: dict) -> Any:
        chain.check(name, args)
        return await tools[name].execute(args)

    text = cast("str", await invoke("extract_text", {"path": input_path}))
    spans = cast("list[dict]", await invoke("detect_pii", {"text": text}))
    redacted = cast("str", await invoke("redact_pii", {"text": text, "spans": spans}))
    resolved_title = title or Path(input_path).stem
    log.info("pipeline.redact path={path} spans={count}", path=input_path, count=len(spans))
    return cast("str", await invoke("render_markdown", {"text": redacted, "title": resolved_title}))
