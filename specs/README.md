# specs — Feature specifications

The canonical specifications for `pyarnes_swarm` live in [`consolidation/`](consolidation/). All older specs (the legacy `packages/*` mono-repo split, the `PR-01`–`PR-06` graph series, the `harness-feature-expansion` proposal, and the Claude Code judge plugin draft) have been absorbed into the consolidation set. The original source files are no longer present in this tree; their content lives in the consolidation specs listed below, and full text is recoverable from git history.

> **Note:** A previous plan kept absorbed sources under `specs/archive/` with "Absorbed into …" banners. That directory has been removed during cleanup; do not look for it. The mapping of original spec → consolidation target is documented in [`consolidation/21-deferred-features.md`](consolidation/21-deferred-features.md).

## Organization

- [`consolidation/`](consolidation/) — Canonical specifications for `pyarnes_swarm`. New work should land here.

## Browse In A Browser

You can browse the specs locally without building the full MkDocs site:

```bash
uv run scripts/serve_specs.py --open
```

What this does:

- Serves the specs viewer at `http://127.0.0.1:8000/`
- Opens `specs/README.md` as the landing page
- Renders local `.md` files as HTML while preserving relative links to other specs and diagrams

Useful variants:

```bash
uv run scripts/serve_specs.py --port 9000
uv run scripts/serve_specs.py --host 0.0.0.0 --port 9000
```

The viewer stylesheet lives at [`consolidation/assets/specs.css`](consolidation/assets/specs.css). The server script is [`../scripts/serve_specs.py`](../scripts/serve_specs.py).

## Consolidation specs (renumbered to match header order)

The consolidation specs now use the same numeric order declared by their
header links. The set now spans `00` through `24`: active runtime and
governance specs occupy `00` through `20` plus `24`, while historical
appendices live at `21` through `23`.

| # | File | Group | Topic |
|---|---|---|---|
| 00 | [`00-overview.md`](consolidation/00-overview.md) | core-runtime | Consolidation overview, inventory, reading paths, dependency map |
| 01 | [`01-package-structure.md`](consolidation/01-package-structure.md) | core-runtime | `pyarnes_swarm` package layout |
| 02 | [`02-test-strategy.md`](consolidation/02-test-strategy.md) | testing | TDD discipline |
| 03 | [`03-test-map.md`](consolidation/03-test-map.md) | testing | Test migration map |
| 04 | [`04-dead-code-audit.md`](consolidation/04-dead-code-audit.md) | testing | Dead-code audit policy |
| 05 | [`05-message-bus.md`](consolidation/05-message-bus.md) | core-runtime | Message bus contract |
| 06 | [`06-model-router.md`](consolidation/06-model-router.md) | core-runtime | Model selection (which model) |
| 07 | [`07-swarm-api.md`](consolidation/07-swarm-api.md) | core-runtime | Stable public `Swarm` API surface — runtime center of gravity |
| 08 | [`08-token-budget.md`](consolidation/08-token-budget.md) | core-runtime | Token budget enforcement |
| 09 | [`09-loop-hooks.md`](consolidation/09-loop-hooks.md) | integrations-safety | Internal in-process loop hooks |
| 10 | [`10-hook-integration.md`](consolidation/10-hook-integration.md) | integrations-safety | External Claude Code hooks |
| 11 | [`11-message-safety.md`](consolidation/11-message-safety.md) | integrations-safety | Sanitization and prompt-injection defense |
| 12 | [`12-transport.md`](consolidation/12-transport.md) | integrations-safety | Transport (through which transport) |
| 13 | [`13-provider-config.md`](consolidation/13-provider-config.md) | integrations-safety | Provider selection (through which provider) |
| 14 | [`14-secrets.md`](consolidation/14-secrets.md) | integrations-safety | Secrets handling and credential redaction |
| 15 | [`15-bench-integrated-axes.md`](consolidation/15-bench-integrated-axes.md) | evaluation-capture | Bench evaluators, scorers, use cases |
| 16 | [`16-run-logger.md`](consolidation/16-run-logger.md) | evaluation-capture | Run capture and JSONL log schema |
| 17 | [`17-tooling-artifacts.md`](consolidation/17-tooling-artifacts.md) | testing | Tooling and build artifacts |
| 18 | [`18-api-surface-governance.md`](consolidation/18-api-surface-governance.md) | governance | Stable surface and semver promises |
| 19 | [`19-template-version-control.md`](consolidation/19-template-version-control.md) | governance | Template version control |
| 20 | [`20-graph-package.md`](consolidation/20-graph-package.md) | optional-subsystem | Code-review graph (absorbed from PR-01..PR-06) |
| 21 | [`21-deferred-features.md`](consolidation/21-deferred-features.md) | historical-appendix | Pointer to absorbed deferred features |
| 22 | [`22-evaluation-taxonomy.md`](consolidation/22-evaluation-taxonomy.md) | historical-appendix | Evaluation taxonomy appendix |
| 23 | [`23-claude-judge-plugin.md`](consolidation/23-claude-judge-plugin.md) | historical-appendix | Claude Code judge plugin appendix |
| 24 | [`24-documentation-governance.md`](consolidation/24-documentation-governance.md) | governance | Documentation governance, audience split, and semver discoverability |
