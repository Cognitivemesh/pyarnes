# specs — Feature specifications

The canonical specifications for `pyarnes_swarm` live in [`consolidation/`](consolidation/). All older specs (the legacy `packages/*` mono-repo split, the `PR-01`–`PR-06` graph series, the `harness-feature-expansion` proposal, and the Claude Code judge plugin draft) have been absorbed into the consolidation set. The original source files are no longer present in this tree; their content lives in the consolidation specs listed below, and full text is recoverable from git history.

> **Note:** A previous plan kept absorbed sources under `specs/archive/` with "Absorbed into …" banners. That directory has been removed during cleanup; do not look for it. The mapping of original spec → consolidation target is documented in [`consolidation/14-deferred-features.md`](consolidation/14-deferred-features.md).

## Organization

- [`consolidation/`](consolidation/) — Canonical specifications for `pyarnes_swarm`. New work should land here.

## Consolidation specs (numerical order)

| # | File | Topic |
|---|---|---|
| 00 | [`00-overview.md`](consolidation/00-overview.md) | Consolidation overview and goals |
| 01 | [`01-package-structure.md`](consolidation/01-package-structure.md) | `pyarnes_swarm` package layout |
| 02 | [`02-message-bus.md`](consolidation/02-message-bus.md) | Message bus contract |
| 03 | [`03-model-router.md`](consolidation/03-model-router.md) | Model router and provider selection |
| 04 | [`04-swarm-api.md`](consolidation/04-swarm-api.md) | Stable public `Swarm` API surface |
| 05 | [`05-dead-code-audit.md`](consolidation/05-dead-code-audit.md) | Dead-code audit policy |
| 06 | [`06-hook-integration.md`](consolidation/06-hook-integration.md) | Hook contract and adopter shapes |
| 07 | [`07-bench-integrated-axes.md`](consolidation/07-bench-integrated-axes.md) | Bench evaluators, scorers, use cases |
| 08 | [`08-test-strategy.md`](consolidation/08-test-strategy.md) | Test strategy |
| 09 | [`09-test-map.md`](consolidation/09-test-map.md) | Test coverage map |
| 10 | [`10-provider-config.md`](consolidation/10-provider-config.md) | Provider configuration |
| 11 | [`11-secrets.md`](consolidation/11-secrets.md) | Secrets handling and credential redaction |
| 12 | [`12-token-budget.md`](consolidation/12-token-budget.md) | Token budget enforcement |
| 13 | [`13-run-logger.md`](consolidation/13-run-logger.md) | Run capture and JSONL log schema |
| 14 | [`14-deferred-features.md`](consolidation/14-deferred-features.md) | Historical pointer to absorbed deferred features |
| 15 | [`15-tooling-artifacts.md`](consolidation/15-tooling-artifacts.md) | Tooling and build artifacts |
| 16 | [`16-api-surface-governance.md`](consolidation/16-api-surface-governance.md) | API surface governance (see also `04`) |
| 17 | [`17-template-version-control.md`](consolidation/17-template-version-control.md) | Template version control (see also `06`) |
| 18 | [`18-evaluation-taxonomy.md`](consolidation/18-evaluation-taxonomy.md) | Evaluation taxonomy (see also `07`) |
| 19 | [`19-claude-judge-plugin.md`](consolidation/19-claude-judge-plugin.md) | Claude Code judge plugin (see also `06`) |
| 20 | [`20-message-safety.md`](consolidation/20-message-safety.md) | Message safety and validation |
| 21 | [`21-loop-hooks.md`](consolidation/21-loop-hooks.md) | Agent loop hook integration |
| 22 | [`22-transport.md`](consolidation/22-transport.md) | Transport abstraction |
| 23 | [`23-graph-package.md`](consolidation/23-graph-package.md) | Code-review graph (absorbed from PR-01..PR-06) |
