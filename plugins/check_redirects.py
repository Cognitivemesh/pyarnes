"""Validate that every ``redirect_maps`` target in mkdocs.yml exists."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from pyarnes_tasks.plugin_base import ModulePlugin


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)  # noqa: T201


def _build_loader() -> type:
    """Return a SafeLoader that ignores mkdocs' ``!!python/name:...`` tags."""
    import yaml  # noqa: PLC0415

    class IgnoreTagLoader(yaml.SafeLoader):
        pass

    IgnoreTagLoader.add_constructor(None, lambda _loader, _node: None)  # type: ignore[arg-type]
    return IgnoreTagLoader


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


def _check_redirects(mkdocs_path: Path, docs_dir: Path) -> list[tuple[str, str]]:
    """Return a list of ``(source, target)`` pairs whose target is missing."""
    import yaml  # noqa: PLC0415

    with mkdocs_path.open("r", encoding="utf-8") as fh:
        config = yaml.load(fh, Loader=_build_loader())  # noqa: S506

    missing: list[tuple[str, str]] = []
    for mapping in _find_redirect_maps(config):
        for source, target in mapping.items():
            if not (docs_dir / target).is_file():
                missing.append((source, target))
    return missing


class CheckRedirects(ModulePlugin):
    """``uv run tasks check:redirects`` — validate mkdocs redirect_maps targets."""

    name = "check:redirects"
    description = "Validate that every redirect_maps target in mkdocs.yml exists"

    def call(self, argv: list[str]) -> int:  # noqa: ARG002
        """Walk mkdocs.yml redirect_maps and verify every target exists on disk."""
        repo_root = Path(__file__).resolve().parent.parent
        mkdocs_path = repo_root / "mkdocs.yml"
        docs_dir = repo_root / "docs"

        if not mkdocs_path.is_file():
            _err(f"error: {mkdocs_path} not found")
            return 1
        if not docs_dir.is_dir():
            _err(f"error: {docs_dir} not a directory")
            return 1

        missing = _check_redirects(mkdocs_path, docs_dir)
        if missing:
            _err(f"error: {len(missing)} redirect target(s) missing:")
            for source, target in missing:
                _err(f"  {source} -> {target}")
            return 1

        print("ok: all redirect targets exist")  # noqa: T201
        return 0
