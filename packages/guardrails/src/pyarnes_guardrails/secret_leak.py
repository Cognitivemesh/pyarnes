r"""Detect plaintext secrets inside tool inputs or outputs.

Two modes of use — both via the same ``check`` signature:

* **Pre-tool** (the Claude Code ``PreToolUse`` hook): pass the tool's
  ``tool_input`` dict. Blocks outbound leaks (an agent pasting a secret
  into a ``Bash`` command, a ``WebFetch`` URL, or a file write).
* **Post-tool** (the Claude Code ``PostToolUse`` hook): pass the tool's
  ``tool_response`` wrapped as ``{"output": tool_response}``. Detect-
  and-halt only — the model has already seen the response; CC's
  PostToolUse contract does not let us rewrite it.

Defenses that matter:

- Patterns compile with ``re.IGNORECASE`` so
  ``AWS_SECRET_ACCESS_KEY`` is caught alongside its lower-case variant.
- Every candidate string is ``NFKC``-normalised and has zero-width /
  RTL marks stripped before matching so confusables do not slip past
  ``\b``-anchored patterns.
- The ``UserFixableError`` message names the tool but **not** the
  pattern or the matched text — so a probing agent cannot enumerate
  which pattern a near-miss triggered, and the sidecar violation log
  never contains the secret itself.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.safety import walk_strings
from pyarnes_guardrails.guardrails import Guardrail

__all__ = ["SecretLeakGuardrail"]

logger = get_logger(__name__)

# Common high-signal, low-false-positive patterns. Adopters add their
# own via the ``extra_patterns`` field.
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

# Zero-width joiners, non-joiners, LTR/RTL marks — strip before match.
# Ranges: U+200B..U+200F (ZW joiners + LTR/RTL marks), U+202A..U+202E
# (explicit directional overrides), U+2060..U+2064 (word joiner, etc.),
# U+FEFF (BOM). Built as a translate table of codepoints so the source
# file itself stays printable ASCII.
_INVISIBLE_TABLE = dict.fromkeys(
    [
        *range(0x200B, 0x2010),  # ZW space, joiners, LTR/RTL marks
        *range(0x202A, 0x202F),  # directional embedding / override
        *range(0x2060, 0x2065),  # word joiner + invisible separators
        0xFEFF,  # BOM / ZW no-break space
    ],
    None,
)


_SECRET_TAGS: frozenset[str] = frozenset(
    {"Credentials", "Password", "Secret", "API", "Private Key", "Token"}
)


@dataclass(frozen=True, slots=True)
class SecretLeakGuardrail(Guardrail):
    """Block tool calls whose arguments or output contain a secret.

    Attributes:
        extra_patterns: Additional regex patterns the adopter wants to
            enforce on top of :data:`_DEFAULT_PATTERNS`.
        use_pywhat: When ``True`` and ``pywhat`` (soft dep, install
            separately: ``pip install pywhat>=5.0``) is available, run the
            identifier alongside the built-in patterns. Additive only —
            the regex patterns always run regardless of this flag.
            Gracefully degraded to a no-op when ``pywhat`` is absent.
    """

    extra_patterns: tuple[str, ...] = ()
    use_pywhat: bool = False

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` when a value matches a secret pattern."""
        patterns = self._compile()
        for value in arguments.values():
            for raw in walk_strings(value):
                candidate = _normalise(raw)
                for pattern in patterns:
                    if pattern.search(candidate):
                        self._block(tool_name, "regex")
                if self.use_pywhat and _pywhat_detects(candidate):
                    self._block(tool_name, "pywhat")

    def _block(self, tool_name: str, source: str) -> None:
        log_warning(
            logger,
            "guardrail.secret_leak_blocked",
            tool=tool_name,
            source=source,
        )
        # Generic exception message on purpose — never echo the pattern
        # or the matched text so the model cannot enumerate what triggered.
        raise UserFixableError(
            message=(f"Tool '{tool_name}' blocked: output or arguments match a secret pattern."),
            prompt_hint="Remove or redact the secret before continuing.",
        )

    def _compile(self) -> tuple[re.Pattern[str], ...]:
        """Compile patterns once per call; trivial cost for ~10 entries."""
        raw = _DEFAULT_PATTERNS + tuple(self.extra_patterns)
        return tuple(re.compile(p, re.IGNORECASE) for p in raw)


def _normalise(text: str) -> str:
    """NFKC-normalise and strip zero-width / RTL marks before matching."""
    return unicodedata.normalize("NFKC", text).translate(_INVISIBLE_TABLE)


def _pywhat_detects(candidate: str) -> bool:
    """Return ``True`` when ``pywhat`` is installed and identifies a secret.

    No-op (returns ``False``) when ``pywhat`` is not installed so the guardrail
    degrades gracefully without the optional dependency.
    """
    try:
        from pywhat import Pywhat  # noqa: PLC0415
    except ImportError:
        return False

    result = Pywhat().identify(candidate)
    if result is None:
        return False
    return any(_SECRET_TAGS & set(match.get("Tags", [])) for match in result.get("Regex", []))
