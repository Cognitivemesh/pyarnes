# Worktree Isolation Patterns

Four strategies for isolating PR work from the current working copy.
Choose based on context — agent sessions prefer EnterWorktree; programmatic workflows prefer AgentFS.

---

## Strategy 1: Claude Code `EnterWorktree` (Preferred for Agent Sessions)

Creates an isolated git worktree managed by Claude Code. Auto-cleans on exit if no changes.

**When to use**: Agent sessions where you need to work on a PR without disturbing the current branch.

**Create**:
```
Use the EnterWorktree tool with name: "pr-NN-short-name"
```

**Work**: All file operations happen in the worktree. The main workspace is untouched.

**Exit**:
```
Use ExitWorktree tool:
  action: "keep"    — preserve changes (for PR submission)
  action: "discard" — clean up (for abandoned work)
```

**Verify it worked**:
```bash
# While in worktree:
git rev-parse --show-toplevel   # Should show worktree path, not main repo
git branch --show-current       # Should show worktree branch
```

---

## Strategy 2: AgentFS `createAgentWorkspace()` (Programmatic Workflows)

Creates a scoped workspace with deterministic isolation, justBash, BEADS tracking, and JSONL journaling.
Part of the `agentfs` package (`toolbox/packages/agentfs/`).

**When to use**: Programmatic or multi-agent workflows that need scoped FS, isolated command execution, and audit trails.

**Create** (TypeScript):
```typescript
import { createAgentWorkspace, createAgentfsBashTool } from 'agentfs'

// Scoped workspace: features/{kind-id}/{session}/{run}
const workspace = await createAgentWorkspace({
  kind: 'feature',
  id: 'pr-15-todo-cleanup',
  rootDir: '/path/to/repo',
  sessionId: crypto.randomUUID(),
  // strictBeads: false,  // true = throw on missing bd; false = warn (default)
})

// justBash mounted on scoped FS — commands run in isolation
const { run } = createAgentfsBashTool({ scope: workspace.scope })
await run('bunx biome check --write .')
```

**Key properties**:
- Deterministic scope prefix prevents path escape across sessions (inputs sanitized via `normalizeIdentifier()`)
- `createAgentfsBashTool()` provides sandboxed command execution with policy enforcement
- BEADS issues auto-created per workspace (graceful degradation if `bd` unavailable)
- JSONL audit trail via `createStepJournal()`

**Verify it worked**:
```typescript
console.log(workspace.scopePath)      // Absolute path to scoped directory
console.log(workspace.scopePrefix)    // Deterministic prefix
console.log(workspace.beadsIssueId)   // Auto-created BEADS issue (or undefined)
```

See [agentfs-integration.md](agentfs-integration.md) for full API reference.

---

## Strategy 3: `jj workspace add` (jj-Native CLI)

Creates a separate jj workspace directory. Both workspaces share the same repo but have independent working copies.

**When to use**: CLI workflows in a jj-managed repo where you want a sibling directory for parallel work.

**Create**:
```bash
# Create workspace from main
jj workspace add ../pr-workspace-name --revision main

# Enter it
cd ../pr-workspace-name

# Create bookmark for the new PR
jj bookmark create feat/0.2.25-feature -r @
```

**Sync changes between workspaces**:
```bash
# From the new workspace, fetch changes from the main workspace
jj git fetch --remote origin

# When done, the bookmark is visible from both workspaces
jj bookmark list --all
```

**Cleanup**:
```bash
# From the main workspace
jj workspace forget pr-workspace-name
rm -rf ../pr-workspace-name
```

**Verify it worked**:
```bash
jj workspace list          # Should show both workspaces
jj log -r '@' --limit 1   # Should show working copy in the new workspace
```

---

## Strategy 4: `git worktree add` (Git Fallback)

Standard git worktree. Use when jj is not available.

**Create**:
```bash
git worktree add -b feat/0.2.25-feature ../pr-workspace-name main
cd ../pr-workspace-name
```

**Cleanup**:
```bash
cd /path/to/main/repo
git worktree remove ../pr-workspace-name
# Or if already deleted:
git worktree prune
```

**Verify it worked**:
```bash
git worktree list          # Should show both worktrees
git branch --show-current  # Should show the new branch in the worktree
```

---

## Decision Matrix

| Context | Strategy | Reason |
|---------|----------|--------|
| Claude Code agent session | EnterWorktree | Auto-managed, clean lifecycle |
| Multi-agent with scoped FS | AgentFS workspace | Isolation + BEADS + audit trail |
| jj CLI, parallel work | `jj workspace add` | Native jj, shared repo |
| Git-only, no jj | `git worktree add` | Standard fallback |
| Clean working copy, no parallel | None — direct branch | Simplest path |
