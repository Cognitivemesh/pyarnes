"""Credential redaction — strip plaintext secrets from strings and dicts.

Operates on *output*: tool results, log content, ToolMessage content.
Complements SecretLeakGuardrail which blocks secrets on *input* (tool args).

Patterns are compiled once at module load. False positives are preferred
over false negatives — a redacted log is recoverable; a leaked secret is not.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["REDACTED", "redact", "redact_dict"]

REDACTED = "[REDACTED]"

_PATTERNS: list[re.Pattern[str]] = [
    # AWS access key id
    re.compile(r"(?<![A-Z0-9])(A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    # AWS secret access key (40 base64 chars after keyword)
    re.compile(r"(?i)aws[_\-\s]?secret[_\-\s]?access[_\-\s]?key[\s:=]+[A-Za-z0-9/+=]{40}"),
    # GitHub personal access token (classic ghp_ and fine-grained github_pat_)
    re.compile(r"gh[pous]_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
    # Generic Bearer token header value
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    # Generic API key patterns: key=<hex/base64 32+ chars>
    re.compile(r"(?i)(?:api[_\-]?key|secret|password|token|passwd|auth)[\s:=]+['\"]?([A-Za-z0-9/+=\-_.]{32,})['\"]?"),
    # Private key PEM block
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^-]+-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
]


def redact(text: str) -> str:
    """Replace all detected secret patterns with ``[REDACTED]``."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact string values in a dict (does not mutate input)."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = redact(v)
        elif isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, list):
            out[k] = [redact(i) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out
