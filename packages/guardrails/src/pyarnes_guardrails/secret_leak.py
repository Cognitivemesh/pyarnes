"""Detect plaintext secrets inside tool inputs or outputs.

The guardrail reuses ``pyarnes_core.safety.walk_strings`` to descend
into nested dicts and lists so alternate argument shapes (``content``,
``body``, ``text``, list-of-strings) are all covered.

Two modes of use — both via the same ``check`` signature:

* **Pre-tool** (the Claude Code ``PreToolUse`` hook): pass the tool's
  ``tool_input`` dict. Blocks outbound leaks (an agent pasting a secret
  into a ``Bash`` command, a ``WebFetch`` URL, or a file write).
* **Post-tool** (the Claude Code ``PostToolUse`` hook): pass the tool's
  ``tool_response`` wrapped as ``{"output": tool_response}``. Detect-
  and-halt only — the model has already seen the response; CC's
  PostToolUse contract does not let us rewrite it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.safety import walk_strings
from pyarnes_guardrails.guardrails import Guardrail

__all__ = ["SecretLeakGuardrail"]

logger = get_logger(__name__)

# Common high-signal, low-false-positive patterns. Adopters add their own
# via the ``extra_patterns`` field.
_DEFAULT_PATTERNS: tuple[str, ...] = (
    # AWS access key IDs — fixed 20-char prefix shape.
    r"\bAKIA[0-9A-Z]{16}\b",
    # AWS secret keys in a "key=VALUE" or JSON "key": "VALUE" shape.
    r"aws_secret_access_key[\"'\s:=]+[A-Za-z0-9/+=]{30,}",
    # GitHub personal-access tokens (classic + fine-grained + server).
    r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
    # Anthropic API keys.
    r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b",
    # Slack bot / user tokens.
    r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",
    # Google API keys.
    r"\bAIza[0-9A-Za-z_\-]{35}\b",
    # PEM-encoded private keys.
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)


@dataclass(frozen=True, slots=True)
class SecretLeakGuardrail(Guardrail):
    """Block tool calls whose arguments or output contain a secret.

    Attributes:
        extra_patterns: Additional regex patterns the adopter wants to
            enforce on top of :data:`_DEFAULT_PATTERNS`.
        scan_keys: When set, only descend into values under these keys.
            When empty (the default), every string value is scanned —
            which is the right choice for PostToolUse where output can
            land in any nested field.
    """

    extra_patterns: tuple[str, ...] = ()
    scan_keys: tuple[str, ...] = ()
    _compiled: tuple[re.Pattern[str], ...] = field(init=False, repr=False, default=())

    def __post_init__(self) -> None:
        """Pre-compile the combined pattern list once per instance."""
        patterns = _DEFAULT_PATTERNS + tuple(self.extra_patterns)
        compiled = tuple(re.compile(p) for p in patterns)
        object.__setattr__(self, "_compiled", compiled)

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` when a value matches a secret pattern."""
        for value in self._values(arguments):
            for candidate in walk_strings(value):
                if not isinstance(candidate, str):
                    continue
                for pattern in self._compiled:
                    if pattern.search(candidate):
                        log_warning(
                            logger,
                            "guardrail.secret_leak_blocked",
                            tool=tool_name,
                            pattern=pattern.pattern,
                        )
                        msg = (
                            f"Potential secret matching {pattern.pattern!r} "
                            f"detected in tool '{tool_name}' arguments/output."
                        )
                        raise UserFixableError(
                            message=msg,
                            prompt_hint="Remove the secret or redact it before continuing.",
                        )

    def _values(self, arguments: dict[str, Any]) -> list[Any]:
        """Return the value subset to scan (all values, or filtered by key)."""
        if not self.scan_keys:
            return list(arguments.values())
        return [arguments[k] for k in self.scan_keys if k in arguments]
