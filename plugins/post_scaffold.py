"""Post-scaffold setup for newly copier-generated projects."""

from __future__ import annotations

from pyarnes_tasks.plugin_base import ModulePlugin


class PostScaffold(ModulePlugin):
    """``uv run tasks post_scaffold`` — post-scaffold setup steps."""

    name = "post_scaffold"
    description = "Post-scaffold setup for newly copier-generated projects"

    def call(self, argv: list[str]) -> int:
        """Run the post_scaffold task in-process; main() already accepts argv."""
        from pyarnes_tasks.post_scaffold import main  # noqa: PLC0415

        return main(argv)
