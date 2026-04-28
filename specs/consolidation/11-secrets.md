# pyarnes_swarm — Secrets Management

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Secrets and Credential Redaction |
> | **Status** | active |
> | **Type** | integrations-safety |
> | **Owns** | SecretStore Protocol, KeyringSecretStore, EnvSecretStore, ChainedSecretStore, credential redaction policy (H9), CLI helper, CI setup, secret-key naming convention |
> | **Depends on** | 10-provider-config.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 10-provider-config.md |
> | **Read before** | 07-bench-integrated-axes.md |
> | **Not owned here** | provider config (see `10-provider-config.md`); transport (see `22-transport.md`); error taxonomy definitions (see `01-package-structure.md`); message-safety pipeline (see `20-message-safety.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

**Why OS keychain over a bespoke encrypted file?** Rolling your own encryption means rolling your own key management. Where does the decryption key live? Usually in another file, hardcoded in source, or derived from a password the developer types — each of which reintroduces the original problem. `keyring` delegates key management to the OS, which uses hardware-backed key stores on modern hardware (Secure Enclave on Apple Silicon, TPM on Windows). The OS has spent decades solving this problem; we inherit that solution for free.

**Why `keyring` specifically, and not another secrets library?** `keyring` is used by `pip`, `twine`, and `Jupyter` — three of the most widely audited Python tools. If it had a leak vector it would have been found. ~250M downloads/month. It is also OS-agnostic by design, which means the same code path works on macOS, Windows, and Linux without conditional logic.

**Why `ChainedSecretStore` as the recommended default?** Local dev uses the OS keychain (no daemon available in CI). CI uses environment variables (no keychain daemon available on headless runners). `ChainedSecretStore` tries keychain first, falls back to env vars — the same code runs in both environments. Without it, you'd need environment-specific configuration or two code paths.

**Why `get()` raises `KeyError` instead of returning `None`?** A missing secret should fail immediately and explicitly. A `None` API key passed to LiteLLM produces a cryptic `401 Unauthorized` hours or thousands of tokens later. `KeyError` at `store.get()` tells you exactly which key is missing before any API call is made.

## The problem with `.env` files

`.env` files are plaintext on disk. Common failure modes:
- `.gitignore` entry forgotten after a git init, `git add .` pushes the file
- `.gitignore` entry accidentally removed in a conflict resolution
- `git add -f` bypasses `.gitignore` silently
- Shared laptops / CI images with developer `.env` files baked in
- Backup tools that archive the workspace including `.env`

**Rule: pyarnes_swarm never reads `.env` files.** Secrets are stored in the OS keychain (local dev) or injected as environment variables (CI).

## Trust basis for `keyring`

`keyring` by [jaraco](https://github.com/jaraco/keyring) is the standard Python secrets abstraction. It is used by `pip`, `twine`, and `Jupyter` — three of the most widely audited Python tools. If it had a leak vector it would have been found. Downloads: ~250M/month.

`keyring` is OS-agnostic by design:

| Platform | Backend |
|---|---|
| macOS | Keychain Access (system-level AES-256, locked to your user) |
| Windows | Windows Credential Manager (DPAPI-encrypted, user-bound) |
| Linux (desktop) | libsecret / GNOME Keyring or KWallet |
| Linux (headless/CI) | No daemon available — falls back to `EnvSecretStore` |

Secrets stored via `keyring` are:
- Encrypted by the OS, not by application code
- Inaccessible to other user accounts
- Not stored in any file `git` can track
- Not exposed in `ps aux` or `/proc/`

## `SecretStore` Protocol (`ports.py`)

```python
class SecretStore(Protocol):
    """Port for secret retrieval. Inject at construction — never read .env directly."""

    def get(self, key: str) -> str:
        """Return the secret for *key*. Raises KeyError if missing."""
        ...

    def get_optional(self, key: str) -> str | None:
        """Return the secret for *key*, or None if missing."""
        ...
```

## Implementations (`secrets.py`)

### `KeyringSecretStore` — local dev

```python
class KeyringSecretStore:
    """Reads from OS keychain via keyring (pip/twine/Jupyter-grade trust).

    One-time setup:
        python -m pyarnes_swarm.secrets set openrouter <api-key>
        # stored as keyring.set_password("pyarnes", "openrouter", "<api-key>")

    Zero disk files. Never in git.
    Fails fast on headless environments (ImportError or no daemon).
    """
    def __init__(self, namespace: str = "pyarnes") -> None: ...
    def get(self, key: str) -> str: ...
    def get_optional(self, key: str) -> str | None: ...
```

### `EnvSecretStore` — CI / containers

```python
class EnvSecretStore:
    """Reads from os.environ. Headless/CI fallback.

    GitHub Actions: add to repo Settings → Secrets → Actions → PYARNES_OPENROUTER
    Then inject: env: {PYARNES_OPENROUTER: ${{ secrets.PYARNES_OPENROUTER }}}
    Secret is never written to disk; injected at process start only.
    """
    def __init__(self, prefix: str = "PYARNES_") -> None: ...
    def get(self, key: str) -> str: ...
    def get_optional(self, key: str) -> str | None: ...
```

`EnvSecretStore` uppercases the key and prepends `prefix`:
- `store.get("openrouter")` → `os.environ["PYARNES_OPENROUTER"]`

### `ChainedSecretStore` — hybrid (recommended default)

```python
class ChainedSecretStore:
    """Tries stores in order; returns the first match.

    Local dev:  keyring succeeds; env vars not needed.
    CI runner:  keyring fails (no daemon); env fallback succeeds.
    Same code path, both environments.
    """
    def __init__(self, *stores: SecretStore) -> None: ...
    def get(self, key: str) -> str: ...
    def get_optional(self, key: str) -> str | None: ...
```

Recommended configuration:

```python
from pyarnes_swarm.secrets import ChainedSecretStore, KeyringSecretStore, EnvSecretStore

store = ChainedSecretStore(
    KeyringSecretStore(namespace="pyarnes"),
    EnvSecretStore(prefix="PYARNES_"),
)
```

This is the default store used by `LiteLLMModelClient` if no `secret_store` is provided.

`LiteLLMModelClient` always calls `store.get(provider.api_key_name)` (not `get_optional`) — if the key is missing the call fails fast with `KeyError`. Tests that don't have a real key should inject an `EnvSecretStore` with `monkeypatch.setenv` or a stub `SecretStore`.

## CLI helper

```bash
# One-time local setup (stores in OS keychain)
python -m pyarnes_swarm.secrets set openrouter <api-key>
python -m pyarnes_swarm.secrets set anthropic <api-key>
python -m pyarnes_swarm.secrets set huggingface <token>
python -m pyarnes_swarm.secrets set nvidia_nim <api-key>

# List stored key names (values are never printed)
python -m pyarnes_swarm.secrets list

# Remove a key
python -m pyarnes_swarm.secrets remove openrouter
```

The CLI is a thin wrapper over `keyring.set_password("pyarnes", key, value)`. It never outputs the value.

## CI setup (GitHub Actions)

```yaml
# .github/workflows/ci.yml

jobs:
  test:
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pytest tests/swarm/
        env:
          # Secrets injected from repo Settings → Secrets → Actions
          PYARNES_ANTHROPIC:  ${{ secrets.PYARNES_ANTHROPIC }}
          PYARNES_OPENROUTER: ${{ secrets.PYARNES_OPENROUTER }}
```

`ChainedSecretStore` picks these up via `EnvSecretStore` automatically. No code change between local and CI.

## Testing secrets code

Tests use `EnvSecretStore` or `ChainedSecretStore` directly — never `KeyringSecretStore` (no keychain daemon in CI):

```python
import os
import pytest
from pyarnes_swarm.secrets import EnvSecretStore, ChainedSecretStore

def test_env_secret_store(monkeypatch):
    monkeypatch.setenv("PYARNES_MY_KEY", "test-value")
    store = EnvSecretStore(prefix="PYARNES_")
    assert store.get("my_key") == "test-value"

def test_env_secret_store_missing():
    store = EnvSecretStore(prefix="PYARNES_")
    with pytest.raises(KeyError):
        store.get("nonexistent_key_xyzzy")

def test_chained_falls_back(monkeypatch):
    monkeypatch.setenv("PYARNES_FALLBACK_KEY", "from-env")
    # KeyringSecretStore will fail (no daemon in test) — ChainedStore falls back
    store = ChainedSecretStore(
        KeyringSecretStore(namespace="pyarnes_test"),
        EnvSecretStore(prefix="PYARNES_"),
    )
    assert store.get("fallback_key") == "from-env"
```

## Why NOT a bespoke encrypted file

Rolling encryption means rolling key management. Where does the decryption key live? Usually in another file, or hardcoded, or derived from a password the developer types — each of which reintroduces the original problem. `keyring` delegates key management to the OS, which has spent decades solving exactly this problem with hardware-backed key stores on modern hardware.

## Credential redaction (H9)

Tool-call arguments are logged to JSONL by `ToolCallLogger`. Without redaction, an argument containing an API key (e.g. a tool that accepts a `token` field) would land in the log file in plaintext.

Module: `pyarnes_swarm.safety.redact`

```python
from pyarnes_swarm.safety.redact import redact_dict

def redact_dict(d: dict) -> dict:
    """Return a copy of *d* with values for secret-looking keys replaced by '***REDACTED***'.

    A key is considered secret if its lowercased form contains any of:
    'key', 'token', 'secret', 'password', 'credential', 'auth'.
    Nested dicts are recursed. The input is never mutated.
    """
    ...
```

`redact_dict` is the default `redactor` in `ToolCallLogger.__init__`. Every tool-call entry is passed through `redactor(entry.arguments)` before the JSONL line is written.

```python
@dataclass
class ToolCallLogger:
    path: Path
    redactor: Callable[[dict], dict] | None = redact_dict  # default: redact secret-looking keys

    # Opt out of redaction:
    # logger = ToolCallLogger(path=Path("..."), redactor=None)
```

To disable redaction entirely, pass `redactor=None`. To supply a custom policy, pass any `Callable[[dict], dict]` that returns a sanitized copy.

## Learning resources

- [keyring library documentation](https://keyring.readthedocs.io/) — OS keychain integration, backends per platform, headless fallback configuration
- [asyncio Synchronisation Primitives](https://docs.python.org/3/library/asyncio-sync.html) — `asyncio.Lock` used in `IterationBudget.consume()` (relevant to the secrets injection pattern in hook integration)

## Why not `.env` files?

> See ["The problem with `.env` files"](#the-problem-with-env-files) at the top of this spec for the canonical rationale. This section previously duplicated that content; consolidated into a single home.

## Open questions or deferred items

- **Secret rotation / expiry.** Today the spec covers storage (keyring + env fallback) but not how to rotate a key, mark it expired, or migrate adopters during a vendor key roll.
- **Audit logging of secret access.** No record of which symbol read which secret at what time. Useful for forensics but cost-heavy at runtime; needs an opt-in switch.
- **Multi-region / cross-account scenarios.** When an adopter has separate credentials for prod and staging, the `SecretStore` Protocol does not currently encode that — a single keyring lookup returns one value.
- **Headless keychain bootstrap.** Setting up `keyring` daemons on headless CI / docker is sketched but not codified.
