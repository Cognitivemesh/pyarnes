"""``[tool.pyarnes-audit]`` configuration loader.

Reads the audit table from the project's ``pyproject.toml``. Every key has a
default so a project that omits the table still gets a working ``audit:check``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["AuditConfig"]


_DEFAULT_GRAPH_PATH = ".pyarnes/audit/graph.json"
_DEFAULT_ROOTS = ["src"]
_DEFAULT_EXCLUDE = [".venv", ".pyarnes", "__pycache__", "node_modules", ".git"]
_DEFAULT_FLAG_PATTERN = r"feature_flag\(['\"](\w+)['\"]\)"
_DEFAULT_DUPLICATE_MIN_TOKENS = 40


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """Source-controlled audit configuration.

    Loaded from ``[tool.pyarnes-audit]`` in the project ``pyproject.toml``.
    The same instance flows from CLI shim → builder → detectors, so all
    operations within one run see the same view of the project.
    """

    project_root: Path
    graph_path: Path
    roots: list[str] = field(default_factory=lambda: list(_DEFAULT_ROOTS))
    exclude: list[str] = field(default_factory=lambda: list(_DEFAULT_EXCLUDE))
    forbidden_edges: list[tuple[str, str]] = field(default_factory=list)
    flag_pattern: str = _DEFAULT_FLAG_PATTERN
    duplicate_min_tokens: int = _DEFAULT_DUPLICATE_MIN_TOKENS

    @classmethod
    def load(cls, project_root: Path | str) -> AuditConfig:
        """Build an :class:`AuditConfig` for the project rooted at *project_root*.

        Resolution order: explicit ``[tool.pyarnes-audit]`` keys → defaults.
        Missing ``pyproject.toml`` is tolerated (defaults apply) so the loader
        also runs in test fixtures that ship a synthetic project tree.
        """
        root = Path(project_root).resolve()
        pyproject = root / "pyproject.toml"
        table: dict[str, object] = {}
        if pyproject.is_file():
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
            table = data.get("tool", {}).get("pyarnes-audit", {})  # type: ignore[assignment]

        graph_path_str = str(table.get("graph_path", _DEFAULT_GRAPH_PATH))
        graph_path = root / graph_path_str

        roots_raw = table.get("roots", _DEFAULT_ROOTS)
        roots = [str(r) for r in roots_raw if isinstance(r, str)] or list(_DEFAULT_ROOTS)  # ty: ignore[not-iterable]

        exclude_raw = table.get("exclude", _DEFAULT_EXCLUDE)
        exclude = [str(e) for e in exclude_raw if isinstance(e, str)] or list(_DEFAULT_EXCLUDE)  # ty: ignore[not-iterable]

        forbidden_raw = table.get("forbidden_edges", [])
        forbidden_edges: list[tuple[str, str]] = [
            (str(pair[0]), str(pair[1]))
            for pair in forbidden_raw  # ty: ignore[not-iterable]
            if isinstance(pair, (list, tuple)) and len(pair) == 2  # noqa: PLR2004  # forbidden_edges is a [src, dst] pair
        ]

        flag_pattern = str(table.get("flag_pattern", _DEFAULT_FLAG_PATTERN))
        duplicate_min_tokens = int(table.get("duplicate_min_tokens", _DEFAULT_DUPLICATE_MIN_TOKENS))  # ty: ignore[invalid-argument-type]

        return cls(
            project_root=root,
            graph_path=graph_path,
            roots=roots,
            exclude=exclude,
            forbidden_edges=forbidden_edges,
            flag_pattern=flag_pattern,
            duplicate_min_tokens=duplicate_min_tokens,
        )
