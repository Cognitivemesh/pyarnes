"""``tasks bench:run -- <dotted.module>`` — import and execute an adopter suite.

The adopter module must expose ``build_suite()`` (sync or async) returning a
``pyarnes_bench.EvalSuite``. This task prints a JSON summary to stdout; the
suite itself is responsible for logging per-scenario results via loguru.

``pyarnes-bench`` is imported lazily inside ``main`` so ``pyarnes-tasks``
doesn't grow a hard runtime dependency on it — adopters who don't use
benchmarks still get the rest of the task runner.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys

_MIN_ARGS = 2


def _usage() -> int:
    print("usage: tasks bench:run -- <dotted.module>", file=sys.stderr)  # noqa: T201
    return 1


def main() -> int:
    """Entry point — returns a process exit code."""
    if len(sys.argv) < _MIN_ARGS:
        return _usage()
    module_path = sys.argv[1]
    module = importlib.import_module(module_path)
    build_suite = getattr(module, "build_suite", None)
    if build_suite is None:
        print(f"{module_path}.build_suite is not defined", file=sys.stderr)  # noqa: T201
        return 1

    result = build_suite()
    suite = asyncio.run(result) if inspect.isawaitable(result) else result
    print(json.dumps(suite.summary(), indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
