#!/usr/bin/env python3
"""Validate that every ``redirect_maps`` target in mkdocs.yml exists.

Run as part of CI / ``uv run tasks check:redirects`` so a rename never
silently 404s an old bookmark.

Exit code 0 on success, 1 if any target is missing or if mkdocs.yml is
unreadable. Prints the full list of missing targets to stderr.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

import yaml


class _IgnoreTagLoader(yaml.SafeLoader):
    """Ignore ``!!python/name:...`` tags used by mkdocs plugin hooks."""


def _ignore_unknown(loader: yaml.SafeLoader, node: yaml.Node) -> None:  # noqa: ARG001
    return None


_IgnoreTagLoader.add_constructor(None, _ignore_unknown)  # type: ignore[arg-type]


def _find_redirect_maps(node: object) -> Iterable[dict[str, str]]:
    """Walk parsed mkdocs.yml and yield every ``redirect_maps`` mapping."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "redirect_maps" and isinstance(value, dict):
                yield value
            else:
                yield from _find_redirect_maps(value)
    elif isinstance(node, list):
        for item in node:
            yield from _find_redirect_maps(item)


def check_redirects(mkdocs_path: Path, docs_dir: Path) -> list[tuple[str, str]]:
    """Return a list of ``(source, target)`` pairs whose target is missing."""
    with mkdocs_path.open("r", encoding="utf-8") as fh:
        config = yaml.load(fh, Loader=_IgnoreTagLoader)  # noqa: S506

    missing: list[tuple[str, str]] = []
    for mapping in _find_redirect_maps(config):
        for source, target in mapping.items():
            if not (docs_dir / target).is_file():
                missing.append((source, target))
    return missing


def main() -> int:
    """Entry point."""
    repo_root = Path(__file__).resolve().parent.parent
    mkdocs_path = repo_root / "mkdocs.yml"
    docs_dir = repo_root / "docs"

    if not mkdocs_path.is_file():
        print(f"error: {mkdocs_path} not found", file=sys.stderr)  # noqa: T201
        return 1
    if not docs_dir.is_dir():
        print(f"error: {docs_dir} not a directory", file=sys.stderr)  # noqa: T201
        return 1

    missing = check_redirects(mkdocs_path, docs_dir)
    if missing:
        print(f"error: {len(missing)} redirect target(s) missing:", file=sys.stderr)  # noqa: T201
        for source, target in missing:
            print(f"  {source} -> {target}", file=sys.stderr)  # noqa: T201
        return 1

    print("ok: all redirect targets exist")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
