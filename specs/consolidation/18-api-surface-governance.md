# pyarnes_swarm — API Surface Governance

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — API Surface Governance |
> | **Status** | active |
> | **Type** | governance |
> | **Tags** | api, governance, semver |
> | **Owns** | semver policy, breaking-change rules, __all__ enforcement, stable-surface declaration, deprecation policy stub |
> | **Depends on** | 01-package-structure.md, 07-swarm-api.md |
> | **Extends** | — |
> | **Supersedes** | — |
> | **Read after** | 17-tooling-artifacts.md |
> | **Read before** | 19-template-version-control.md |
> | **Not owned here** | actual symbol definitions / package layout (see `01-package-structure.md`); runtime symbols (see `07-swarm-api.md`); evaluation symbols (see `15-bench-integrated-axes.md`); template versioning (see `19-template-version-control.md`) |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

Maintaining a strict Semantic Versioning (SemVer) contract requires enforced discipline over the public API surface.

## Specification

### API Surface Governance

#### Root package `__all__` contract

The package root is intentionally constrained. `pyarnes_swarm.__all__` is **exactly** this 8-symbol set:

```python
__all__ = [
	"Swarm",
	"AgentSpec",
	"LoopConfig",
	"GuardrailChain",
	"ToolRegistry",
	"ModelClient",
	"InMemoryBus",
	"configure_logging",
]
```

These are the only names permitted to be imported from the package root in the stable 80%-case API. Adding a ninth root export is a contract change, not a routine convenience addition.

#### Deep-path public APIs stay deep-path

Public symbols outside that 8-symbol root set must remain available only via explicit module paths such as `pyarnes_swarm.agent`, `.ports`, `.errors`, `.guardrails`, `.bench`, `.routing`, or another subsystem module documented by its owning spec. A module-level `__all__` may define a public deep-path surface; it does **not** imply entitlement to package-root re-export.

```python
# valid deep-path import
from pyarnes_swarm.agent import AgentRuntime

# invalid root widening unless KR1.2 / governance specs are updated
from pyarnes_swarm import AgentRuntime
```

#### Semver enforcement tests

The public API surface is pinned and tested. CI must assert both:

- `len(pyarnes_swarm.__all__) == 8`
- exact set equality with `{Swarm, AgentSpec, LoopConfig, GuardrailChain, ToolRegistry, ModelClient, InMemoryBus, configure_logging}`

Any change to that root set must update the enforcement test and the owning specs in the same patch; otherwise it is treated as accidental API leakage.

#### Review rule for contributors

When a contributor wants to expose a new symbol, the default move is **not** to add it to `pyarnes_swarm.__init__`. The default move is to document the symbol under its subsystem module and keep the package root unchanged. Root widening is exceptional and must justify why the symbol belongs in the 8-symbol onboarding path.

## Appendix

### Notes

> See also `07-swarm-api.md` § Stable public API surface — 8-symbol root contract, deep-path split, and semver policy.

### Open questions or deferred items

- **Deprecation policy.** Currently no spec governs how breaking changes are announced, what the deprecation window is, or how `DeprecationWarning` should be wired (decorator? `__getattr__` shim? CHANGELOG only?). Belongs here once the policy is decided.
- **Stable-surface CHANGELOG generation.** The `__all__` declaration is the source of truth for the public surface, but there is no automated diff against the previous tagged release. A pre-release task should compare `__all__` snapshots and surface additions / removals.
- **Pre-1.0 stability promises.** The spec implies semver but does not state whether 0.x releases follow strict semver, "best-effort" semver, or are explicitly unstable. Adopters need to know.
