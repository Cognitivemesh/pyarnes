# Review of Block C — Phase 8a: Heading-to-bucket classification

> **Source plans:** the plan being reviewed (`block-c-phase-8a-classification.md`) and its parent (`please-plan-execute-the-soft-twilight.md`) live in the local planning workspace and are not committed to this repo. This review is published here as a permanent record of the analysis; references to those plans in the body are by name only.
>
> Verified against: live `specs/consolidation/` tree on `main` (24 files), heading inventory, three appendix headers.

## TL;DR

The plan is structurally sound — the bucket schema, disposition vocabulary, and "shape-first, content-second" framing are well-grounded. But it ships with **three factual errors that will trip the pre-flight check**, **a schema/verification conflict that lets the table claim completeness while missing synthesis rows**, and **a heuristic table that covers only ~60 % of real headings**. Fix those, then ship.

Issues are graded:

- **Blocker** — pre-flight or verification will fail; or wrong artifact will be produced.
- **Issue** — correctness gap that increases AMBIG count or rework risk.
- **Enhancement** — quality-of-life or cost reduction.

---

## Blockers (factual / will break execution)

### B1 — Spec count is 24, not 23

`ls specs/consolidation/*.md | wc -l` returns **24** (files `00-…` through `23-…`, inclusive). The plan repeatedly says "23 specs":

- Step 1 pre-flight: `ls specs/consolidation/*.md | wc -l   # expect: 23` — **will fail.**
- "20 active specs (`Type` is anything except `historical-appendix`)" — actual count is 21 active (24 − 3 appendices `14, 18, 19`).
- The active-spec list at L41 enumerates 21 numbers (`00…13, 15, 16, 17, 20…23`) but the prose claims "that's 20."

Fix: change "23" → "24", "20 active" → "21 active", and the pre-flight expectation. Hand-off counts in Step 8 ("Active specs covered: 20 / 20") shift to `21 / 21`.

### B2 — Step 4 heuristic mis-handles already-existing standalone `## Cross-references`

The Context paragraph claim ("*none* of the 8 Phase-6 specs has a `## Cross-references` section") is technically true — Phase 6 added Open Questions sections to specs 02, 04, 08, 09, 10, 11, 12, 16, none of which gained Cross-references. So the narrative stands.

But three *other* specs already do have a top-level `## Cross-references`:

- [00-overview.md](../../specs/consolidation/00-overview.md) L237
- [13-run-logger.md](../../specs/consolidation/13-run-logger.md) L199
- [23-graph-package.md](../../specs/consolidation/23-graph-package.md) L156

Step 4's L141 row reads:

| Existing heading pattern | Default target bucket | Disposition |
|---|---|---|
| `## See also` / existing `## Cross-references` | `Cross-references` | `merge_into_existing` |

`merge_into_existing` is wrong for a standalone existing top-level `## Cross-references` — there's nothing to merge into; the heading *is* the destination. The right disposition is `keep_as_h2` (and likely augment with the typed list synthesized from header fields).

Fix: split L141 into two rows. `## See also` (subordinate alias) → `Cross-references` / `merge_into_existing`; existing standalone `## Cross-references` → `Cross-references` / `keep_as_h2` (with a note that 8b should append synthesized typed-ref lines, not replace the existing prose). Without this split, 8b agents handed those three specs may either delete the existing heading and re-create it, or double-up.

### B3 — 10's "Cross-Provider Cost Comparison" was NOT deduped in Phase 4

Step 5 (L156) says "10's `## Cross-Provider Cost Comparison` (already deduplicated by Phase 4)". The current state of [10-provider-config.md](../../specs/consolidation/10-provider-config.md) shows **both** still present:

- L119: `## Cross-provider cost comparison via LLMCostRouter`
- L188: `## Cross-Provider Cost Comparison`

Either Phase 4 didn't run, or it deduped the prose but left two H2s. Phase 8a must classify both rows; the safe call is `merge_into_existing` for L188 → L119's section, both targeting `Canonical Contract`.

### B4 — Schema vs. verification criterion conflict on `synthesize_new` rows

- Step 3's row schema says **one row per existing H2 heading** (columns include `current_h2` and `line` from the inventory).
- Step 6 says synthesized buckets get a row with `disposition=synthesize_new` and a `notes` source pointer.
- Verification item 1 says "Every `## ` heading … appears as exactly one row in the classification table."
- Verification item 4 says "rows marked `synthesize_new` count toward coverage."

These can't all hold simultaneously: a `synthesize_new` row has no `current_h2` to anchor on, so item 1's "exactly one row per heading" is technically violated by every synthesis row. Worse, **Step 7's per-spec coverage section is a parallel structure that duplicates synthesis tracking**, so the same fact ends up in two places with no reconciliation rule.

Fix (pick one):
- (a) Drop `synthesize_new` rows from the main table; track all synthesis exclusively in Step 7's coverage section. Then the table has the clean invariant "exactly one row per existing H2", and Step 7 is the only synthesis source.
- (b) Allow the main table to carry `synthesize_new` rows (with `current_h2=—`, `line=—`); delete Step 7 entirely as redundant. Then verification item 1 becomes "every existing `## ` heading has exactly one row".

(a) is cleaner because synthesis is at the spec/bucket level, not the heading level — there's no heading to anchor a row on.

### B5 — Spec 14 has zero H2 headings

[14-deferred-features.md](../../specs/consolidation/14-deferred-features.md) has no `## ` lines (only header table + body prose). Under the current "one row per H2" schema this spec contributes zero rows, but it needs full appendix-bucket synthesis. The plan's appendix flow assumes existing headings to classify; for 14 there are none.

Fix: explicitly carve out a "zero-H2 spec" path that goes straight to a synthesis-only block in Step 7's per-spec section.

---

## Issues (correctness / completeness gaps)

### I1 — Heuristic table covers ~60 % of real headings

Cross-checked against the live inventory. Headings with no row in Step 4's table that will need ad-hoc judgment (and therefore inflate AMBIG count) include:

| Heading | Likely bucket | Specs affected |
|---|---|---|
| `## Goals` | `Why this exists` | 00 |
| `## Intended outcome` | `Purpose` (extension) or `Why this exists` | 00 |
| `## When to use pyarnes_swarm` | `Scope` | 00 |
| `## Spec inventory and reading paths` | `Cross-references` (it's nav) | 00 |
| `## Distribution and documentation` | `Integration Points` | 00 |
| `## Key concepts` | `Canonical Contract` | 01, 02, 03 |
| `## What moved where` / `## What was deleted` | `Design Rationale` (history) | 01 |
| `## Public API stability and semver` | `Canonical Contract` | 01 |
| `## Trust basis for keyring` | `Design Rationale` | 11 |
| `## CLI helper` | `Canonical Contract` | 11 |
| `## CI setup (GitHub Actions)` | `Integration Points` | 11 |
| `## .pyarnes/ directory layout` / `## .pyarnes/runs/<run_id>/ layout` | `Canonical Contract` | 06, 13 |
| `## Adopter shapes (Copier template)` | `Integration Points` | 06 |
| `## Template Version Control` (the sole H2 of 17) | `Canonical Contract` | 17 |
| `## API Surface Governance` (sole content H2 of 16) | `Canonical Contract` | 16 |
| `## Three control layers` / `## System overhead baseline` / `## Token counting APIs` | `Canonical Contract` | 12 |
| `## Library summary` | `Canonical Contract` | 12 |
| `## Claude Code session integration` | `Integration Points` | 12 |
| `## Repository Hygiene` / `## Template Scaffolding Exclusions` / `## Development Tasks` | `Canonical Contract` (mostly) | 15 |

Pre-populating these (or a "fallback rule: domain-named class/protocol/file/dir headings → `Canonical Contract`") will roughly halve the classification time and reduce AMBIG load.

### I2 — Spec 11 has near-duplicate headings the plan misses

[11-secrets.md](../../specs/consolidation/11-secrets.md):

- L29: `## The problem with .env files`
- L253: `## Why not .env files?`

These are textually distinct but topically overlap (the existence of L253 after the credential redaction section reads like a leftover/relocation candidate). Step 5's "known ambiguity offenders" mentions L29 and `## Why NOT a bespoke encrypted file`, but not the L29/L253 pair. Add to Step 5 with disposition `merge_into_existing` (L253 → L29) targeting `Design Rationale`.

### I3 — Disposition vocabulary mixes two operations under `move_only`

The Step 4 heuristic table assigns `move_only` to two semantically distinct cases:

- `## Why a ModelRouter?` → `Why this exists` (rename heading + move under bucket)
- `## Tool-dispatch and error-routing` → `Integration Points` (no rename; just relocate under bucket H2)

If 8b's executable action is the same ("section sits under bucket H2"), this is fine. But the current `move_only` definition ("heading is renamed to match the bucket") only covers case 1; case 2 fits neither `keep_as_h2` (different heading text from the bucket) nor `move_only` as currently defined.

Fix: either redefine `move_only` as "section relocates under bucket H2; existing heading text may be preserved as an H3 or replaced with bucket label", or split into `rename_and_move` vs `relocate_only`.

### I4 — `MERGE_INTO:<other_h2>` overloads the `target_bucket` column

Step 3's schema lets `target_bucket` be one of "9 active buckets / 5 appendix buckets / `MERGE_INTO:<other_h2>`". Mixing bucket identity with merge directive in one cell makes the table harder to validate ("count rows per bucket" needs special-case parsing).

Fix: add a `merge_target` column. `target_bucket` always names the destination bucket (the merge target's bucket). `disposition=merge_into_existing` is the signal to read `merge_target`.

### I5 — Verification criterion 4 picks an arbitrary "minimum 4 buckets"

L230: minimum-required = `Purpose`, `Canonical Contract`, `Cross-references`, plus one of `Scope` or `Why this exists`. Why these four? The locked v5 order has 9 buckets — silently allowing 5 of them to be empty is a content-completeness loophole. `Out of scope` and `Design Rationale`, in particular, are arguably more load-bearing than `Cross-references` for spec hygiene.

Fix: either justify the choice (e.g., "these four are the v5 hard floor; everything else is best-effort") or strengthen to "every locked-order bucket has at least an empty H2 stub or a covered row." Worth a one-line note from the user during Step 8 review.

### I6 — Pre-flight `python3 /tmp/check-reciprocals.py` assumes ephemeral state

Block A's parent plan creates the script at `/tmp/check-reciprocals.py`. If Phase 8a runs in a fresh session (likely, given block separation), `/tmp/` is gone. Either:
- (a) Block A's PR commits the script to `scripts/check-reciprocals.py` (preferred — also useful as a CI check), or
- (b) Phase 8a's pre-flight regenerates it inline before running.

Either is fine; the plan should say which.

### I7 — Estimate is tight; review iterations are likely under-budgeted

24 specs × ~10 H2s ≈ ~240 rows × 30 sec/row = 2 hours raw classification, with no AMBIG resolution. Step 8's "≤ 2 review iterations" assumes the user agrees with most rows on first pass — for a 240-row table with judgment calls, 3–4 iterations is more realistic. The "If Step 3 stretches past 90 min, classify more aggressively" escape valve is good but doesn't address review-cycle bloat.

Fix: budget Step 8 at 30–45 min (not 15) and label the 2-hour total as "best case, single review iteration."

---

## Enhancements (quality of life)

### E1 — Compact Step 7's per-spec coverage into a single matrix

Step 7 produces 21 sub-sections (one per active spec) of bullet lists. A single matrix (rows = specs, columns = 9 buckets, cells = ✓ / `synth:Owns` / `merge:<source>` / —) is denser, easier to spot gaps in, and grep-able. Same data, ~⅕ the lines.

### E2 — Promote the artifact out of `/tmp/`

The Deliverable hedges: "Optionally check it into the repo at `specs/consolidation/.phase-8-classification.md`". Phase 8b agents need this file as input, and a leading-dot path is hidden in many tools. Make it default-committed at e.g. `specs/consolidation/_phase-8-classification.md` (underscore, not dot) or `docs/process/phase-8-classification.md`. `/tmp/` survives across sessions only by accident.

### E3 — Add a circuit breaker for "schema is wrong"

The plan correctly forbids new buckets ("No 'improvements' to the order; no new buckets"). But classification is the only point where the schema is empirically tested. If 3+ specs reveal a structural need the v5 schema didn't anticipate (e.g., `Migration` as a recurring section), the plan has no escalation path. Add: "If you find ≥ N specs requiring a bucket the schema lacks, stop classifying and escalate to user before Step 8b begins."

### E4 — Snapshot the inventory file

Step 2 builds `/tmp/spec-h2-inventory.md`. Commit this alongside the classification artifact (or include it as a fenced block in the same file) so the table's `line` column is reproducible against a known snapshot. Otherwise line numbers drift if any spec is touched between 8a and 8b.

### E5 — Pre-populate a "fallback heuristic" rule

Most uncovered headings in I1 are "domain-named class/protocol/file path/section name." A single fallback rule — *"if the heading is a class/protocol/file/dir/method name in backticks, default to `Canonical Contract`, `disposition=demote_to_h3`"* — would catch ~80 % of the misses without bloating the heuristic table.

### E6 — Add an explicit summary count for `keep_as_h2` after pre-fix

Once B2/B3 are fixed, the three already-existing `## Cross-references` sections plus various `## Design Rationale` / `## Open questions or deferred items` sections will pre-populate `keep_as_h2` rows. Adding "expected `keep_as_h2` floor: ~30 rows" to Step 8's stats anchors the sanity check.

### E7 — Tag rows with PR-batch from the parent plan

The parent plan splits Phase 8 into 3 PRs (`core-runtime`, `integrations-safety + evaluation-capture + optional-subsystem`, `governance + testing + historical-appendix`). Add a `pr_batch` column (A/B/C) to the classification table so 8b's parallel-agent dispatch can filter directly without re-deriving the grouping.

---

## What's working well (don't change)

- The "shape-first, content-second" framing.
- The locked 9-bucket / 5-appendix schema is correctly transcribed.
- The hard constraint "Phase 8a does NOT modify any spec file" is the right invariant — pure classification, zero file edits, no temptation to refactor under cover of "moving sections."
- Step 5's known-ambiguity-offenders list is the right place for hand-curated calls; it captures the 04 / 05 / 07 / 12 / 20 / 23 cases that would otherwise burn AMBIG flags.
- Disposition codes (`keep_as_h2` / `demote_to_h3` / `merge_into_existing` / `move_only` / `synthesize_new`) cover the action space well — the only quibbles are vocabulary tightness (I3) and the merge-directive overload (I4).
- The user-review gate at Step 8 is the right shape: print stats, surface AMBIGs, iterate.
- Block-then-block sequencing with no interleave is preserved correctly from the parent plan.

---

## Suggested patch order

If you fix all of the above, the natural sequence is:

1. **Blockers first** (B1 spec count, B2 cross-refs claim, B3 10's dedupe claim, B4 schema/verification reconciliation, B5 zero-H2 spec carve-out). All five are wording or schema fixes — should take ~20 min.
2. **I1 + E5** together: extend the heuristic table with the missing patterns *and* add the fallback rule. ~15 min.
3. **I2** (11's L253 dup) — add to Step 5. ~2 min.
4. **I3, I4** (vocabulary cleanup) — pick a convention and apply. ~5 min.
5. **I5, I6, I7** (verification floor, script path, estimate) — narrative tweaks. ~10 min.
6. **E1–E7** at your discretion — none are blockers; E2 (artifact path) is the highest-value one.

Total revision time: ~1 hour. The plan is close to ready; these are surface-area issues, not structural ones.

---

## Risk if shipped as-is (no fixes applied)

Concrete failures the next person running this plan would hit, in order:

1. **Step 1 pre-flight aborts** on `ls specs/consolidation/*.md | wc -l` (returns 24, plan expects 23). The agent stops before classification begins.
2. If the agent edits the pre-flight to pass, **Step 2's inventory carries 24 specs through but the active-count math (`20 / 20`) is still wrong** — the user-review gate at Step 8 will print misleading stats.
3. **Three specs (00, 13, 23) get their existing `## Cross-references` mis-classified** as `merge_into_existing` per L141. Phase 8b agents will either (a) delete the heading and re-create it from header fields, dropping any existing prose; or (b) double-create, leaving two `## Cross-references` sections. (a) is a content-loss event — Phase 8c's word-count check would catch it, but only after the damage.
4. **Spec 10's two `Cross-Provider Cost Comparison` H2s** both get `keep_as_h2` (no Step-5 entry corrects them), so the dedup work the plan claims was already done… still doesn't get done.
5. **Spec 14 (zero H2s) silently falls out of the table.** Phase 8b never gets a row for it, so 8b agents won't synthesize the appendix bucket structure. Spec 14 ships with no buckets.
6. **AMBIG count balloons** — the heuristic table covers ~60 % of real headings, so the classifier flags ~40 % for user review at Step 8. With 240 rows that's ~95 AMBIG flags, blowing the 15-min review budget by an order of magnitude.

Net: at least one content-loss event (item 3), one silently-skipped spec (item 5), and a review gate that takes 2–4× longer than estimated.

## Final verdict

**Approve with mandatory revisions.** The plan's spine — bucket schema, disposition vocabulary, classification-then-execute split, Phase 8b parallel-agent dispatch, Step 8 user-review gate — is sound. None of the defects above require redesign; all are wording, schema-cell, or table-coverage fixes.

**Do not start Phase 8a until at least the five blockers (B1–B5) are patched.** I1 (heuristic coverage) and E5 (fallback rule) are strong-recommend; I2/I3/I4/I5/I6/I7 and E1/E2/E3/E4/E6/E7 are nice-to-have and can be deferred to a second editing pass without risking execution.

Recommended next step: have the plan author (or a follow-up agent) apply patches per the "Suggested patch order" above, then re-run a focused diff-review on the blockers before kickoff.

## Coverage of this review (transparency)

What was verified against live state on `main`:

- Spec count and filename inventory (`ls specs/consolidation/*.md`).
- H2 inventory across all 24 specs (the inventory the plan's Step 2 would generate).
- Three appendix specs' header `Type` fields (14, 18, 19 — all confirmed `historical-appendix`).
- The plan's `is_appendix` grep pattern actually matches those three specs.
- Three already-existing top-level `## Cross-references` sections (00, 13, 23).
- Spec 10's two `Cross-Provider Cost Comparison` H2s (both still present at L119, L188).
- Spec 11's two near-duplicate `.env`-related H2s (L29, L253).
- Spec 14 has zero H2s.
- The Phase-6 specs set (per the parent plan) does not overlap with the three Cross-references-having specs — so the plan's narrative claim is technically correct.

What was **not** verified (out of scope for this review):

- Whether Block A's reciprocity audit script actually exists yet (the plan assumes `/tmp/check-reciprocals.py` is callable; this depends on Block A being merged).
- Whether the v5 master plan's locked H2 order is itself correct — taken as given.
- Whether each individual `target_bucket` recommendation in Step 4's heuristic table is right; only spot-checked for the cases the plan explicitly enumerates and for the I1 additions.
- The 5-bucket appendix schema's fit against specs 18 and 19 — they each have exactly one content H2 (`## Evaluation Use-Case Taxonomy` and `## Claude Code Judge Plugin` respectively), neither of which matches any of the 5 appendix buckets. By the same logic as B5, both will need full appendix-bucket synthesis. Worth re-using the B5 carve-out.
- Phase 8b's per-spec agent prompt template (out of 8a's scope).
- Phase 8c's word-count regression check (out of 8a's scope).
- Whether the planning estimate scales linearly with spec count (24 vs the plan's 23 implies a ~5 % time bump, well within noise).
