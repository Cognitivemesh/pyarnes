# pyarnes_swarm — Claude Code Judge Plugin (Deferred Appendix)

> **Spec header**
>
> | Field | Value |
> |---|---|
> | **Title** | pyarnes_swarm — Claude Code Judge Plugin (Deferred Appendix) |
> | **Status** | appendix |
> | **Type** | historical-appendix |
> | **Tags** | evaluation, claude, judge, deferred |
> | **Owns** | Claude Code judge plugin design notes (deferred), exit code mapping, ClaudeCliJudge sketch |
> | **Depends on** | 10-hook-integration.md |
> | **Extends** | 10-hook-integration.md |
> | **Supersedes** | claudecode-pyarnes-judge-plugin.md |
> | **Read after** | — |
> | **Read before** | — |
> | **Not owned here** | external hook contract / event semantics (see `10-hook-integration.md`); error taxonomy and exit codes (see `01-package-structure.md`, `07-swarm-api.md`) — this file is a deferred-design appendix only |
> | **Last reviewed** | 2026-04-29 |

## Design Rationale

For deep evaluations within `bench`, pyarnes runs the `ClaudeCliJudge` plugin to run assessments entirely automated via a subprocess, without needing direct Anthropic SDK scaffolding.

## Specification

### Claude Code Judge Plugin

#### `claude -p` Invocation
Automated LLM judging leverages the `claude -p <prompt>` entry point rather than API bindings. This allows leveraging the exact same tools and internal logic the user uses, effectively bootstrapping evaluation.

#### Exit Code Contract
The `ClaudeCliJudge` dictates standard exit codes, which map directly to the error taxonomy framework:
- **`2`**: UserFixableError (Bad input file, unparseable prompt)
- **`3`**: LLMRecoverableError (Failed constraint, but can retry)
- **`4`**: TransientError (Network timeout, rate limit)

## Appendix

### Notes

> See also `10-hook-integration.md` § Deferred: Claude Code judge plugin — full deferred plugin design.
