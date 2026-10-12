# Rule: Loop Engineering (core)

Full version with rationale/examples: `docs/agent/full/loop_engineering_full.md` · skill `loop-engineer`.

1. **DECOMPOSE** — split into atomic units (1 function / file / call-site / assertion / browser action), ordered by dependency.
   Write them under `## Steps / Task Decomposition` in the handoff file before starting; each unit has Expected Outcome + Verify command.
2. **EXECUTE** — exactly 1 unit per loop. No batching unrelated edits. No scope creep / unplanned refactor.
3. **VERIFY** — `scripts/verify_changes.py <files>` (targeted tests + compileall). FAIL → do not move on, go to REFLECT.
   - `--full` only once at task close. If `--full` hangs ~87% > 5 min (known SQLite lock) → kill + log in Open questions.
   - Docs-only changes = report-only (check against code). Browser/hardware = real evidence + human confirm.
   - Health checks/preflight must call the same checker the driver uses (single source of truth, LIB-RCA-007).
4. **REFLECT** — 3-point RCA (session/context · live DOM · data schema). Fixed failure → RCA entry for that broker;
   changed selectors/steps → update the runbook in `learned_workflows/` immediately (no contradictions).
5. **REPEAT** — next unit. All units done → report Files changed / Summary / Tests run / Open questions.

**Budget → STOP & REVIEW with the user:** 15 min or ~20 tool calls per unit · 3 self-anneal attempts per failure (then escalate) ·
end of every major step. Near budget → split the unit further, don't push through.
