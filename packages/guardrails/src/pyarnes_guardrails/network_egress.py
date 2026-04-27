"""Block outbound network calls to disallowed hosts.

URL parsing goes through ``urllib.parse.urlsplit`` — not a regex — so
userinfo tricks (``https://trusted@attacker.com/``), explicit ports,
and IDN / punycode all flatten to the canonical host token before the
allow/deny check. A denylist match wins over an allowlist hit; an
unparseable URL or a URL whose scheme is not on the allowed-scheme set
is treated as "potentially blocked" and rejected (fail-closed).

We **do not** resolve DNS. A host on the allowlist that resolves to an
internal IP is still allowed — the trust boundary is the textual host,
not the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from pyarnes_core.errors import UserFixableError
from pyarnes_core.observability import log_warning
from pyarnes_core.observe.logger import get_logger
from pyarnes_core.safety import walk_strings
from pyarnes_guardrails.guardrails import Guardrail

__all__ = ["NetworkEgressGuardrail"]

logger = get_logger(__name__)

# Match anything that looks URL-ish. The scheme check happens after
# parsing; here we only need a cheap pre-filter so urlsplit isn't
# called on every token.
_URL_PREFIX = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]{1,19}://")

# Schemes we understand and are willing to allow when the host passes.
# Anything else (``file://``, ``gopher://``, ``data:``, ``jar:``, bare
# schemes) is rejected unconditionally.
_DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset(
    {"http", "https", "ws", "wss", "ftp", "ftps"}
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
        allowed_schemes: URL schemes permitted. Defaults to
            ``{http, https, ws, wss, ftp, ftps}``.
    """

    allowed_hosts: tuple[str, ...] = ()
    denied_hosts: tuple[str, ...] = ()
    allowed_schemes: frozenset[str] = _DEFAULT_ALLOWED_SCHEMES

    def check(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """Raise ``UserFixableError`` for any URL whose host is blocked."""
        allowed = frozenset(h.lower() for h in self.allowed_hosts)
        denied = frozenset(h.lower() for h in self.denied_hosts)
        for value in arguments.values():
            for text in walk_strings(value):
                for host in _extract_hosts(text, self.allowed_schemes):
                    if _is_blocked(host, allowed, denied):
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


def _extract_hosts(text: str, allowed_schemes: frozenset[str]) -> list[str]:
    """Yield every canonical host token in *text*.

    A URL with userinfo (``user@host``) is always rejected by yielding
    the literal string ``"<userinfo-host>"`` which is guaranteed to
    fail allowlist matching. An unparseable URL yields ``"<unparseable>"``
    with the same effect. A URL whose scheme is not allowed yields
    ``"<blocked-scheme:...>"``.
    """
    hosts: list[str] = []
    for match in _URL_PREFIX.finditer(text):
        start = match.start()
        end = _find_url_end(text, start)
        raw = text[start:end]
        hosts.append(_canonical_host(raw, allowed_schemes))
    return hosts


def _find_url_end(text: str, start: int) -> int:
    """Return the exclusive end index of the URL starting at *start*."""
    end = len(text)
    for i in range(start, len(text)):
        if text[i] in " \t\n\r\"'`<>":
            end = i
            break
    return end


def _canonical_host(url: str, allowed_schemes: frozenset[str]) -> str:
    """Extract and normalise the host; return a sentinel on any anomaly."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable>"
    scheme = parts.scheme.lower()
    if scheme not in allowed_schemes:
        return f"<blocked-scheme:{scheme}>"
    # urlsplit exposes .username; any userinfo is a phishing / spoofing
    # attempt in an agent context — never let the guardrail believe the
    # host was the userinfo token.
    if parts.username or parts.password:
        return "<userinfo-rejected>"
    host = parts.hostname or ""
    if not host:
        return "<no-host>"
    # IDN -> ASCII so Cyrillic lookalikes don't shadow the allowlist
    # (e.g. U+0435 in place of ASCII 'e').
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return "<idn-unparseable>"
    return host.strip(".").lower()


def _is_blocked(host: str, allowed: frozenset[str], denied: frozenset[str]) -> bool:
    """Return ``True`` when *host* fails the allow/deny rules."""
    if host.startswith("<") and host.endswith(">"):
        # Sentinel values from _canonical_host — always blocked.
        return True
    if _matches(host, denied):
        return True
    if not allowed:
        return False
    return not _matches(host, allowed)


def _matches(host: str, rules: frozenset[str]) -> bool:
    """Return ``True`` when *host* equals a rule or is its subdomain."""
    if host in rules:
        return True
    return any(host.endswith("." + rule) for rule in rules)
