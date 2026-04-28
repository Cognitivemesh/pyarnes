# 16-api-surface-governance

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — API Surface Governance |
> | **Status** | active |
> | **Type** | governance |
> | **Owns** | semver policy, breaking-change rules, __all__ enforcement, stable-surface declaration, deprecation policy stub |
> | **Depends on** | 01-package-structure.md, 04-swarm-api.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 15-tooling-artifacts.md |
> | **Read before** | 17-template-version-control.md |
> | **Not owned here** | actual symbol definitions / package layout (see `01-package-structure.md`); runtime symbols (see `04-swarm-api.md`); evaluation symbols (see `07-bench-integrated-axes.md`); template versioning (see `17-template-version-control.md`) |
> | **Last reviewed** | 2026-04-29 |

> See also `04-swarm-api.md` § Stable public API surface — full symbol inventory and semver policy.

## API Surface Governance

Maintaining a strict Semantic Versioning (SemVer) contract requires enforced discipline over the public API surface.

### Per-Package `__all__` Audit Discipline
Every module must strictly specify its public exports using `__all__`. If a symbol is not in `__all__`, it is considered private and its modification will not trigger a major version bump.

```python
# __init__.py
__all__ = ["AgentLoop", "Swarm", "MessageBus"]
```

### Semver Enforcement Tests
The public API surface is pinned and tested. Any addition or removal of an exported symbol must explicitly update the `test_stable_surface.py` enforcement tests, ensuring accidental leakage or breaking changes are caught in CI.
