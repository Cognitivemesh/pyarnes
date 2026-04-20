"""Parse every Python fenced block in ``docs/**/*.md``.

Two layers of protection against doc-rot:

1. Every ```python block in every docs page must parse with :func:`ast.parse`.
   Catches syntax errors, bad indentation, missing colons, incomplete snippets.
2. Sequential tutorials in :data:`RUNNABLE_PAGES` (pages that promise the
   reader they can copy-paste end-to-end) have their concatenated blocks
   checked by ``ruff --select F821`` — catches missing imports such as the
   ``ModelClient`` bug fixed in the docs audit.

Reference-style pages (API docs, package deep-dives) are intentionally
excluded from the F821 check because their snippets are demonstrative and
assume the reader's surrounding context. If you add a new sequential tutorial,
add its path to :data:`RUNNABLE_PAGES`.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs"
PYTHON_FENCE = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)

RUNNABLE_PAGES: frozenset[str] = frozenset(
    {
        "docs/adopter/build/quickstart.md",
    }
)


def _python_blocks(md_path: Path) -> list[str]:
    return PYTHON_FENCE.findall(md_path.read_text(encoding="utf-8"))


def _md_files_with_python() -> list[Path]:
    return sorted(p for p in DOCS_ROOT.rglob("*.md") if _python_blocks(p))


def _rel(path: Path) -> str:
    return str(path.relative_to(DOCS_ROOT.parent))


MD_FILES = _md_files_with_python()
RUNNABLE_FILES = [p for p in MD_FILES if _rel(p) in RUNNABLE_PAGES]


@pytest.mark.parametrize("md_path", MD_FILES, ids=_rel)
def test_docs_python_blocks_parse(md_path: Path) -> None:
    """Every Python fenced block must parse as valid Python."""
    for idx, block in enumerate(_python_blocks(md_path), start=1):
        try:
            ast.parse(block)
        except SyntaxError as exc:
            pytest.fail(f"{_rel(md_path)} block #{idx}: {exc}")


@pytest.mark.parametrize("md_path", RUNNABLE_FILES, ids=_rel)
def test_runnable_tutorials_no_undefined_names(md_path: Path, tmp_path: Path) -> None:
    """Concatenated blocks in a runnable tutorial must not use undefined names."""
    combined = "\n\n".join(_python_blocks(md_path))
    target = tmp_path / "combined.py"
    target.write_text(combined, encoding="utf-8")
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "ruff",
            "check",
            "--select",
            "F821",
            "--no-cache",
            "--output-format",
            "concise",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"{_rel(md_path)} has undefined names in its Python examples:\n{result.stdout}{result.stderr}")


def test_docs_examples_coverage() -> None:
    """Fail if discovery returns zero — regex or layout has drifted."""
    assert MD_FILES, "no Markdown files with python blocks found under docs/"
    assert RUNNABLE_FILES, "no runnable tutorials matched RUNNABLE_PAGES"
