---
name: loop-engineer
description: Use ONLY when the user explicitly invokes /loop-engineer. Runs the task through the
  DECOMPOSE→EXECUTE→VERIFY→REFLECT→REPEAT loop defined in .agents/rules/loop_engineering.md,
  one atomic unit per turn.
---

# /loop-engineer

1. **Read** `.agents/rules/loop_engineering.md` — single source of truth; do not restate it here.
2. **DECOMPOSE**: write the Task Decomposition table
   (`# | Atomic Step | Expected Outcome | Verify | Status`) into the handoff file
   (`docs/handoff/TASK-xxx.md`) if one exists, otherwise into a task artifact.
   Ask the user to approve the table before executing anything.
3. **Per turn** (exactly one unit):
   EXECUTE → VERIFY with a real command / evidence
   (`scripts/verify_changes.py <changed files>` → exit 0 = PASS; `--full` only once at close-of-work)
   → REFLECT (RCA / runbook update if it failed
   or selectors changed) → update Status (⬜ → ✅/❌) → **STOP** and report:
   > Done #n: <actual result + evidence>. Next: #n+1 <expected outcome>. Continue?
4. **FAIL**, or >3 anneal attempts without progress → stop and escalate
   (`.agents/rules/root_cause_and_escalation.md`). Never report ✅ without real evidence (Anti-Mock).
5. Context getting long → suggest `/compact`.
6. Hardware / headed-browser steps → also apply `/stepwise-approval` (human confirm required).
