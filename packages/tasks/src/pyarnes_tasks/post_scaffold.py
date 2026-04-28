"""Post-scaffold task: run after `uvx copier copy` to set up the new project.

Steps:
1. ``uv sync`` — install dependencies
2. ``uv run tasks check`` — lint + typecheck + test (exit code 5 = no tests yet, treated as ok)
3. Append a next-steps checklist to ``AGENTS.md``

Exit codes:
- 0: all steps succeeded
- Non-zero: an unexpected error in uv sync or check (not exit-5)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CHECKLIST = """
## Post-scaffold checklist

- [ ] Add your first tool in `src/{module}/tools/`
- [ ] Write a matching test in `tests/unit/`
- [ ] Run `uv run tasks check` — all checks must pass before opening a PR
- [ ] Set `OTEL_EXPORTER_OTLP_ENDPOINT` if you want distributed tracing
- [ ] Review `AGENTS.md` and extend with domain-specific guidelines
- [ ] Commit and push to your remote
"""


def _run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, check=False)  # noqa: S603
    return result.returncode


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Run post-scaffold setup steps."""
    root = Path.cwd()

    print("post_scaffold: running uv sync …", flush=True)  # noqa: T201
    rc = _run(["uv", "sync"])
    if rc != 0:
        print(f"post_scaffold: uv sync failed (exit {rc})", file=sys.stderr)  # noqa: T201
        return rc

    print("post_scaffold: running uv run tasks check …", flush=True)  # noqa: T201
    rc = _run(["uv", "run", "tasks", "check"])
    if rc not in (0, 5):
        print(f"post_scaffold: tasks check failed (exit {rc})", file=sys.stderr)  # noqa: T201
        return rc

    agents_md = root / "AGENTS.md"
    if agents_md.exists():
        with agents_md.open("a", encoding="utf-8") as fh:
            fh.write(_CHECKLIST)
        print("post_scaffold: appended checklist to AGENTS.md", flush=True)  # noqa: T201
    else:
        print("post_scaffold: AGENTS.md not found, skipping checklist", flush=True)  # noqa: T201

    print("post_scaffold: done.", flush=True)  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
