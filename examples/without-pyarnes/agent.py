# ruff: noqa
"""File-summarisation agent — raw loop, no harness.

This is the baseline: a minimal agent that reads a directory tree and
reports findings.  Error handling is inline and hardcoded; there is no
lifecycle management, guardrails, or structured logging.

Run:
    python examples/without-pyarnes/agent.py <directory>

Requires:
    pip install anthropic
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


# ── Inline tool definitions ───────────────────────────────────────────────────


def list_files(path: str) -> str:
    """Return a newline-separated list of files under *path*."""
    root = Path(path)
    if not root.is_dir():
        return f"ERROR: {path!r} is not a directory"
    files = [str(p.relative_to(root)) for p in sorted(root.rglob("*")) if p.is_file()]
    return "\n".join(files) if files else "(empty)"


def read_file(path: str) -> str:
    """Return up to 4 KB of *path*."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError as exc:
        return f"ERROR: {exc}"


TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
}

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


# ── Raw loop ──────────────────────────────────────────────────────────────────


def run(directory: str) -> None:
    """Run the agent against *directory* and print the summary."""
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic()
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Summarise the contents of the directory '{directory}'. "
                "List the files, read the most important ones, then write a "
                "2-3 sentence summary of what the project does."
            ),
        }
    ]

    max_iterations = 20
    for _ in range(max_iterations):
        # Retry loop — inline, hardcoded
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1024,
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
                break
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    print(f"Fatal: {exc}", file=sys.stderr)
                    sys.exit(1)
                time.sleep(2**attempt)

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)
            return

        if response.stop_reason != "tool_use":
            print(f"Unexpected stop_reason: {response.stop_reason}", file=sys.stderr)
            sys.exit(1)

        # Append assistant message
        messages.append({"role": "assistant", "content": response.content})

        # Dispatch tool calls — no guardrails, no error taxonomy
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = TOOLS.get(block.name)
            if fn is None:
                result = f"Unknown tool: {block.name}"
            else:
                try:
                    result = fn(**block.input)
                except Exception as exc:  # noqa: BLE001
                    result = f"Error: {exc}"
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": result}
            )

        messages.append({"role": "user", "content": tool_results})

    print("Reached iteration limit without finishing.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <directory>", file=sys.stderr)
        sys.exit(1)
    run(sys.argv[1])
