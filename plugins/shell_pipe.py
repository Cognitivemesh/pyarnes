"""Shell pipelines via the ``sh`` library (PEP 723 — own deps).

Demonstrates running shell commands as Python functions. Default
behaviour: count tracked LOC under sources via ``git ls-files | xargs wc``.

Usage:
    uv run tasks shell_pipe                 # default LOC count
    uv run tasks shell_pipe -- <cmd> ...    # arbitrary first-positional binary
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["sh>=2.0"]
# ///

from __future__ import annotations

import sys


def _run_shell_pipe(argv: list[str]) -> int:
    """Run the configured pipeline; return exit code."""
    import sh  # noqa: PLC0415 — heavy lazy import

    if argv:
        # Pass-through mode: first positional arg is the binary.
        binary, *rest = argv
        try:
            cmd = getattr(sh, binary)
        except sh.CommandNotFound as exc:
            print(f"sh: {exc}", file=sys.stderr)  # noqa: T201
            return 127
        result = cmd(*rest, _out=sys.stdout, _err=sys.stderr, _ok_code=list(range(256)))
        return int(result.exit_code)

    # Default: count LOC across tracked Python files.
    files = sh.git("ls-files", "*.py").splitlines()
    if not files:
        print("(no .py files tracked)")  # noqa: T201
        return 0
    total = sum(int(sh.wc("-l", f).split()[0]) for f in files)
    print(f"{total} lines across {len(files)} python files")  # noqa: T201
    return 0


try:
    from pyarnes_tasks.plugin_base import ScriptPlugin

    class ShellPipe(ScriptPlugin):
        """``uv run tasks shell_pipe`` — shell pipelines via the ``sh`` library."""

        name = "shell_pipe"
        description = "Shell pipelines via ``sh`` (PEP 723 demo)"

        def run_script(self, argv: list[str]) -> int:
            """Forward to ``_run_shell_pipe``."""
            return _run_shell_pipe(argv)
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run_shell_pipe(sys.argv[1:]))
