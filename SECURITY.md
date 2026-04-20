# Security Policy

## Reporting a vulnerability

**Do not report security issues via public GitHub issues or pull requests.**

Use GitHub's private vulnerability reporting instead:

1. Open <https://github.com/Cognitivemesh/pyarnes/security/advisories/new>.
2. Describe the issue, the affected pyarnes version or git ref, and (if possible) a minimal reproduction.
3. Maintainers will acknowledge within 5 business days and coordinate a fix privately.

If GitHub advisories are unavailable, email the repository owner listed on the [pyarnes GitHub profile](https://github.com/Cognitivemesh) with `[pyarnes security]` in the subject line.

## Supported versions

pyarnes ships as a git-URL dependency, not a PyPI package. Adopters pin via `pyarnes_ref` in their Copier answers. The **two** supported refs are:

- `main` — receives all fixes, including security patches.
- The most recent tagged release (`v<MAJOR>.<MINOR>.<PATCH>`) — receives security patches backported as new patch releases.

Older tags receive no security updates. Adopters should update `pyarnes_ref` to the latest tag and run `uv run tasks update` to pull the fix.

## Scope

In scope:

- All code under `packages/*/src/`.
- The Copier template under `template/` (including shipped `.claude/hooks/` and `.claude/skills/`).
- CI workflows under `.github/workflows/` that run on the default branch.

Out of scope:

- Vulnerabilities in transitive dependencies reachable only via the opt-in `graph` dependency group (`code-review-graph`, `graphifyy`) — report those upstream.
- Behaviour of adopter projects generated from the template — those are the adopter's responsibility once scaffolded.
- Hypothetical issues requiring an attacker who already has write access to the repository.

## Commitments

- We will not sue or take adverse action against good-faith security researchers.
- We will credit reporters in the release notes (opt-out available on request).
- Fixes land via a private fork and are merged to `main` once the advisory is published.
