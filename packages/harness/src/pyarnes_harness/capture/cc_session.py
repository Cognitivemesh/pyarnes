"""Parse Claude Code session transcripts into ``ToolCallEntry`` records.

Claude Code writes a per-session JSONL transcript to
``~/.claude/projects/<cwd-escaped>/<session-id>.jsonl`` — the directory
name is the absolute CWD with every ``/`` replaced by ``-`` (so
``/home/user/pyarnes`` becomes ``-home-user-pyarnes``).

**Schema caveat.** The transcript format is not part of the public
Claude Code surface. This adapter is locked to the shape captured in
``tests/unit/fixtures/cc_session_sample.jsonl``:

* ``type: "assistant"`` carries ``message.content`` as a list; each
  ``{"type": "tool_use", "id", "name", "input"}`` entry is a new call.
  ``message.usage.input_tokens`` / ``output_tokens`` and
  ``message.model`` are present on current CC builds but may not be in
  future versions — callers that care about token accounting should
  check for ``None``.
* ``type: "user"`` carries ``message.content`` as a list containing
  ``{"type": "tool_result", "tool_use_id", "is_error", "content"}``
  entries that pair back to the ``tool_use`` by id.

Tool-use entries without a matching ``tool_result`` (mid-stream reads)
are yielded with ``result=None`` and ``is_error=False``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pyarnes_harness.capture.tool_log import ToolCallEntry

__all__ = ["MAX_TRANSCRIPT_LINE_BYTES", "read_cc_session", "resolve_cc_session_path"]

# 1 MiB per JSONL line is a generous ceiling: even a transcript with a
# full file ``Read`` tool result rarely crosses a few hundred KiB. Any
# line larger than this is almost certainly a malformed / adversarial
# entry and we refuse it rather than risk unbounded memory on
# ``json.loads``.
MAX_TRANSCRIPT_LINE_BYTES = 1_048_576


def resolve_cc_session_path(
    cwd: Path | str | None = None,
    session_id: str | None = None,
    *,
    home: Path | None = None,
) -> Path:
    """Return the transcript path for *cwd* / *session_id*.

    Args:
        cwd: The project directory. Defaults to :func:`Path.cwd`.
        session_id: Specific session file (without ``.jsonl``). When
            ``None``, picks the most recently modified transcript in
            the project directory.
        home: Override for ``~`` — useful in tests.

    Returns:
        The JSONL path. The file may not exist yet; callers are expected
        to check with :meth:`Path.is_file`.

    Raises:
        FileNotFoundError: When *session_id* is ``None`` and the project
            directory has no JSONL transcripts.
    """
    # ``.absolute()`` rather than ``.resolve()`` so we don't touch the
    # filesystem when the caller hands us a non-existent cwd in tests,
    # and so we don't accidentally follow symlinks across trust
    # boundaries.
    target_cwd = Path(cwd).absolute() if cwd is not None else Path.cwd().absolute()
    target_home = home or Path.home()
    escaped = "-" + "-".join(target_cwd.parts[1:]) if target_cwd.parts else "-"
    project_dir = target_home / ".claude" / "projects" / escaped
    if session_id is not None:
        return project_dir / f"{session_id}.jsonl"
    candidates = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        msg = f"No Claude Code transcripts found under {project_dir}"
        raise FileNotFoundError(msg)
    return candidates[0]


def read_cc_session(path: Path) -> Iterator[ToolCallEntry]:
    """Yield one ``ToolCallEntry`` per tool_use in a CC transcript.

    Args:
        path: Path to a CC session JSONL transcript.

    Yields:
        :class:`ToolCallEntry` records (one per assistant ``tool_use``).
        ``started_at`` / ``finished_at`` come from the assistant +
        tool_result line timestamps when available; ``duration_seconds``
        is left at ``0.0`` because CC does not record it explicitly.
    """
    lines = _read_bounded_lines(path)
    results_by_id = _index_tool_results(lines)
    for line in lines:
        if line.get("type") != "assistant":
            continue
        yield from _assistant_tool_uses(line, results_by_id)


def _read_bounded_lines(path: Path) -> list[dict[str, Any]]:
    """Read the transcript into memory, dropping oversize or malformed lines."""
    lines: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            if not raw.strip():
                continue
            if len(raw.encode("utf-8")) > MAX_TRANSCRIPT_LINE_BYTES:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return lines


def _index_tool_results(lines: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return ``{tool_use_id: {content, is_error, timestamp}}`` for every tool result."""
    results_by_id: dict[str, dict[str, Any]] = {}
    for line in lines:
        if line.get("type") != "user":
            continue
        for part in _iter_list(_message_content(line)):
            if part.get("type") != "tool_result":
                continue
            tool_use_id = part.get("tool_use_id")
            if isinstance(tool_use_id, str):
                results_by_id[tool_use_id] = {
                    "content": part.get("content"),
                    "is_error": bool(part.get("is_error", False)),
                    "timestamp": line.get("timestamp"),
                }
    return results_by_id


def _assistant_tool_uses(
    line: dict[str, Any],
    results_by_id: dict[str, dict[str, Any]],
) -> Iterator[ToolCallEntry]:
    """Yield one ``ToolCallEntry`` per ``tool_use`` block in an assistant line."""
    message = line.get("message") or {}
    if not isinstance(message, dict):
        return
    usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
    model = message.get("model") if isinstance(message.get("model"), str) else None
    started_at = str(line.get("timestamp") or "")
    token_in = _int_or_none(usage, "input_tokens") if usage else None
    token_out = _int_or_none(usage, "output_tokens") if usage else None
    for part in _iter_list(message.get("content")):
        if part.get("type") != "tool_use":
            continue
        use_id = part.get("id")
        result = results_by_id.get(use_id) if isinstance(use_id, str) else None
        finished_at = str((result or {}).get("timestamp") or started_at)
        yield ToolCallEntry(
            tool=str(part.get("name", "unknown")),
            arguments=part.get("input", {}) or {},
            result=_stringify(result["content"]) if result else None,
            is_error=bool(result["is_error"]) if result else False,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=0.0,
            token_in=token_in,
            token_out=token_out,
            model=model,
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _message_content(line: dict[str, Any]) -> Any:
    """Return ``line["message"]["content"]`` tolerating the legacy flat shape."""
    message = line.get("message")
    if isinstance(message, dict):
        return message.get("content")
    return None


def _iter_list(value: Any) -> Iterable[dict[str, Any]]:
    """Yield every dict element when *value* is a list of dicts; else nothing."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _stringify(content: Any) -> str:
    """Render a tool_result ``content`` field as a string for logging.

    CC may send a plain string, a list of ``{"type": "text", "text": ...}``
    blocks, or (rarely) other shapes. We collapse list-of-dict content
    to the concatenated ``text`` fields so the ``result`` column is
    greppable.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return json.dumps(content, default=str)


def _int_or_none(data: dict[str, Any], key: str) -> int | None:
    """Coerce ``data[key]`` to ``int`` when it is a number; else ``None``."""
    value = data.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None
