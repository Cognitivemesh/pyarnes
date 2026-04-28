# 19-claude-judge-plugin

> See also `06-hook-integration.md` § Deferred: Claude Code judge plugin — full deferred plugin design.

## Claude Code Judge Plugin

For deep evaluations within `bench`, pyarnes runs the `ClaudeCliJudge` plugin to run assessments entirely automated via a subprocess, without needing direct Anthropic SDK scaffolding.

### `claude -p` Invocation
Automated LLM judging leverages the `claude -p <prompt>` entry point rather than API bindings. This allows leveraging the exact same tools and internal logic the user uses, effectively bootstrapping evaluation.

### Exit Code Contract
The `ClaudeCliJudge` dictates standard exit codes, which map directly to the error taxonomy framework:
- **`2`**: UserFixableError (Bad input file, unparseable prompt)
- **`3`**: LLMRecoverableError (Failed constraint, but can retry)
- **`4`**: TransientError (Network timeout, rate limit)
