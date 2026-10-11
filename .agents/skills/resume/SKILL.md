---
name: resume
description: Use ONLY when the user explicitly invokes /resume. Loads the newest (or a named)
  docs/handoff/CONTEXT-*.md snapshot created by /compact and continues from its "Next step".
---

# /resume — Continue from Snapshot

1. **Pick the file**: the argument if given, else
   `ls -t docs/handoff/CONTEXT-*.md | head -1`. None found → tell the user to run `/compact` first.
2. **Load context**: read the snapshot + any handoff file it links. Re-read the mandatory rules
   listed in `AGENTS.md` (loop engineering, PDCA/RCA, escalation, trading safety).
3. **Re-verify reality before acting** (state may have changed since the snapshot):
   - check every file in "Files changed" exists;
   - re-run the "last verify" command (read-only / tests only — never order tools);
   - check listed background commands / logs.
   Report any drift between the snapshot and reality.
4. **Restate and wait**: Goal, current step, Next step + Expected Outcome + Verify.
   Ask the user to confirm, then execute exactly that ONE unit
   (`.agents/rules/loop_engineering.md`), and update the Task Decomposition status.
