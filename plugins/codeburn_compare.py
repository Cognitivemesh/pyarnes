"""A/B compare two models across CC sessions."""

from __future__ import annotations

import sys

from pyarnes_tasks.plugin_base import ModulePlugin


class CodeburnCompare(ModulePlugin):
    """``uv run tasks codeburn:compare`` — A/B compare two models across CC sessions."""

    name = "codeburn:compare"
    description = "A/B compare two models across CC sessions"

    def call(self, argv: list[str]) -> int:
        """Run the codeburn:compare task in-process via a sys.argv shim."""
        from pyarnes_tasks.codeburn_compare import main  # noqa: PLC0415

        original = sys.argv
        sys.argv = ["codeburn:compare", *argv]
        try:
            return main()
        finally:
            sys.argv = original
