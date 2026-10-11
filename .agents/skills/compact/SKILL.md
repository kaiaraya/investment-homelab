---
name: compact
description: Use ONLY when the user explicitly invokes /compact. Writes a context snapshot of the
  current conversation to docs/handoff/CONTEXT-<YYYY-MM-DD-HHMM>.md so work can continue in a fresh
  conversation via /resume (Antigravity cannot truncate its own context window).
---

# /compact — Context Snapshot

> Antigravity ลบ context ของตัวเองไม่ได้ (ต่างจาก Cline `/compact`) → ใช้ snapshot ไฟล์ + แชทใหม่ + `/resume` แทน

## 1. Build the snapshot (real conversation state only — Anti-Mock)
Use exactly these sections:

```markdown
# CONTEXT <YYYY-MM-DD HH:MM> — <short task title>

## Goal / Task
- <goal>; handoff file: <docs/handoff/TASK-xxx.md or N/A>; broker: <...|N/A>

## Decisions made
- <decision> — <why>

## Files changed (full paths — repo has no git)
- /home/.../file.py (new|modified) — <one line>

## Task Decomposition (current status)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|-------------|------------------|--------|--------|

## Current step + last verify
- Step #n: <...>
- Command: `<...>` → <actual result summary>

## Next step (exactly ONE atomic unit)
- Step #n+1: <action>
- Expected Outcome: <...>
- Verify: `<command / evidence>`

## Open questions / blockers / RCA ids
- <...>
```

## 2. Safety (mandatory)
- NEVER include `.env` values, passwords, PINs, OTPs, tokens, cookies, or account numbers.
- Only verified facts — never write an order id, balance, or "✅" that was not actually observed.
- Running background commands: list them (command + log path) so `/resume` can check them.

## 3. Write + verify
1. Write to `docs/handoff/CONTEXT-<YYYY-MM-DD-HHMM>.md` (local time).
2. Verify: `ls -la` the file and `grep -n '^## ' <file>` to show all sections exist.
3. Tell the user: **"Open a new conversation and run `/resume` (or `/resume <file>`)."**
