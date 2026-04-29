---
mode: agent
description: 'Build or refresh the ClaudeMap visual architecture map. Use to initialize, rebuild, or update the interactive map of this project.'
---

# ClaudeMap Setup / Refresh

## Install (first time only)

If ClaudeMap is not installed yet:

```bash
npx @quinnaho/claudemap install
```

Restart Claude Code after install.

## Generate the map

Run `/setup-claudemap` in Claude Code to analyze the repo and build the map.

If the map already exists and you just want to update it after code changes:

```
/refresh
```

## Explore

- `/explain $QUESTION` — Claude answers step-by-step with visual highlighting on the map.
- `/show $WHAT_TO_SEE` — Claude navigates the map to the thing you want to see.
- `/create-map` — Create a focused sub-map for a specific subsystem.
