# 16-api-surface-governance

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
