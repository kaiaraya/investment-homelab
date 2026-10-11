# Implementation Plan — Loop Engineering & Task Decomposition (Cline Efficiency)

> Status: **IMPLEMENTED (2026-10-06)** — process/rules change only; see `## Cline Report` at the end.

## Overview
Codify "loop engineering" as a first-class mandatory rule for both Antigravity and Cline, so every
task is **decomposed into atomic units up-front** and executed through a **tight
DECOMPOSE → EXECUTE → VERIFY → REFLECT → REPEAT loop** instead of one big prompt/batch verified only
at the end. This is a **process/rules change only** (no application code, no tests). It consolidates
the loop fragments already present in `broker_pdca_rca.md`, `stepwise-approval`, and `watch-and-learn`
under one canonical rule.

Reference: "Loop Engineering vs Prompt Engineering" — small units + short verify loops beat one big
prompt (fail-fast, self-correcting).

## Files
- **NEW** `.agents/rules/loop_engineering.md` — the canonical methodology (bilingual, matching existing rule style).
- **MODIFY** `AGENTS.md` — loop engineering added to "Mandatory rules" + a decomposition bullet in "Handoff protocol".
- **MODIFY** `docs/handoff/_TEMPLATE.md` — the freeform "Steps" section replaced with a mandatory **Task Decomposition** table.
- **NEW** `implementation_plan_loop_engineering.md` — this plan document (kept separate from the existing
  `implementation_plan.md` so the LIB-RCA-007 live-evidence history stays untouched).

## Types / Functions / Classes / Dependencies
None. No application code, no new packages.

## Testing
- No unit tests required (documentation-only change).
- Validation: greps confirming the new references resolve and the template renders the new table.

## Implementation Order
1. Write `.agents/rules/loop_engineering.md`.
2. Edit `AGENTS.md` (2 bullets).
3. Edit `docs/handoff/_TEMPLATE.md` (Steps → decomposition table).
4. Save this plan to `implementation_plan_loop_engineering.md`.
5. Validate with greps.

## Open Questions / Side Observations
- `LIB-RCA-007` (preflight false-positive) is already implemented in code
  (`app/brokers/liberator/session_health.py`, 3-way split in `scripts/preflight_check.py`,
  `tests/test_preflight_check.py`). The existing `implementation_plan.md` "IN PROGRESS — Gate 1 done"
  header is stale vs. the code; only the RCA-doc reconciliation (mark `LIB-RCA-007` 🟢 RESOLVED)
  appears outstanding. Out of scope here — flagged for the next handoff.

---

## Cline Report
- Files changed:
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/rules/loop_engineering.md` (new)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/AGENTS.md` (modified)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/_TEMPLATE.md` (modified)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/implementation_plan_loop_engineering.md` (new)
- Summary: Added the canonical loop-engineering rule and wired it into the shared agent rules +
  handoff workflow; handoff template now forces a Task Decomposition table before any work.
- Tests run + result: No code/tests changed (docs-only). Validation greps all PASS:
  `grep -n "loop_engineering" AGENTS.md` → 1 hit (L15);
  `grep -rniE "loop engineering|Task Decomposition" .agents/rules docs/handoff AGENTS.md` → hits in
  `loop_engineering.md`, `docs/handoff/_TEMPLATE.md` (L13), `AGENTS.md` (L24). Both new files confirmed on disk.
- Open questions: LIB-RCA-007 staleness (above).
