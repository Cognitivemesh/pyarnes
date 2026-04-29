#!/usr/bin/env python3
"""PreToolUse hook: block destructive shell commands.

Reads a JSON hook payload from stdin. If the tool is Bash and the command
matches a known-dangerous pattern, exits with code 2 to block execution.

Dangerous patterns:
  - rm -rf with / or repo root
  - sudo (any)
  - git push --force / git reset --hard on published branches
  - DROP TABLE / TRUNCATE (SQL)
"""

import json
import re
import sys

DANGEROUS = [
    r"\brm\s+-[a-z]*r[a-z]*f\b",  # rm -rf variants
    r"\bsudo\b",
    r"\bgit\s+push\s+.*--force\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bDROP\s+TABLE\b",
    r"\bTRUNCATE\b",
]

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = payload.get("tool_name", "")
cmd = payload.get("tool_input", {}).get("command", "")

if tool.lower() == "bash" and cmd:
    for pattern in DANGEROUS:
        if re.search(pattern, cmd, re.IGNORECASE):
            result = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        f"Potentially destructive command detected: {cmd!r}. Please confirm before proceeding."
                    ),
                }
            }
            print(json.dumps(result))  # noqa: T201
            sys.exit(0)

sys.exit(0)
