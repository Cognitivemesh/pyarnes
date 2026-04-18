"""Tool handlers for the PII redaction pipeline.

The spans-detection here uses simple regex fixtures — a real deployment
would swap ``DetectPii.execute`` for ``presidio_analyzer.AnalyzerEngine``.
"""

from __future__ import annotations

import re

from pyarnes_core.types import ToolHandler
from pyarnes_harness import ToolRegistry

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


class ExtractText(ToolHandler):
    """Return the raw text of the file at ``arguments['path']``.

    A real pipeline would call ``kreuzberg.extract_file``; the stub just
    reads the file so tests can seed deterministic input.
    """

    async def execute(self, arguments: dict) -> str:
        from pathlib import Path  # noqa: PLC0415

        return Path(arguments["path"]).read_text(encoding="utf-8")


class DetectPii(ToolHandler):
    """Return the list of PII spans found in ``arguments['text']``."""

    async def execute(self, arguments: dict) -> list[dict]:
        text = arguments["text"]
        spans: list[dict] = []
        for name, pattern in (("email", EMAIL_PATTERN), ("phone", PHONE_PATTERN), ("ssn", SSN_PATTERN)):
            for match in pattern.finditer(text):
                spans.append({"type": name, "start": match.start(), "end": match.end(), "value": match.group()})
        return spans


class RedactPii(ToolHandler):
    """Replace every detected PII span with its type token."""

    async def execute(self, arguments: dict) -> str:
        text: str = arguments["text"]
        spans: list[dict] = sorted(arguments["spans"], key=lambda s: s["start"], reverse=True)
        for span in spans:
            text = text[: span["start"]] + f"[{span['type'].upper()}]" + text[span["end"] :]
        return text


class RenderMarkdown(ToolHandler):
    """Wrap the redacted text into a minimal markdown document."""

    async def execute(self, arguments: dict) -> str:
        title = arguments.get("title", "Redacted document")
        return f"# {title}\n\n{arguments['text']}\n"


def register_tools(registry: ToolRegistry) -> None:
    """Register every PII-pipeline tool on ``registry``."""
    registry.register("extract_text", ExtractText())
    registry.register("detect_pii", DetectPii())
    registry.register("redact_pii", RedactPii())
    registry.register("render_markdown", RenderMarkdown())
