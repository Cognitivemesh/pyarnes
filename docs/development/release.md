# Release workflow

pyarnes does not publish to PyPI. Adopters pin by git ref via `pyarnes_ref`
in their Copier answers. A release is a signed git tag that downstream
projects bump to.

## Cutting a release

1. Land all PRs for the release on `main`; confirm `uv run tasks check` is green.
2. Pick a version per the [semver policy in `CHANGELOG.md`](https://github.com/Cognitivemesh/pyarnes/blob/main/CHANGELOG.md#versioning-policy):
   - **MAJOR** — a public symbol disappeared, a base-class signature changed, an error-class inheritance flipped.
   - **MINOR** — new public symbols, new optional kwargs, new built-in `Guardrail`/`Scorer` subclass.
   - **PATCH** — bug fixes, docstring changes, private-surface refactors.
3. Move `CHANGELOG.md`'s `## [Unreleased]` content into a new `## [vX.Y.Z] - YYYY-MM-DD` section. Leave `## [Unreleased]` empty for the next cycle.
4. Commit, tag, push:
   ```bash
   git tag vX.Y.Z
   git push --tags
   ```
5. Announce the tag. Adopters update by editing their `.copier-answers.yml`:
   ```yaml
   pyarnes_ref: vX.Y.Z
   ```
   then running `uv run tasks update` (wraps `uvx copier update`) followed
   by `uv sync` to resolve the new git URLs.

## What `uv run tasks update` does

`uv run tasks update` invokes `copier update` against the ref recorded in
`.copier-answers.yml`. Copier replays every question, applies templated
file updates, and leaves user edits intact where possible. Conflicts are
reported as three-way merge markers the adopter resolves manually.

## What adopters commit to

When pinning a specific tag, adopters get:

- Every symbol in the public surface table (see `CHANGELOG.md`) to remain
  importable until the next MAJOR.
- The `ToolHandler`, `ModelClient`, `Guardrail`, and `Scorer` base-class
  signatures to remain stable.
- The `ToolCallLogger` JSONL **field set** to remain stable (field *order*
  is not guaranteed — parse as JSON, not as column-oriented text).
- The `pyarnes-tasks` CLI surface to remain stable (task names and
  `[tool.pyarnes-tasks]` keys).

Things adopters must **not** depend on, per the private-surface list:

- Any underscore-prefixed attribute on a public class.
- Log event string names (`"tool.pre"`, `"guardrail.command_blocked"`, …).
- The concrete type of `Lifecycle.history`.

## Stability enforcement

`tests/unit/test_stable_surface.py` is the CI gate. If a public symbol
disappears from any package's `__all__`, it fails. If star-importing a
package yields anything outside `__all__`, it fails. If an expected symbol
cannot be resolved, it fails. Keep the test in lockstep with
`CHANGELOG.md`.
