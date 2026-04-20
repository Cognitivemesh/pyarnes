# AgentFS Integration for PR Creation

The `agentfs` package (`toolbox/packages/agentfs/`) provides scoped filesystem access, workflow journaling, BEADS issue tracking, Jujutsu orchestration, and sandboxed command execution. This reference documents the APIs most relevant to the PR creation workflow.

**Package entrypoints**: `agentfs`, `agentfs/fs`, `agentfs/just-bash`

---

## Workspace Isolation

### `createAgentWorkspace(seed: AgentWorkspaceSeed)`

Creates a scoped workspace with deterministic isolation at `features/{id}/{session}/{run}`.
Each workspace derives a unique scope prefix and mount ID, preventing path escape across sessions.
All user inputs are sanitized via `sanitizeScopeToken()` and `normalizeIdentifier()`.

```typescript
import { createAgentWorkspace } from 'agentfs'

const workspace = await createAgentWorkspace({
  kind: 'feature',                    // workspace kind (used in feature token)
  id: 'pr-15-todo-cleanup',           // feature identifier (normalized: lowercase, safe chars)
  rootDir: '/path/to/repo',           // repository root for scoped FS
  sessionId: crypto.randomUUID(),     // unique session identifier
  // Optional:
  // testRunId: 'run-001',            // deterministic run ID (defaults to UUID)
  // strictBeads: false,              // true = throw on missing bd; false = warn (default)
  // backend: 'local',                // FS backend selection
  // env: {},                         // environment overrides
  // agentPrompt: 'Implement PR-15',  // agent context for journaling
})
```

**Return type** (`AgentWorkspace`):
- `adapter` — `FeatureFsAdapter` (scoped FS operations: read, write, mkdir)
- `scope` — `FeatureFsScope` (scope metadata: rootDir, featureId, sessionId)
- `scopePrefix` — deterministic prefix string for isolation
- `scopePath` — absolute path to scoped workspace directory
- `beadsIssueId?` — auto-created BEADS issue ID (if `bd` available)
- `beadsWarnings?` — probing/creation warnings (non-fatal)

**Source**: `agentfs/src/workspace/workspace.ts`

### `createAgentfsBashTool()` (justBash)

Mounts a sandboxed bash environment on the scoped FS. Commands run in isolation with policy enforcement.

```typescript
import { createAgentfsBashTool } from 'agentfs/just-bash'

const bash = createAgentfsBashTool(workspace)
await bash.execute('bunx biome check --write .')
```

Policies prevent escape from the scoped directory. Violations raise `E_JUST_BASH_POLICY`.

**Source**: `agentfs/src/workspace/agentfsBash.ts`

---

## BEADS Issue Tracking

BEADS is the issue tracking component, accessed via the `bd` CLI. It is **optional** — the skill gracefully degrades if `bd` is not installed.

### Probing

```typescript
import { probeBdBinary, probeBdInit } from 'agentfs'

const hasBd = await probeBdBinary()        // Is bd CLI installed?
const hasInit = await probeBdInit()         // Is bd initialized in this repo?
```

### Creating Issues

```bash
# CLI usage (preferred in shell scripts)
bd create "PR-15: Todo cleanup" --description="Implements specs/PR-15-todo-cleanup-a.md" -t feature -p 1 --json
bd update <id> --claim --json
bd close <id> --reason "PR submitted: https://..." --json
bd list --json
```

```typescript
// TypeScript usage (for programmatic workflows)
import { createBeadsIssueForAgentWorkspace } from 'agentfs'

const issue = await createBeadsIssueForAgentWorkspace(workspace, {
  title: 'PR-15: Todo cleanup',
  type: 'feature',
  priority: 1,
})
```

**Source**: `agentfs/src/beads/beadsAgentWorkflow.ts`

---

## Workflow Orchestration

### `runWorkflow()` + `createStepJournal()`

Orchestrates multi-step workflows with JSONL audit trail and automatic rollback on failure.

```typescript
import { runWorkflow, createStepJournal } from 'agentfs'

const journal = createStepJournal('pr-15-implementation')

const result = await runWorkflow({
  journal,
  steps: [
    { name: 'create-branch', execute: async () => { /* ... */ } },
    { name: 'implement', execute: async () => { /* ... */ } },
    { name: 'preflight', execute: async () => { /* ... */ } },
    { name: 'submit', execute: async () => { /* ... */ } },
  ],
})
// result.status → 'completed' | 'failed' | 'rolled-back'
// journal emits NDJSON events for audit trail
```

If a step fails, committed steps are compensated (rolled back) automatically.

**Source**: `agentfs/src/workflow/workflowRunner.ts`

---

## Jujutsu Orchestration

### `VigiaRuntime`

Class-based runtime for jj operations. Owns stacked-change preparation, description, split, and rebase.

```typescript
import { VigiaRuntime } from 'agentfs'

const runtime = new VigiaRuntime({ repoPath: '/path/to/repo' })

// Prepare a stacked change
await runtime.prepareStackedChange({ description: 'feat: PR-15 todo cleanup' })

// Describe the current change
await runtime.describeChange({ message: 'feat(core): add formatIsoDate utility' })

// Rebase onto updated main
await runtime.rebaseStack({ destinationRevision: 'main' })

// Split a change into multiple
await runtime.splitChange({ paths: ['src/a.ts', 'src/b.ts'] })
```

**Source**: `agentfs/src/workflow/vigiaRuntime.ts`

### `VigiaReleaseService`

Changeset preparation and conventional commit enforcement.

```typescript
import { VigiaReleaseService } from 'agentfs'

const release = new VigiaReleaseService({ repoPath: '/path/to/repo' })

// Check if changes are ready for release
const ready = await release.readyCheck()

// Enforce conventional descriptions on all changes
await release.enforceConventionalDescriptions()
```

**Source**: `agentfs/src/workflow/vigiaRuntime.ts`

---

## Error Contracts

AgentFS normalizes all failures into stable `AgentFsError` codes:

| Code | Meaning |
|------|---------|
| `E_SCOPE_ESCAPE` | Attempted path escape from scoped workspace |
| `E_JJ_EXEC_FAILED` | Jujutsu command execution failed |
| `E_JJ_POLICY_VIOLATION` | Jujutsu policy constraint violated |
| `E_JUST_BASH_POLICY` | justBash sandbox policy violated |
| `E_WORKFLOW_ABORTED` | Workflow aborted (step failure + rollback) |
| `E_BEADS_NOT_AVAILABLE` | bd CLI not installed or not initialized |

```typescript
import { isAgentFsError } from 'agentfs'

try {
  await workspace.someOperation()
} catch (err) {
  if (isAgentFsError(err)) {
    console.error(err.code, err.reason)
  }
}
```

---

## Verification Targets

```bash
cd toolbox && bun run test:agentfs           # Core agentfs tests
cd toolbox && bun run test:vigia:readiness   # Vigia workflow readiness
cd toolbox && bun run test:agentfs:uat       # Full UAT suite
cd toolbox && bunx tsc -p packages/agentfs/tsconfig.json --noEmit  # Type check
cd toolbox && bunx biome check packages/agentfs/src                # Lint
```

---

## Key Source Files

| File | Purpose |
|------|---------|
| `agentfs/src/workspace/workspace.ts` | Scoped workspace creation |
| `agentfs/src/workspace/agentfsBash.ts` | justBash sandboxed execution |
| `agentfs/src/workflow/workflowRunner.ts` | Workflow orchestration + rollback |
| `agentfs/src/workflow/vigiaRuntime.ts` | VigiaRuntime + VigiaReleaseService |
| `agentfs/src/beads/beadsAgentWorkflow.ts` | BEADS issue lifecycle |
| `agentfs/src/workflow/jujutsuAdapter.ts` | jj operation dispatch + policy |
| `agentfs/src/workflow/jujutsuCliExecutor.ts` | jj binary probing + execution |
| `agentfs/src/errors/agentFsError.ts` | Error contracts |
