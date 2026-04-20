"""``tasks bench:report -- <jsonl_path>`` — render a markdown table from JSONL.

Each JSONL line is expected to have ``scenario``, ``score``, and (optional)
``reason`` / ``metadata.reason`` fields — matching ``EvalResult.as_dict()``.
Stdlib-only; ``pyarnes-bench`` is not imported.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_MIN_ARGS = 2


def _usage() -> int:
    print("usage: tasks bench:report -- <jsonl_path>", file=sys.stderr)  # noqa: T201
    return 1


def _reason(row: dict[str, Any]) -> str:
    if "reason" in row:
        return str(row["reason"])
    metadata = row.get("metadata")
    if isinstance(metadata, dict) and "reason" in metadata:
        return str(metadata["reason"])
    return ""


def main() -> int:
    """Entry point — returns a process exit code."""
    if len(sys.argv) < _MIN_ARGS:
        return _usage()
    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"not a file: {path}", file=sys.stderr)  # noqa: T201
        return 1

    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    print("| scenario | score | reason |")  # noqa: T201
    print("| --- | --- | --- |")  # noqa: T201
    for row in rows:
        scenario = row.get("scenario", "")
        score = row.get("score", "")
        print(f"| {scenario} | {score} | {_reason(row)} |")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
