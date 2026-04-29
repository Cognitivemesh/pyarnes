"""Plugin discovery — import every ``*.py`` in a folder, side-effect register.

Plugins self-register via :meth:`Plugin.__init_subclass__` when their
class definition is executed during import. This loader walks a folder,
imports each file, and attaches ``plugin_file`` to any
:class:`ScriptPlugin` instances that landed in the registry — those need
to know which file to re-invoke under ``uv run``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pyarnes_tasks.plugin_base import ScriptPlugin
from pyarnes_tasks.registry import global_registry

__all__ = ["load_plugins"]


def load_plugins(folder: Path) -> None:
    """Import every ``*.py`` plugin under ``folder`` (non-recursive).

    Files starting with ``_`` are skipped (helpers, tests, ``__init__``).
    A missing folder is a no-op so a freshly-scaffolded project without
    a ``/plugins/`` directory boots cleanly.
    """
    if not folder.is_dir():
        return

    registry = global_registry()
    for file in sorted(folder.glob("*.py")):
        if file.name.startswith("_"):
            continue
        before = set(registry.as_dict())
        _import_file(file)
        # Any plugin that registered during this exec was authored in `file`.
        for name in set(registry.as_dict()) - before:
            plugin = registry.get(name)
            if isinstance(plugin, ScriptPlugin):
                plugin.plugin_file = file


def _import_file(file: Path) -> None:
    module_name = f"_pyarnes_plugin_{file.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
