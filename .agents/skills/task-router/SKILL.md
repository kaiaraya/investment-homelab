---
name: task-router
description: Use when a plan/loop must be split into work items and you must decide WHERE each
  item runs — a Kanban card (headless, risk-tier T0/T1) or this interactive Antigravity room
  (risk-tier T2: order / OTP / account switch / SBL / live login / live browser / merge main).
  Encodes the routing rule, the exact `kanban task create` template, and the HITL protocol for
  the items that stay interactive. Invoke as /task-router.
---

# /task-router — route each work item to Headless (Kanban) or HITL (interactive room)

Sources of truth (read them, do not restate here): `docs/agent/workflow_playbook.md` §1/§4 ·
`docs/agent/github_handoff.md` §5–§7 · `.agents/rules/loop_engineering.md` ·
`.agents/skills/stepwise-approval/SKILL.md`.

## §1 Classify — headless or interactive?

| Tier | Nature | Where it runs |
|---|---|---|
| 🟢 **T0** | code / docs / unit test / headless scrape — touches no order, OTP or account | **Kanban card** (automatic) |
| 🟡 **T1** | logic that does not touch order / OTP / tick size — needs diff audit + report | **Kanban card** (`--auto-review-mode commit`) |
| 🔴 **T2** | **order · OTP · account switch · SBL · live login · live browser · merge `main`** | **Interactive room only** — never a card |

Fast screen (answer "yes" to any item ⇒ T2 ⇒ do **not** create a card):

1. Will a real order be placed / modified / cancelled on a broker?
2. Will an SMS OTP be fired, or a full login / 2FA triggered?
3. Will an account be switched, or SBL touched?
4. Will a headed browser be driven, or a real screen read for live witness?
5. Will a PR be merged into `main` (gate #2)?

> **merge `main` is always T2** → it stays in the interactive room (human gate).

## §2 Split — one plan → several work items

Split by **run mode**, not by file count:

1. **Code + unit test** portion → HEADLESS → one Kanban card per task
   (1 card = 1 TASK = 1 handoff doc; never two handoffs in one card).
2. **Remaining live/HITL** portion of the same task → INTERACTIVE → keep it in this room, no card.
3. Record the mode in every handoff doc with a `- Run mode:` line (see §5):
   - `HEADLESS — Kanban card <id>`
   - `HYBRID — โค้ด+unit = HEADLESS (Kanban card <id>) · live <X> = INTERACTIVE (ห้องนี้)`
   - `INTERACTIVE 100% HITL — ไม่มี Kanban card`

Worked example — Loop 1 (rollback + re-plan 2026-10-15):

| Card | Content | Mode |
|---|---|---|
| loop1-1 | Pillar 2 orders / margin lock | INTERACTIVE (การ์ด start ไม่ได้ → §3 fallback) |
| loop1-2 | unify `/nego kss` → QuickTrade in-place | INTERACTIVE (ห้องนี้ · ไม่มี session ของการ์ด `2b7ff`) + live amend (room) |
| loop1-3 | Liberator quote hardening | INTERACTIVE (ห้องนี้ · การ์ด `045ac` ถูกลบ → §3 fallback) + live quote = live witness ใน loop1-4 |
| loop1-4 | Live Round B witness | INTERACTIVE 100% (no card) |

## §3 Headless → create the Kanban card

```bash
cd <repo-root>
kanban task create --base-ref main \
  --title "TASK-<slug> [HEADLESS]" \
  --prompt "$(printf '%s\n' \
    'งาน: <one-line goal>' '' \
    'อ่านแผนเต็ม: docs/handoff/TASK-<slug>.md' '' \
    'Scope: <file1>, <file2>, <file3>' \
    'สาระสำคัญ: <what to change, given ↔ then>' \
    'Verify: .venv/bin/python scripts/verify_changes.py <file1> <file2> <file3>' \
    'ห้าม: place/modify/cancel order · SMS OTP · restart gateway · รัน live/HITL')"
```

Rules:

- `--prompt` **must** carry a `Verify:` command and a `ห้าม:` list — that is what stops the
  headless agent from drifting into live/HITL work.
- `--base-ref main` (or the agreed branch). Defaults: `--start-in-plan-mode false`,
  `--auto-review-mode commit` — fine for T0/T1.
- **Dependencies:** `kanban task link --task-id <dependent> --linked-task-id <prereq>`.
  ⚠️ Not used in Loop 1: linking two cards that edit the **same file** (e.g. `handlers.py`) was
  observed producing cards that never start. After the root cause found on 2026-10-15 (see
  "Starting a card" below) the suspicion moved to *how the card was started*, but the
  workaround stands: **create without `--link` and run them serially**.
- Verify: `kanban task list --column backlog` shows every expected id.
- **Never** create a card for T2 work.

### Starting a card — the streaming client must stay alive

⚠️ **Observed 2026-10-15 (twice, both when the card was started from an agent tool terminal):**
the session flips to `state: interrupted` / `reviewReason: interrupted` after ~38 s and ~49 s
**mid-turn** (the assistant had just emitted `thinking` + 3 × `tool_use`), the card is moved to
**`trash`**, and the transcript says `"status": "cancelled"`, `"exit_code": 0`,
`"interactive": true`, `totalCost: 0`.

**ROOT CAUSE FOUND (2026-10-15 evening) — upstream packaging bug, not this repo:**

`kanban@0.1.70` (and every published version 0.1.40→0.1.70) ships a `dist/` holding only `cli.js`,
`index.js`, `web-ui/`. `dist/cli.js` spawns the hub daemon as `node <pkg>/dist/entry.js` →
the spawn dies with `MODULE_NOT_FOUND` (that is the ~8-entry crash loop in
`~/.cline/data/logs/hub-daemon.log`), the hub command then times out after ~30 s and the card
session ends `cancelled` / `interrupted` mid-turn. Second stacked bug: even with `dist/entry.js`
present, `@clinebot/core`'s daemon entry references a bare global `AI` (Vercel AI SDK) at
module-evaluation time → `ReferenceError: AI is not defined`.
Upstream: **`cline/kanban#495`** and **`cline/kanban#590`** (both open; the fix commits
`2f8764b` / `7ab7909` on `main` are **not** in any npm release yet).

**Machine-local fix (applied 2026-10-15, verified end-to-end):** a 1.4 KB shim at
`<npm-global>/kanban/dist/entry.js` that sets `globalThis.AI` from the installed `ai` package
**before** `await import("@clinebot/core/hub/daemon-entry")` — the order matters, a static
`export * from` is hoisted and the global would not exist yet.
Code + full evidence: `rca/shared/rca_kanban_hub_daemon.md`.
⚠️ Re-apply after every `npm i -g kanban` / npm upgrade, until a release > 0.1.70 ships the file.

Evidence (verified **twice**, 2026-10-15): `node dist/entry.js --cwd /tmp --port 45999` binds the
port with no error · `hub-daemon.log` stopped growing (8 → 8 `MODULE_NOT_FOUND`, mtime frozen at
13:48) · two smoke cards (`f76e7` → `DONE 9ed1f5a`, `11c9e` → `PWD …/worktrees/11c9e/InvestmentHomelab`
+ `DONE 842c6c5`) went `in_progress`, their sessions ended `status: completed` (not `cancelled`),
and `kanban task delete` removed the worktrees.

Still true (independent of the bug):

- Start the card in a terminal that a **human keeps open** — `kanban task start --task-id <id>`
  streams into it — or press **Start** in the Kanban UI (`http://127.0.0.1:3484`).
- `kanban task start` v0.1.70 has **no** `--detach/--background/--watch` flag, so the client must
  remain attached for the whole run.

Diagnostics when a card dies:

```bash
cd <repo-root>
ls -d $HOME/.cline/data/sessions/<id>-*/                       # per-session transcript
grep -o '"status": *"[a-z]*"' $HOME/.cline/data/sessions/<id>-*/<id>-*.json   # cancelled? failed?
python3 -c "import json;print(json.load(open('$HOME/.cline/kanban/workspaces/<ws>/sessions.json'))['<id>'])"
journalctl --user -u cline-kanban.service --since '-10 min' --no-pager | tail -20
```

Recovery — a trashed card refuses to start (`"is in trash and can only be started from backlog or
in_progress"`): `kanban task delete --task-id <old>` → `kanban task create …` (same prompt, **new
id**) → then update every `<old-id>` reference in the handoff docs and this skill (§5).
Keep the prompt's **absolute** plan path plus the "ถ้าอ่านไฟล์นี้ไม่ได้ ให้หยุดและรายงาน" rule —
untracked handoff docs are absent from the card worktree (it is cut from `--base-ref`).
Run **one card at a time** while the cards share a file (`handlers.py`).

### Fallback when a card will not start

Observed on 2026-10-15 for loop1-1 (card `5596a`): the card could not be started at all →
**re-route that item to the interactive room** and run it with `.agents/skills/stepwise-approval`
(valid whenever the item is really code+unit only). Then clean up so nothing contradicts:

1. `kanban task delete --task-id <id>`
2. handoff `- Run mode:` line → `INTERACTIVE (ห้องนี้ · stepwise-approval) …`
3. the id table in §2 above (§5 zero-contradiction).

## §4 Interactive → protocol inside this room

Run the full `.agents/skills/stepwise-approval` protocol:

1. **Stage A (Code Audit)** — diff matches scope; invariants checked (Anti-Mock, Zero-OTP, uptick).
2. **Stage B (Verify)** — `.venv/bin/python scripts/verify_changes.py <changed files>` = PASS.
3. **Stage C (Visual / HITL)** — human confirmation before *every* step that touches a broker:
   - state the Expected Outcome **before** acting (one line);
   - do exactly one step → capture evidence (`DISPLAY=:0` screenshot) → turn it into text
     (DOM text / `browser_evaluate` / short OCR) → `ask_question` for the human verdict;
   - 🚨 on anomaly: **stop** → 3-point RCA (session · live DOM · data schema) → self-anneal
     ≤ 3 attempts → escalate `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`.
4. **Stage D (Verdict + Merge)** — PASS → open the result PR → **the user merges `main`**
   (gate #2) → clean the worktree.

Pre-conditions before step 1 (all must hold): dependency cards merged + verify PASS ·
gateway live (`curl http://127.0.0.1:8000/health`) · market open · correct account.
⛔ The agent must **never** start or restart the gateway (Invariant 7/9 · LINE-RCA-011) — Admin
starts it from the main checkout.

## §5 Loop + zero-contradiction

- Work per atomic unit: `.agents/rules/loop_engineering.md` (DECOMPOSE → EXECUTE → VERIFY →
  REFLECT → REPEAT).
- Every handoff doc must carry `- Run mode: ...` (§2) and Steps `Status` reset to ⬜ before start.
- **Rollback / re-plan:** archive first (git tag + copy handoff docs / `board.json`), then
  **wipe** the previous round's `## Cline Report`, Steps `Status` ✅ marks and
  `## Cline Verification` — never leave ✅ that refers to code that was reverted
  (zero-contradiction).
- Cross-refs: `docs/agent/workflow_playbook.md` · `docs/agent/github_handoff.md` ·
  `docs/agent/handoff_protocol.md` · `.agents/skills/loop-engineer/SKILL.md` ·
  `.agents/skills/stepwise-approval/SKILL.md`.
