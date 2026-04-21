"""Block outbound network calls to disallowed hosts.

Lexical URL scan — no DNS, no socket. We parse host tokens out of every
string reachable in the tool arguments and apply an allowlist/denylist.

This is a *PreToolUse* guardrail: wire it before ``Bash`` and
``WebFetch`` so an agent cannot exfiltrate to an unreviewed host. A
denylist match wins over an allowlist hit — a host pinned on the
denylist is always blocked.
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

__all__ = ["NetworkEgressGuardrail"]

logger = get_logger(__name__)

_URL_RE: re.Pattern[str] = re.compile(
    r"""
    (?:https?|ftp|wss?):// # scheme
    (?P<host>[^\s/:?#'"`]+) # host (up to the next separator)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class NetworkEgressGuardrail(Guardrail):
    """Block tool calls targeting hosts outside the allowlist.

    Attributes:
        allowed_hosts: Hosts that may be contacted. ``"example.com"``
            matches both ``example.com`` and ``*.example.com``. An empty
            tuple permits every host (deny-only mode).
        denied_hosts: Hosts that are always blocked, even if they also
            appear in ``allowed_hosts``.
    """

    allowed_hosts: tuple[str, ...] = ()
    denied_hosts: tuple[str, ...] = ()
    _allowed: frozenset[str] = field(init=False, repr=False, default=frozenset())
    _denied: frozenset[str] = field(init=False, repr=False, default=frozenset())

    def __post_init__(self) -> None:
        """Freeze the host sets for O(1) membership checks."""
        object.__setattr__(self, "_allowed", frozenset(h.lower() for h in self.allowed_hosts))
        object.__setattr__(self, "_denied", frozenset(h.lower() for h in self.denied_hosts))

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` for any URL whose host is blocked."""
        for value in arguments.values():
            for text in walk_strings(value):
                for match in _URL_RE.finditer(text):
                    host = match.group("host").lower()
                    if self._is_blocked(host):
                        log_warning(
                            logger,
                            "guardrail.network_egress_blocked",
                            tool=tool_name,
                            host=host,
                        )
                        raise UserFixableError(
                            message=(
                                f"Tool '{tool_name}' attempted to reach "
                                f"blocked host {host!r}."
                            ),
                            prompt_hint="Add the host to allowed_hosts or choose another target.",
                        )

    def _is_blocked(self, host: str) -> bool:
        """Return ``True`` when *host* fails the allow/deny rules."""
        if _matches(host, self._denied):
            return True
        if not self._allowed:
            # No allowlist configured → deny-only mode.
            return False
        return not _matches(host, self._allowed)


def _matches(host: str, rules: frozenset[str]) -> bool:
    """Return ``True`` when *host* equals a rule or is its subdomain."""
    if host in rules:
        return True
    return any(host.endswith("." + rule) for rule in rules)
