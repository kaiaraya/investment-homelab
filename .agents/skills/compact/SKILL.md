---
name: compact
description: Use when the user invokes /compact [focus], or when context exceeds ~60K tokens (AGENTS.md
  token budget). Writes a short focused snapshot to docs/handoff/CONTEXT-<YYYY-MM-DD-HHMM>.md so work
  continues in a fresh conversation/card via /resume.
---

# /compact [focus] — Context Snapshot

> Antigravity ลบ context ของตัวเองไม่ได้ (ต่างจาก Cline `/compact`) → ใช้ snapshot ไฟล์ + แชทใหม่ + `/resume` แทน

## 0. Focus + size (token budget)
- Optional focus arg, e.g. `/compact focus on current bug` → keep only what serves that focus.
- **English bullets, ≤ 40 lines total.** No narrative, no tool output dumps, no code except 1–3 line snippets.
- Must cover: goal · files changed · commands run + result · what is **still failing** · next step.

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
- Commands run: `<...>` → <actual result summary>

## Still failing / errors
- <error + where> (or "none")

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
