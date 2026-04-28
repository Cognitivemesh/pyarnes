# ruff: noqa
"""File-summarisation agent — using AgentRuntime.

The same scenario as ``examples/without-pyarnes/agent.py`` but wired through
the pyarnes harness.  Error routing, lifecycle transitions, structured logging,
and guardrails are handled by the framework.

Run:
    uv run python examples/with-pyarnes/agent.py <directory>

Requires:
    pyarnes-core, pyarnes-harness, pyarnes-guardrails (from git URL deps)
    anthropic (or any ModelClient implementation)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from pyarnes_core import UserFixableError
from pyarnes_core.dispatch.ports import ModelClient, ToolHandler
from pyarnes_guardrails import CommandGuardrail, GuardrailChain, PathGuardrail
from pyarnes_harness import AgentRuntime


# ── Tools ─────────────────────────────────────────────────────────────────────


class ListFilesTool(ToolHandler):
    """List all files under a directory."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        root = Path(arguments["path"])
        if not root.is_dir():
            raise UserFixableError(message=f"{arguments['path']!r} is not a directory")
        files = [str(p.relative_to(root)) for p in sorted(root.rglob("*")) if p.is_file()]
        return "\n".join(files) if files else "(empty)"


class ReadFileTool(ToolHandler):
    """Read up to 4 KB of a file."""

    async def execute(self, arguments: dict[str, Any]) -> Any:
        try:
            return Path(arguments["path"]).read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError as exc:
            raise UserFixableError(message=str(exc)) from exc


TOOL_SCHEMAS = [
    {
        "name": "list_files",
        "description": "List all files in a directory recursively.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_file",
        "description": "Read up to 4 KB of a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
    },
]


# ── Minimal Anthropic ModelClient adapter ─────────────────────────────────────


class AnthropicClient(ModelClient):
    """Thin adapter wrapping the Anthropic SDK."""

    def __init__(self) -> None:
        import anthropic  # noqa: PLC0415

        self._client = anthropic.Anthropic()
        self._tools = TOOL_SCHEMAS

    async def next_action(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        import asyncio  # noqa: PLC0415

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                tools=self._tools,
                messages=[m for m in messages if m.get("role") != "system"],
            ),
        )
        if response.stop_reason == "end_turn":
            text = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            return {"type": "final_answer", "content": text}

        for block in response.content:
            if block.type == "tool_use":
                return {
                    "type": "tool_call",
                    "tool": block.name,
                    "id": block.id,
                    "arguments": block.input,
                }
        return {"type": "final_answer", "content": ""}


# ── Main ──────────────────────────────────────────────────────────────────────


async def run(directory: str) -> None:
    """Run the agent against *directory* and print the summary."""
    guardrails = GuardrailChain(
        guardrails=[
            PathGuardrail(allowed_roots=[Path(directory)]),
            CommandGuardrail(),
        ]
    )

    runtime = AgentRuntime(
        tools={"list_files": ListFilesTool(), "read_file": ReadFileTool()},
        model=AnthropicClient(),
        guardrail_chain=guardrails,
        log_json=False,
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Summarise the contents of the directory '{directory}'. "
                "List the files, read the most important ones, then write a "
                "2-3 sentence summary of what the project does."
            ),
        }
    ]

    history = await runtime.run(messages)
    for msg in reversed(history):
        if msg.get("type") == "final_answer":
            print(msg["content"])  # noqa: T201
            break


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <directory>", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))
