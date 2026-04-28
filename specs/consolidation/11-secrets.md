# pyarnes_swarm — Secrets Management

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
