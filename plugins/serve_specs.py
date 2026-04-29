#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "markdown>=3.10",
# ]
# ///
"""Serve the specs tree as a styled local website.

This script renders local markdown files to HTML on demand, preserves relative
links between specs, and serves existing HTML diagrams directly.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import errno
import html
import json
import math
import os
import re
import signal
import socket
import subprocess
import sys
import textwrap
import time
import webbrowser
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, unquote, urlsplit

from markdown import Markdown

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_ROOT = REPO_ROOT / "specs"
CONSOLIDATION_ROOT = SPECS_ROOT / "consolidation"
DIAGRAMS_ROOT = CONSOLIDATION_ROOT / "diagrams"
STYLESHEET_PATH = CONSOLIDATION_ROOT / "assets" / "specs.css"
LANDING_PAGE = SPECS_ROOT / "README.md"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_STYLESHEET = textwrap.dedent(
    """
    :root {
      color-scheme: light;
      --bg: oklch(0.975 0.008 75);
      --panel: oklch(0.986 0.004 75);
      --panel-strong: oklch(0.952 0.012 75);
      --text: oklch(0.27 0.02 55);
      --muted: oklch(0.55 0.016 60);
      --accent: oklch(0.61 0.15 38);
      --line: oklch(0.89 0.009 75);
      --code: oklch(0.95 0.01 75);
    }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
    """
).strip()


@dataclass(frozen=True)
class NavItem:
    """A navigation entry in the viewer sidebar."""

    label: str
    href: str


def _extract_heading_title(path: Path) -> str:
    """Return the first markdown H1 for *path*, falling back to the file stem."""
    stem = path.stem.replace("-", " ")
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        return stem
    return stem


def _nav_href(path: Path) -> str:
    """Return the browser href for a repo-local path."""
    return "/" + path.relative_to(REPO_ROOT).as_posix()


def _collect_markdown_items(root: Path) -> list[NavItem]:
    """Return sorted markdown items below *root*."""
    items: list[NavItem] = []

    def _sort_key(path: Path) -> tuple[int, str]:
        if root == CONSOLIDATION_ROOT:
            prefix = path.stem.split("-", 1)[0]
            if prefix.isdigit():
                return (int(prefix), path.name)
        return (999, path.name)

    for path in sorted(root.glob("*.md"), key=_sort_key):
        if path.name == "README.md":
            continue
        label = path.name.removesuffix(".md")
        items.append(NavItem(label=label, href=_nav_href(path)))
    return items


def _collect_diagram_items(root: Path) -> list[NavItem]:
    """Return sorted HTML diagram entries below *root*."""
    items: list[NavItem] = []
    for path in sorted(root.glob("*.html")):
        label = path.stem.replace("-", " ")
        items.append(NavItem(label=label, href=_nav_href(path)))
    return items


def _load_stylesheet() -> str:
    """Return the viewer stylesheet, or a minimal fallback while developing."""
    try:
        return STYLESHEET_PATH.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_STYLESHEET


def _directory_target(directory: Path) -> str | None:
    """Return the preferred landing target for a directory request."""
    readme = directory / "README.md"
    if readme.is_file():
        return _nav_href(readme)

    markdown_files = sorted(directory.glob("*.md"))
    if markdown_files:
        return _nav_href(markdown_files[0])

    html_files = sorted(directory.glob("*.html"))
    if html_files:
        return _nav_href(html_files[0])

    return None


_NAV_ICONS: dict[str, str] = {
    "Overview": "house",
    "Consolidation": "book-open",
    "Diagrams": "workflow",
}


# Authored data for the three interactive artifacts. Lives here (not in
# markdown) so spec content stays free of widget data. Consumed by
# specs.js via the JSON data island emitted in _render_data_island.

ERROR_TREE_DATA: list[dict[str, object]] = [
    {
        "id": "transient",
        "question": "Did the call hit the network or a transient resource?",
        "yes_terminal": {
            "kind": "TransientError",
            "summary": "Retry with exponential backoff (cap: 2 attempts).",
            "snippet": (
                "from pyarnes_core.errors import TransientError\n\n"
                'raise TransientError("upstream API timeout")'
            ),
        },
        "no_next": "recoverable",
    },
    {
        "id": "recoverable",
        "question": "Can the loop recover by feeding the message back to the model?",
        "yes_terminal": {
            "kind": "LLMRecoverableError",
            "summary": "Return as a ToolMessage so the model adjusts on the next step.",
            "snippet": (
                "from pyarnes_core.errors import LLMRecoverableError\n\n"
                'raise LLMRecoverableError("unknown tool: foo")'
            ),
        },
        "no_next": "user",
    },
    {
        "id": "user",
        "question": "Does it require a human decision (auth, missing config, ambiguity)?",
        "yes_terminal": {
            "kind": "UserFixableError",
            "summary": "Interrupt the loop for human input.",
            "snippet": (
                "from pyarnes_core.errors import UserFixableError\n\n"
                'raise UserFixableError("missing API key for provider X")'
            ),
        },
        "no_terminal": {
            "kind": "UnexpectedError",
            "summary": "Bubble up the original exception for debugging.",
            "snippet": "raise  # let the framework surface the traceback",
        },
    },
]

FSM_DATA: dict[str, object] = {
    "states": [
        {"id": "created", "label": "created", "kind": "initial",
         "summary": "Swarm has been instantiated; no iterations have run yet."},
        {"id": "running", "label": "running", "kind": "active",
         "summary": "Loop is executing; tools may be dispatched."},
        {"id": "paused", "label": "paused", "kind": "active",
         "summary": "Loop is held; resumes on the next steering signal."},
        {"id": "done", "label": "done", "kind": "terminal",
         "summary": "Loop completed normally."},
        {"id": "failed", "label": "failed", "kind": "terminal",
         "summary": "Loop hit an UnexpectedError and stopped."},
        {"id": "interrupted", "label": "interrupted", "kind": "terminal",
         "summary": "Loop was halted by an external signal or UserFixableError."},
    ],
    "transitions": [
        {"from": "created", "to": "running", "trigger": "Swarm.run()"},
        {"from": "running", "to": "paused", "trigger": "Swarm.pause() / steer(Pause)"},
        {"from": "paused", "to": "running", "trigger": "Swarm.resume() / steer(Resume)"},
        {"from": "running", "to": "done", "trigger": "loop reaches terminal step"},
        {"from": "running", "to": "failed", "trigger": "UnexpectedError raised"},
        {"from": "running", "to": "interrupted", "trigger": "Swarm.interrupt() / UserFixableError"},
        {"from": "paused", "to": "interrupted", "trigger": "Swarm.interrupt()"},
    ],
    "guarantees": [
        "Terminal states (done, failed, interrupted) are mutually exclusive.",
        "Once terminal, the Swarm cannot be resumed; create a new instance.",
    ],
}

HOOK_WIRING_DATA: list[dict[str, str]] = [
    {
        "event": "PreToolUse",
        "handler": "IterationBudget.reserve",
        "artifact": "Reserved tokens for the about-to-run tool call.",
        "location": ".pyarnes/hooks/pre_tool_use.py",
    },
    {
        "event": "PostToolUse",
        "handler": "IterationBudget.refund + RunLogger.append",
        "artifact": "Refunded unused reservation; appended ToolResult event to the run log.",
        "location": ".pyarnes/hooks/post_tool_use.py",
    },
    {
        "event": "Stop",
        "handler": "RunLogger.finalise",
        "artifact": "Sealed run log written to .pyarnes/runs/<id>.jsonl.",
        "location": ".pyarnes/hooks/stop.py",
    },
]


# Reading-time / last-edited / spec-header helpers (step 2 + 3 + 4b)
#
# All three live close together so the related parsing logic is easy to
# evolve without spelunking. None of them mutates global state — every
# helper takes its inputs explicitly so unit tests can pin behaviour.


@dataclass(frozen=True)
class SpecMeta:
    """Lightweight metadata rendered as a chip below each H1."""

    reading_minutes: int
    section_count: int
    last_edited_relative: str | None  # None = untracked or git unavailable


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _word_count(html_text: str) -> int:
    """Count word-like tokens in rendered HTML (tags stripped)."""
    plain = _HTML_TAG_RE.sub(" ", html_text)
    return len(_WORD_RE.findall(plain))


@lru_cache(maxsize=64)
def _git_relative_mtime(path_str: str, _mtime_key: int) -> str | None:
    """`git log -1 --format=%ar -- <path>`. None if untracked or git missing."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ar", "--", path_str],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            cwd=REPO_ROOT,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    line = result.stdout.strip()
    return line or None


def _compute_spec_meta(path: Path, body_html: str) -> SpecMeta:
    """Derive reading-time, section count, and git mtime for one rendered page."""
    words = _word_count(body_html)
    reading_minutes = max(1, math.ceil(words / 220)) if words > 0 else 1
    section_count = len(re.findall(r"<h2\b", body_html))
    try:
        mtime_ns = path.stat().st_mtime_ns
        last_edited = _git_relative_mtime(str(path), mtime_ns)
    except OSError:
        last_edited = None
    return SpecMeta(
        reading_minutes=reading_minutes,
        section_count=section_count,
        last_edited_relative=last_edited,
    )


def _inject_spec_meta(body_html: str, meta: SpecMeta) -> str:
    """Insert <div class='spec-meta'>...</div> right after the first </h1>."""
    closing = "</h1>"
    idx = body_html.find(closing)
    if idx < 0:
        return body_html
    insert_at = idx + len(closing)
    parts = [
        f'<span class="spec-meta-item"><i data-lucide="clock" aria-hidden="true"></i>{meta.reading_minutes} min read</span>',
        f'<span class="spec-meta-item"><i data-lucide="list-tree" aria-hidden="true"></i>{meta.section_count} sections</span>',
    ]
    if meta.last_edited_relative:
        parts.append(
            f'<span class="spec-meta-item"><i data-lucide="git-commit" aria-hidden="true"></i>last edited {html.escape(meta.last_edited_relative)}</span>'
        )
    chip = f'<div class="spec-meta">{"".join(parts)}</div>'
    return body_html[:insert_at] + chip + body_html[insert_at:]


# --- Spec header parsing (step 3) ---


@dataclass(frozen=True)
class SpecHeader:
    """Parsed `> **Spec header**` blockquote table for one spec."""

    title: str | None = None
    status: str | None = None  # "active" / "draft" / "deprecated"
    type: str | None = None
    tags: tuple[str, ...] = ()
    owns: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    extends: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    read_after: tuple[str, ...] = ()
    read_before: tuple[str, ...] = ()
    not_owned_here: tuple[str, ...] = ()
    last_reviewed: str | None = None


_HEADER_TABLE_ROW_RE = re.compile(r"^>\s*\|\s*\*\*(?P<field>[^*]+)\*\*\s*\|\s*(?P<value>.+?)\s*\|\s*$")
_SPEC_REF_RE = re.compile(r"\b(\d{2})(?:-[a-z][a-z0-9-]*)?(?:\.md)?\b")


def _split_csv(value: str) -> tuple[str, ...]:
    """Split a free-form value on `,` or `;`, trim, dedupe (preserve order)."""
    parts = re.split(r"[;,]", value)
    seen: list[str] = []
    out: list[str] = []
    for raw in parts:
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.append(item)
        out.append(item)
    return tuple(out)


def _split_tags(value: str) -> tuple[str, ...]:
    """Tags are normalised (lowercased, deduped, trimmed)."""
    parts = re.split(r"[;,]", value)
    seen: set[str] = set()
    out: list[str] = []
    for raw in parts:
        item = raw.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return tuple(out)


# Folds near-synonyms into canonical tags so the topic-chip strip stays small.
# Applied at every read of spec-header tags via `_canonicalize_tags`, so the
# canonical form propagates to sidebar `data-tags`, dep-graph `tagSet`, and
# topic-chip counts in lockstep.
_TAG_ALIASES: dict[str, str] = {
    "hooks": "lifecycle",
    "in-process": "lifecycle",
    "guardrails": "safety",
    "cleanup": "audit",
    "dead-code": "audit",
    "complexity": "audit",
    "tdd": "testing",
    "strategy": "testing",
    "governance": "api",
    "budget": "cost",
    "tokens": "cost",
    "limits": "cost",
}


def _canonicalize_tags(tags: Iterable[str]) -> list[str]:
    """Map each tag through `_TAG_ALIASES` and dedupe while preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        canonical = _TAG_ALIASES.get(raw, raw)
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def _split_spec_refs(value: str) -> tuple[str, ...]:
    """Pull `NN-name.md` / `NN-name` / `NN` references from a value cell."""
    matches = _SPEC_REF_RE.findall(value)
    seen: list[str] = []
    out: list[str] = []
    for prefix in matches:
        if prefix in seen:
            continue
        seen.append(prefix)
        out.append(prefix)
    return tuple(out)


@lru_cache(maxsize=64)
def _extract_spec_header(path_str: str, _mtime_key: int) -> SpecHeader | None:
    """Parse the `> **Spec header**` blockquote in *path*.

    Returns None if no header block is detected. Specs without the
    convention contribute no metadata; the rest of the viewer keeps
    working.
    """
    try:
        text = Path(path_str).read_text(encoding="utf-8")
    except OSError:
        return None
    # Only consider the first block-level chunk that starts with the marker.
    lines = text.splitlines()
    in_block = False
    rows: dict[str, str] = {}
    saw_marker = False
    for line in lines:
        stripped = line.rstrip()
        if not saw_marker:
            if re.match(r"^>\s*\*\*Spec header\*\*\s*$", stripped):
                saw_marker = True
                in_block = True
            continue
        if not stripped.startswith(">"):
            # Empty line or end of blockquote terminates parsing.
            break
        match = _HEADER_TABLE_ROW_RE.match(stripped)
        if not match:
            continue
        field_name = match.group("field").strip().lower()
        value = match.group("value").strip()
        rows[field_name] = value

    if not saw_marker or not rows:
        return None

    return SpecHeader(
        title=rows.get("title"),
        status=rows.get("status"),
        type=rows.get("type"),
        tags=_split_tags(rows.get("tags", "")),
        owns=_split_csv(rows.get("owns", "")),
        depends_on=_split_spec_refs(rows.get("depends on", "")),
        extends=_split_spec_refs(rows.get("extends", "")),
        supersedes=_split_spec_refs(rows.get("supersedes", "")),
        read_after=_split_spec_refs(rows.get("read after", "")),
        read_before=_split_spec_refs(rows.get("read before", "")),
        not_owned_here=_split_spec_refs(rows.get("not owned here", "")),
        last_reviewed=rows.get("last reviewed"),
    )


def _spec_header_for(path: Path) -> SpecHeader | None:
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None
    return _extract_spec_header(str(path), mtime_ns)


def _all_spec_headers() -> dict[str, dict[str, object]]:
    """Map slug → header dict for every consolidation spec that has a header."""
    headers: dict[str, dict[str, object]] = {}
    for path in sorted(CONSOLIDATION_ROOT.glob("*.md")):
        if path.name == "README.md":
            continue
        header = _spec_header_for(path)
        if header is None:
            continue
        headers[path.stem] = {
            "title": header.title,
            "status": header.status,
            "type": header.type,
            "tags": _canonicalize_tags(header.tags),
            "owns": list(header.owns),
            "depends_on": list(header.depends_on),
            "extends": list(header.extends),
            "supersedes": list(header.supersedes),
            "read_after": list(header.read_after),
            "read_before": list(header.read_before),
            "not_owned_here": list(header.not_owned_here),
            "last_reviewed": header.last_reviewed,
        }
    return headers


def _all_topic_chips(min_count: int = 3) -> list[tuple[str, int]]:
    """Aggregate (tag, count) pairs across every spec, descending by count.

    Tags appearing in fewer than ``min_count`` specs are dropped — single-
    and double-spec tags add chip-strip noise without usefully partitioning
    the corpus. The threshold operates on canonicalized tags (see
    `_canonicalize_tags`), so synonym folding compounds with the filter.
    """
    counts: dict[str, int] = {}
    for header_dict in _all_spec_headers().values():
        for tag in header_dict.get("tags", []) or []:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(
        ((tag, n) for tag, n in counts.items() if n >= min_count),
        key=lambda kv: (-kv[1], kv[0]),
    )


# --- Spec-card transformation (step 4b) ---


def _staleness_class(last_reviewed_iso: str | None, today: _dt.date | None = None) -> tuple[str, str]:
    """Compute (className-suffix, label) from an ISO date.

    ≤30 days → "recent" / "✓ recent"
    31–90 days → "stale" / "⏱ stale"
    >90 days → "very-stale" / "⚠ very stale"
    None or unparseable → "missing" / "· last-reviewed missing"
    """
    if not last_reviewed_iso:
        return ("missing", "· last-reviewed missing")
    try:
        when = _dt.date.fromisoformat(last_reviewed_iso.strip())
    except ValueError:
        return ("missing", "· last-reviewed missing")
    today = today or _dt.date.today()
    age = (today - when).days
    if age <= 30:
        return ("recent", "✓ recent")
    if age <= 90:
        return ("stale", "⏱ stale")
    return ("very-stale", "⚠ very stale")


def _resolve_spec_ref(text: str, page_index: dict[str, PageEntry]) -> tuple[str, str] | None:
    """Resolve `04-swarm-api.md` / `04-swarm-api` / `04` to (href, slug)."""
    if not text:
        return None
    match = _SPEC_REF_RE.match(text.strip())
    if not match:
        return None
    prefix = match.group(1)
    for slug, entry in page_index.items():
        if slug.startswith(f"{prefix}-"):
            return (entry.href, slug)
    return None


def _render_spec_card(
    header: SpecHeader,
    slug: str,
    page_index: dict[str, PageEntry],
) -> str:
    """Replace the > **Spec header** blockquote with an interactive card."""
    title = html.escape(header.title or slug)
    status = (header.status or "").lower() or "unknown"
    status_label = html.escape(status)
    type_class = re.sub(r"[^a-z0-9]+", "-", (header.type or "unknown").lower()).strip("-") or "unknown"
    type_label = html.escape(header.type or "—")
    stale_class, stale_label = _staleness_class(header.last_reviewed)

    parts: list[str] = []
    parts.append(f'<aside class="spec-card" x-data="{{ open: $persist(true).as(\'spec-header.{html.escape(slug)}\') }}">')
    parts.append('  <header class="spec-card-head">')
    parts.append(f'    <h2 class="spec-card-title">{title}</h2>')
    parts.append('    <div class="spec-card-badges">')
    parts.append(f'      <span class="spec-status spec-status--{html.escape(status)}">{status_label}</span>')
    if header.type:
        parts.append(
            f'      <a class="spec-type-chip spec-type--{type_class}" href="?type={html.escape(header.type)}">{type_label}</a>'
        )
    parts.append(
        f'      <span class="spec-staleness spec-staleness--{stale_class}" title="Last reviewed: {html.escape(header.last_reviewed or "unknown")}">{stale_label}</span>'
    )
    parts.append("    </div>")
    parts.append(
        '    <button class="spec-card-toggle" @click="open = !open" :aria-label="open ? \'Collapse spec header\' : \'Expand spec header\'">'
    )
    parts.append('      <i data-lucide="chevron-up" :class="{ \'is-flipped\': !open }" aria-hidden="true"></i>')
    parts.append("    </button>")
    parts.append("  </header>")

    parts.append('  <div class="spec-card-body" x-show="open" x-transition>')

    if header.tags:
        parts.append('    <div class="spec-card-row">')
        parts.append('      <span class="spec-card-label">Topics</span>')
        parts.append('      <ul class="spec-card-tags">')
        for tag in header.tags:
            parts.append(
                f'        <li><a class="spec-tag" href="?tag={html.escape(tag)}"><i data-lucide="tag" aria-hidden="true"></i>{html.escape(tag)}</a></li>'
            )
        parts.append("      </ul>")
        parts.append("    </div>")

    if header.owns:
        parts.append('    <div class="spec-card-row spec-card-row--block">')
        parts.append('      <span class="spec-card-label">Owns</span>')
        parts.append('      <ul class="spec-card-owns">')
        for item in header.owns:
            parts.append(f'        <li>{html.escape(item)}</li>')
        parts.append("      </ul>")
        parts.append("    </div>")

    def _refs_block(label: str, refs: tuple[str, ...]) -> None:
        if not refs:
            return
        parts.append('    <div class="spec-card-row">')
        parts.append(f'      <span class="spec-card-label">{html.escape(label)}</span>')
        parts.append('      <ul class="spec-card-refs">')
        for prefix in refs:
            target = _resolve_spec_ref(prefix, page_index)
            if target is None:
                parts.append(f'        <li>{html.escape(prefix)}</li>')
                continue
            href, target_slug = target
            label_text = html.escape(target_slug)
            parts.append(
                f'        <li><a class="spec-ref" href="{html.escape(href)}" x-data x-spec-preview="{html.escape(target_slug)}">{label_text}</a></li>'
            )
        parts.append("      </ul>")
        parts.append("    </div>")

    _refs_block("Depends on", header.depends_on)
    _refs_block("Extends", header.extends)
    _refs_block("Supersedes", header.supersedes)
    _refs_block("Read after", header.read_after)
    _refs_block("Read before", header.read_before)
    _refs_block("Not owned here", header.not_owned_here)

    if header.last_reviewed:
        parts.append('    <div class="spec-card-row">')
        parts.append('      <span class="spec-card-label">Last reviewed</span>')
        parts.append(f'      <span class="spec-card-value">{html.escape(header.last_reviewed)}</span>')
        parts.append("    </div>")

    parts.append('    <footer class="spec-card-actions">')
    parts.append(
        f'      <button class="spec-card-button" type="button" @click="$dispatch(\'dep-graph-open\', {{ focus: \'{html.escape(slug)}\' }})"><i data-lucide="network" aria-hidden="true"></i>Open in dep-graph</button>'
    )
    if header.read_after:
        target = _resolve_spec_ref(header.read_after[0], page_index)
        if target is not None:
            href, target_slug = target
            parts.append(
                f'      <a class="spec-card-button" href="{html.escape(href)}"><i data-lucide="arrow-left" aria-hidden="true"></i>Read first: {html.escape(target_slug)}</a>'
            )
    if header.read_before:
        target = _resolve_spec_ref(header.read_before[0], page_index)
        if target is not None:
            href, target_slug = target
            parts.append(
                f'      <a class="spec-card-button" href="{html.escape(href)}">Read next: {html.escape(target_slug)}<i data-lucide="arrow-right" aria-hidden="true"></i></a>'
            )
    parts.append("    </footer>")
    parts.append("  </div>")
    parts.append("</aside>")
    return "\n".join(parts)


_SPEC_HEADER_BLOCKQUOTE_RE = re.compile(
    r"<blockquote>\s*(?:<p>)?\s*<strong>Spec header</strong>.*?</blockquote>",
    re.DOTALL,
)


def _replace_spec_header_blockquote(body_html: str, slug: str, header: SpecHeader, page_index: dict[str, PageEntry]) -> str:
    """Swap the rendered blockquote for the styled card. No-op if missing."""
    card_html = _render_spec_card(header, slug, page_index)
    new_html, count = _SPEC_HEADER_BLOCKQUOTE_RE.subn(card_html, body_html, count=1)
    return new_html if count > 0 else body_html


# --- Related specs panel (step 12) ---


def _render_related_specs(
    slug: str,
    deps: dict[str, list[str]],
    page_index: dict[str, PageEntry],
) -> str:
    """Two stacked lists below the TOC: downstream + upstream cross-refs."""
    if not slug or slug not in page_index or not deps:
        return ""
    match = re.match(r"^(\d{2})-", slug)
    if match is None:
        return ""
    prefix = match.group(1)
    downstream = deps.get(prefix, [])
    upstream = [src for src, targets in deps.items() if prefix in targets]
    if not downstream and not upstream:
        return ""

    def _link_for(p: str) -> str:
        target = _resolve_spec_ref(p, page_index)
        if target is None:
            return html.escape(p)
        href, slug_target = target
        return f'<a class="spec-ref" href="{html.escape(href)}" x-data x-spec-preview="{html.escape(slug_target)}">{html.escape(slug_target)}</a>'

    parts: list[str] = ['<section class="related-specs">']
    parts.append(
        '  <p class="eyebrow"><i data-lucide="git-merge" aria-hidden="true"></i>Related specs</p>'
    )
    if downstream:
        parts.append('  <p class="related-specs-label">Re-read when this changes</p>')
        parts.append('  <ul class="related-specs-list">')
        for prefix_id in downstream:
            parts.append(f'    <li>{_link_for(prefix_id)}</li>')
        parts.append("  </ul>")
    if upstream:
        parts.append('  <p class="related-specs-label">This page re-reads</p>')
        parts.append('  <ul class="related-specs-list">')
        for prefix_id in upstream:
            parts.append(f'    <li>{_link_for(prefix_id)}</li>')
        parts.append("  </ul>")
    parts.append("</section>")
    return "\n".join(parts)


# --- Server-side task-list conversion (step 4 / Alpine checklist) ---


_TASK_LI_RE = re.compile(r'<li>\s*\[([ xX])\]\s+(.*?)</li>', re.DOTALL)


def _convert_task_list_items(body_html: str, slug: str) -> str:
    """Turn `<li>[ ] foo</li>` into Alpine-bound checklist items.

    Positional `task-N` keys per spec-slug — documented trade-off: reordering
    markdown drifts state. Acceptable for spec content.
    """
    counter = {"i": 0}

    def _rewrite(match: re.Match[str]) -> str:
        marker = match.group(1).lower() == "x"
        text = match.group(2)
        idx = counter["i"]
        counter["i"] += 1
        key = f"checklist.{slug}.task-{idx}"
        return (
            f'<li class="checklist-item" x-data="{{ checked: $persist({str(marker).lower()}).as(\'{key}\') }}" '
            f':class="{{ \'is-checked\': checked }}">'
            f'<input type="checkbox" class="checklist-checkbox" x-model="checked"> '
            f'{text}</li>'
        )

    return _TASK_LI_RE.sub(_rewrite, body_html)


# Parses the dependency-map table in 00-overview.md. The table format is
# `| **NN** name | comma-separated NNs |` and lives under a `### Dependency
# map` heading; we stop at the next `## ` heading so trailing tables can't
# leak in. lru_cache because the file is read once per server boot.
_DEP_ROW_RE = re.compile(
    r"^\|\s*\*\*(\d{2})\*\*\s+[^|]+?\s*\|\s*([^|]+?)\s*\|\s*$",
)
_DEP_TARGET_RE = re.compile(r"\d{2}")


@lru_cache(maxsize=4)
def _extract_dependency_edges(overview_path: str) -> dict[str, list[str]]:
    """Return a mapping from spec id to its dependents (re-read on change).

    Silent on missing files / missing sections — the dep-graph drawer
    self-disables in the JS rather than crashing the server.
    """
    edges: dict[str, list[str]] = {}
    try:
        text = Path(overview_path).read_text(encoding="utf-8")
    except OSError:
        return edges

    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "### Dependency map":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        match = _DEP_ROW_RE.match(line)
        if match is None:
            continue
        edges[match.group(1)] = _DEP_TARGET_RE.findall(match.group(2))
    return edges


@dataclass(frozen=True)
class PageEntry:
    """A page exposed to the JS index (sidebar entries + diagrams)."""

    slug: str
    title: str
    group: str
    href: str


def _build_page_entries() -> list[PageEntry]:
    """Return every navigable page the JS index needs."""
    entries: list[PageEntry] = [
        PageEntry(
            slug="readme",
            title=_extract_heading_title(LANDING_PAGE),
            group="Overview",
            href=_nav_href(LANDING_PAGE),
        ),
    ]
    for path in sorted(CONSOLIDATION_ROOT.glob("*.md")):
        if path.name == "README.md":
            continue
        entries.append(
            PageEntry(
                slug=path.stem,
                title=_extract_heading_title(path),
                group="Consolidation",
                href=_nav_href(path),
            )
        )
    for path in sorted(DIAGRAMS_ROOT.glob("*.html")):
        entries.append(
            PageEntry(
                slug=path.stem,
                title=path.stem.replace("-", " "),
                group="Diagrams",
                href=_nav_href(path),
            )
        )
    return entries


def _diagram_parent_spec(diagram_path: Path) -> NavItem | None:
    """Return the consolidation spec a diagram belongs to, by `NN-` prefix.

    `07-lifecycle-fsm.html` → the spec starting with `04-` (swarm-api).
    Returns None if the leading token isn't numeric or no spec matches.
    """
    stem = diagram_path.stem
    prefix = stem.split("-", 1)[0]
    if not prefix.isdigit():
        return None
    matches = sorted(CONSOLIDATION_ROOT.glob(f"{prefix}-*.md"))
    if not matches:
        return None
    spec = matches[0]
    return NavItem(label=_extract_heading_title(spec), href=_nav_href(spec))


def _diagram_back_button(diagram_path: Path) -> str:
    """Return the HTML snippet injected into served diagram pages.

    Adds a fixed-position pill at the top-left linking back to the
    diagram's parent spec (or the specs index if no parent maps).
    Self-contained — does not depend on specs.css or Lucide.
    """
    parent = _diagram_parent_spec(diagram_path)
    parent_href = parent.href if parent else _nav_href(LANDING_PAGE)
    parent_label = parent.label if parent else "Specs index"
    return textwrap.dedent(
        f"""
        <style>
          .specs-back-button {{
            position: fixed;
            top: 1rem;
            left: 1rem;
            z-index: 9999;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.45rem 0.8rem 0.45rem 0.6rem;
            border: 1px solid #d8d4cd;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.92);
            backdrop-filter: blur(8px);
            color: #4a3221;
            font: 500 0.85rem/1.2 -apple-system, "Segoe UI", system-ui, sans-serif;
            text-decoration: none;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            transition: background-color 150ms ease, color 150ms ease, transform 150ms ease;
          }}
          .specs-back-button:hover {{
            background: #fff;
            color: #b34f1d;
            transform: translateX(-1px);
          }}
          .specs-back-button svg {{
            width: 14px;
            height: 14px;
          }}
          @media print {{
            .specs-back-button {{ display: none !important; }}
          }}
        </style>
        <a class="specs-back-button" href="{html.escape(parent_href)}" aria-label="Back to {html.escape(parent_label)}">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          <span>{html.escape(parent_label)}</span>
        </a>
        """
    ).strip()


def _inject_diagram_back_button(html_text: str, diagram_path: Path) -> str:
    """Insert the back-button snippet immediately after the diagram's <body>."""
    snippet = _diagram_back_button(diagram_path)
    lower = html_text.lower()
    body_open = lower.find("<body")
    if body_open == -1:
        return snippet + "\n" + html_text
    body_end = html_text.find(">", body_open)
    if body_end == -1:
        return snippet + "\n" + html_text
    return html_text[: body_end + 1] + "\n" + snippet + "\n" + html_text[body_end + 1 :]


def _render_data_island(current_path: Path) -> str:
    """Return the JSON data island consumed by specs.js."""
    pages = [asdict(entry) for entry in _build_page_entries()]
    current_slug = "readme" if current_path == LANDING_PAGE else current_path.stem
    payload: dict[str, object] = {
        "pages": pages,
        "current": current_slug,
        "deps": _extract_dependency_edges(str(CONSOLIDATION_ROOT / "00-overview.md")),
        "spec_headers": _all_spec_headers(),
        "topic_chips": _all_topic_chips(),
        "artifacts": {
            "error-tree": ERROR_TREE_DATA,
            "lifecycle-fsm": FSM_DATA,
            "hook-wiring": HOOK_WIRING_DATA,
        },
    }
    serialized = json.dumps(payload, separators=(",", ":"))
    # Defang any literal "</" so the JSON cannot break out of its host
    # <script> tag (HTML5 §4.12.1.3). The JS side reverses this on parse.
    serialized = serialized.replace("</", "<\\/")
    return f'<script id="__specs_index__" type="application/json">{serialized}</script>'


def _render_nav(current_path: Path) -> str:
    """Render the left-hand navigation panel.

    Each nav item is wrapped in an `<li class="nav-link-wrapper" data-tags="...">`
    so the Alpine-powered Topics filter can toggle visibility based on tags.
    """
    sections = [
        (
            "Overview",
            [NavItem(label="Specs Home", href=_nav_href(LANDING_PAGE))],
        ),
        ("Consolidation", _collect_markdown_items(CONSOLIDATION_ROOT)),
        ("Diagrams", _collect_diagram_items(DIAGRAMS_ROOT)),
    ]
    headers = _all_spec_headers()
    chunks: list[str] = []
    current_href = _nav_href(current_path)
    for heading, items in sections:
        icon = _NAV_ICONS.get(heading, "folder")
        item_markup: list[str] = []
        for item in items:
            active = " is-active" if item.href == current_href else ""
            # Tag attribute drives the Alpine sidebar Topics filter.
            slug = item.href.rsplit("/", 1)[-1].removesuffix(".md").removesuffix(".html")
            tag_list = headers.get(slug, {}).get("tags", []) if slug in headers else []
            data_tags = ",".join(tag_list) if tag_list else ""
            tags_attr = f' data-tags="{html.escape(data_tags)}"' if data_tags else ""
            visibility_attr = (
                ' :class="{ \'is-hidden\': tags.length > 0 && '
                "!tags.some(t => ($el.dataset.tags || '').split(',').includes(t)) "
                '}"'
                if data_tags
                else ""
            )
            item_markup.append(
                f'<li class="nav-link-wrapper"{tags_attr}{visibility_attr}>'
                f'<a class="nav-link{active}" href="{html.escape(item.href)}">{html.escape(item.label)}</a>'
                f'</li>'
            )
        chunks.append(
            "\n".join(
                [
                    '<section class="nav-group">',
                    f'  <h2 class="nav-heading"><i data-lucide="{icon}" aria-hidden="true"></i>{html.escape(heading)}</h2>',
                    '  <ul class="nav-list">',
                    *[f"    {line}" for line in item_markup],
                    '  </ul>',
                    '</section>',
                ]
            )
        )
    return "\n".join(chunks)


def _render_topic_chips(topic_chips: list[tuple[str, int]]) -> str:
    """Topics filter: Alpine multi-select chip strip above the sidebar nav."""
    if not topic_chips:
        return ""
    chip_lines: list[str] = []
    for tag, count in topic_chips:
        tag_safe = html.escape(tag)
        chip_lines.append(
            f'<li><button type="button" class="topic-chip" '
            f':class="{{ \'is-active\': tags.includes(\'{tag_safe}\') }}" '
            f'@click="tags = tags.includes(\'{tag_safe}\') '
            f'? tags.filter(t => t !== \'{tag_safe}\') '
            f': [...tags, \'{tag_safe}\']">'
            f'<span>{tag_safe}</span> <span class="topic-count">{count}</span>'
            f'</button></li>'
        )
    chips_html = "\n      ".join(chip_lines)
    return (
        '<div class="sidebar-tags-filter">\n'
        '  <p class="eyebrow">'
        '<i data-lucide="tag" aria-hidden="true"></i>'
        '<span>Topics</span>'
        '<button type="button" x-show="tags.length > 0" @click="tags = []" class="topic-clear">Clear</button>'
        '</p>\n'
        '  <ul class="sidebar-tag-chips">\n'
        f'      {chips_html}\n'
        '  </ul>\n'
        '</div>'
    )


def _build_markdown() -> Markdown:
    """Return a configured Markdown renderer."""
    return Markdown(
        extensions=[
            "extra",
            "admonition",
            "toc",
            "sane_lists",
            "smarty",
        ],
        extension_configs={
            "toc": {
                "anchorlink": True,
                "permalink": True,
                "permalink_title": "Link to this section",
            },
        },
        output_format="html5",
    )


def _render_template(*, current_path: Path, body_html: str, toc_html: str, title: str) -> str:
    """Render the full page shell for a markdown document."""
    rel_path = current_path.relative_to(REPO_ROOT).as_posix()
    raw_href = f"{_nav_href(current_path)}?raw=1"
    toc_panel = (
        toc_html
        if toc_html.strip() and toc_html.strip() != '<div class="toc">\n<ul></ul>\n</div>'
        else '<p class="toc-empty">No section outline on this page.</p>'
    )
    data_island = _render_data_island(current_path)

    # Slug + helpers for downstream renderers.
    slug = "readme" if current_path == LANDING_PAGE else current_path.stem
    deps = _extract_dependency_edges(str(CONSOLIDATION_ROOT / "00-overview.md"))
    page_index = {entry.slug: entry for entry in _build_page_entries()}
    related_specs_html = _render_related_specs(slug, deps, page_index)
    topic_chips_html = _render_topic_chips(_all_topic_chips())

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{html.escape(title)} · pyarnes specs</title>
  <link rel="stylesheet" href="/specs/consolidation/assets/specs.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/plugins/line-numbers/prism-line-numbers.min.css">
  <script src="https://cdn.jsdelivr.net/npm/lucide@latest/dist/umd/lucide.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@2/dist/htmx.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/@alpinejs/persist@3.x.x/dist/cdn.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-core.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/plugins/autoloader/prism-autoloader.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/prismjs@1.29.0/plugins/line-numbers/prism-line-numbers.min.js"></script>
  <script defer src="https://d3js.org/d3.v7.min.js" integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i" crossorigin="anonymous"></script>
  <script>
    // Tell the autoloader where to pull missing language grammars from.
    window.addEventListener('DOMContentLoaded', () => {{
      if (window.Prism && Prism.plugins && Prism.plugins.autoloader) {{
        Prism.plugins.autoloader.languages_path = 'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/';
      }}
    }});
  </script>
</head>
<body>
  <div class=\"progress-rail\" aria-hidden=\"true\"></div>
  <div class=\"app-shell\">
    <aside class=\"sidebar\" x-data=\"{{ tags: $persist([]).as('sidebar.tags') }}\" x-init=\"(new URLSearchParams(location.search).get('tag')) && (tags = [new URLSearchParams(location.search).get('tag')])\">
      <div class=\"sidebar-chrome\">
        <p class=\"eyebrow\">Local browser viewer</p>
        <h1 class=\"brand\">pyarnes specs</h1>
        <p class=\"sidebar-copy\">Browse the consolidation set, the appendices, and the hand-drawn runtime diagrams without building the full docs site.</p>
      </div>
      {topic_chips_html}
      <nav class=\"sidebar-nav\" aria-label=\"Spec navigation\">
        {_render_nav(current_path)}
      </nav>
    </aside>

    <main class=\"main-panel\">
      <header class=\"topbar\">
        <div>
          <p class=\"eyebrow\">Current file</p>
          <p class=\"path-label\">{html.escape(rel_path)}</p>
        </div>
        <div class=\"topbar-actions\">
          <button type=\"button\" class=\"cmdk-trigger\" data-specs-action=\"open-palette\" hidden><i data-lucide=\"search\" aria-hidden=\"true\"></i><span>Find anything</span></button>
          <button type=\"button\" class=\"action-link dep-graph-trigger\" data-specs-action=\"open-dep-graph\" hidden><i data-lucide=\"network\" aria-hidden=\"true\"></i><span>Dependency graph</span></button>
          <a class=\"action-link\" href=\"{html.escape(raw_href)}\"><i data-lucide=\"code-2\" aria-hidden=\"true\"></i>Raw markdown</a>
          <a class=\"action-link\" href=\"/specs/README.md\"><i data-lucide=\"layout-list\" aria-hidden=\"true\"></i>Specs index</a>
        </div>
      </header>

      <div class=\"content-grid\">
        <article class=\"markdown-body\">
          {body_html}
        </article>

        <aside class=\"toc-panel\">
          <p class="eyebrow"><i data-lucide="list" aria-hidden="true"></i>On this page</p>
          {toc_panel}
          {related_specs_html}
        </aside>
      </div>
    </main>
  </div>

  <!-- Global toast root. Features dispatch `show-toast` with `detail: '...'`. -->
  <div class=\"spec-toast-root\"
       x-data=\"{{ msg: '', visible: false, show(text) {{ this.msg = text; this.visible = true; clearTimeout(this._t); this._t = setTimeout(() => this.visible = false, 1500); }} }}\"
       @show-toast.window=\"show($event.detail)\">
    <div class=\"spec-toast\" x-show=\"visible\" x-transition x-text=\"msg\"></div>
  </div>

  {data_island}
  <script>document.addEventListener('DOMContentLoaded', () => lucide.createIcons());</script>
  <script type=\"module\" src=\"/specs/consolidation/assets/specs.js\" defer></script>
</body>
</html>
"""


class SpecsHandler(SimpleHTTPRequestHandler):
    """Request handler that renders markdown files and serves static assets."""

    server_version = "PyarnesSpecsServer/0.1"
    repo_root: ClassVar[Path] = REPO_ROOT

    def __init__(self, *args: object, directory: str | None = None, **kwargs: object) -> None:
        super().__init__(*args, directory=str(self.repo_root), **kwargs)

    def do_GET(self) -> None:
        """Handle GET requests for markdown and static content."""
        parsed = urlsplit(self.path)
        if parsed.path in {"", "/", "/index.html"}:
            self._redirect(_nav_href(LANDING_PAGE))
            return

        target = self._resolve_path(parsed.path)
        if target is None:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        if target.is_dir():
            location = _directory_target(target)
            if location is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Directory has no browser entry")
                return
            self._redirect(location)
            return

        if target.suffix == ".md" and target.is_file():
            params = parse_qs(parsed.query)
            if params.get("raw") == ["1"]:
                self._serve_raw_markdown(target)
                return
            self._serve_markdown(target)
            return

        if target.suffix == ".html" and target.is_file() and self._is_under(target, DIAGRAMS_ROOT):
            self._serve_diagram_html(target)
            return

        super().do_GET()

    @staticmethod
    def _is_under(candidate: Path, root: Path) -> bool:
        """Return True if *candidate* sits inside *root*."""
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    def _serve_diagram_html(self, target: Path) -> None:
        """Serve a diagram HTML file with a back-button snippet injected."""
        try:
            source = target.read_text(encoding="utf-8")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "Diagram unreadable")
            return
        document = _inject_diagram_back_button(source, target)
        payload = document.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """Log requests to stderr in a compact form."""
        print(f"[{self.log_date_time_string()}] {format % args}", file=sys.stderr)  # noqa: T201

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def _resolve_path(self, request_path: str) -> Path | None:
        raw_path = unquote(request_path).lstrip("/")
        candidate = (self.repo_root / raw_path).resolve()
        try:
            candidate.relative_to(self.repo_root)
        except ValueError:
            return None
        return candidate

    def _serve_raw_markdown(self, target: Path) -> None:
        source = target.read_text(encoding="utf-8")
        payload = source.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_markdown(self, target: Path) -> None:
        source = target.read_text(encoding="utf-8")
        markdown = _build_markdown()
        body_html = markdown.convert(source)
        title = _extract_heading_title(target)

        # Reading-time / section / mtime chip below the H1.
        meta = _compute_spec_meta(target, body_html)
        body_html = _inject_spec_meta(body_html, meta)

        # Spec-card replacement for the > **Spec header** blockquote.
        slug = "readme" if target == LANDING_PAGE else target.stem
        header = _spec_header_for(target)
        if header is not None:
            page_index = {entry.slug: entry for entry in _build_page_entries()}
            body_html = _replace_spec_header_blockquote(body_html, slug, header, page_index)

        # Convert `<li>[ ] foo</li>` into Alpine-bound checklist items.
        body_html = _convert_task_list_items(body_html, slug)

        document = _render_template(
            current_path=target,
            body_html=body_html,
            toc_html=markdown.toc,
            title=title,
        )
        payload = document.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT})")
    parser.add_argument("--open", action="store_true", help="Open the browser after the server starts")
    return parser.parse_args()


# Port-conflict recovery. The script binds the same port across runs, so a
# stale instance left over from a crashed previous run is the most common
# reason `bind()` fails. Detect that case and restart cleanly; never touch
# a process we can't confirm is one of our own.

def _find_listening_pid(port: int) -> int | None:
    """Return the PID listening on *port* on TCP, or None.

    Uses lsof (default on macOS/Linux). Returns None on Windows or if
    lsof is missing — we fall back to the original OSError in that case.
    """
    try:
        result = subprocess.run(
            ["lsof", "-iTCP:" + str(port), "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not pids:
        return None
    try:
        return int(pids[0])
    except ValueError:
        return None


def _is_python_process(pid: int) -> bool:
    """Return True if *pid* is running a Python interpreter.

    The user contract is "if it's a python process holding our port,
    treat it as a stale instance and reclaim the port". This means
    sibling Python services on the same port (e.g. mkdocs) will also
    be terminated — that is intentional. To opt out, run the other
    service on a different port or pass --port to this script.
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    # `ps -o command=` prints the executable path + argv. Match
    # case-insensitively because macOS framework builds expose the
    # binary as `.../Python.app/Contents/MacOS/Python` (capital P).
    return "python" in result.stdout.lower()


def _stop_previous_instance(port: int) -> bool:
    """Find and stop a Python process holding *port*.

    Returns True if the process was terminated and the port is free;
    False if there's nothing to handle (port free, listener isn't a
    Python process, or platform tools aren't available).
    """
    pid = _find_listening_pid(port)
    if pid is None or pid == os.getpid():
        return False
    if not _is_python_process(pid):
        return False
    print(  # noqa: T201
        f"Port {port} is held by Python pid {pid}; treating as a stale instance and stopping it.",
        file=sys.stderr,
    )
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return _find_listening_pid(port) is None
    # Wait up to 2s for the socket to free; escalate to SIGKILL if not.
    for _ in range(20):
        time.sleep(0.1)
        if _find_listening_pid(port) is None:
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    time.sleep(0.5)
    return _find_listening_pid(port) is None


def _describe_listener(port: int) -> str:
    """Return a one-liner describing whatever holds *port*, or '(unknown)'.

    Used purely for diagnostics so the user can see why a Python kill
    didn't fire (e.g. listener is non-Python, or platform tools missing).
    """
    pid = _find_listening_pid(port)
    if pid is None:
        return "(no LISTEN socket found — the port may be in TIME_WAIT or platform tooling is unavailable)"
    try:
        result = subprocess.run(
            ["ps", "-o", "pid=,command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return f"pid {pid} (could not query command line)"
    line = result.stdout.strip()
    return line or f"pid {pid}"


def _find_free_port(host: str, start: int, span: int = 10) -> int | None:
    """Return the first port in [start, start+span] this script can bind on *host*.

    Used as the auto-fallback path: if we can't reclaim `start`, walk up
    the next handful of ports until one binds. Each probe-bind is closed
    immediately so the real server can take over the port itself.
    """
    for offset in range(span + 1):
        candidate = start + offset
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, candidate))
        except OSError:
            sock.close()
            continue
        sock.close()
        return candidate
    return None


def _bind_server(host: str, port: int) -> tuple[ThreadingHTTPServer, int]:
    """Bind a ThreadingHTTPServer, with two recovery layers.

    1. If the requested port is held by a Python process, kill it and retry.
    2. If that doesn't free the port, scan upward for a free port and use it.

    Returns the server and the port it actually bound. Raises SystemExit
    only if neither the kill path nor the fallback scan finds a usable port.
    """
    try:
        return ThreadingHTTPServer((host, port), SpecsHandler), port
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Layer 1: try to reclaim from a Python process.
        if _stop_previous_instance(port):
            try:
                return ThreadingHTTPServer((host, port), SpecsHandler), port
            except OSError as second_exc:
                if second_exc.errno != errno.EADDRINUSE:
                    raise
        # Layer 2: scan upward for a free port.
        listener = _describe_listener(port)
        print(  # noqa: T201
            f"Port {port} is held by {listener}; cannot reclaim it. Looking for a free port nearby…",
            file=sys.stderr,
        )
        fallback = _find_free_port(host, port + 1)
        if fallback is None:
            raise SystemExit(
                f"error: port {port} is busy and ports {port + 1}–{port + 10} are all unavailable. "
                f"Pass --port <free port> explicitly."
            ) from exc
        print(  # noqa: T201
            f"Falling back to port {fallback}.",
            file=sys.stderr,
        )
        return ThreadingHTTPServer((host, fallback), SpecsHandler), fallback


def main() -> int:
    """Run the local specs viewer."""
    if not LANDING_PAGE.is_file():
        print(f"error: missing landing page at {LANDING_PAGE}", file=sys.stderr)  # noqa: T201
        return 1

    STYLESHEET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STYLESHEET_PATH.exists():
        STYLESHEET_PATH.write_text(_load_stylesheet(), encoding="utf-8")

    args = parse_args()
    server, bound_port = _bind_server(args.host, args.port)
    url = f"http://{args.host}:{bound_port}/"
    print(f"Serving specs at {url}", file=sys.stderr)  # noqa: T201
    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping specs server", file=sys.stderr)  # noqa: T201
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
