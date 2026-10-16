---
name: task-router
description: Use when a plan/loop must be split into work items and you must decide WHERE each
  item runs — the Cline plugin (headless, risk-tier T0/T1) or this Antigravity IDE room
  (risk-tier T2: order / OTP / account switch / SBL / live login / live browser / merge main).
  Encodes the routing rule, the exact session prompt template, and the HITL protocol for
  the items that stay interactive. Invoke as /task-router.
---

# /task-router — route each work item to Cline plugin (headless) or Antigravity IDE (HITL)

Sources of truth (read them, do not restate here): `docs/agent/workflow_playbook.md` §1/§4 ·
`docs/agent/local_handoff.md` §3/§5 · `.agents/rules/loop_engineering.md` ·
`.agents/skills/stepwise-approval/SKILL.md`.

## §1 Classify — headless (Cline) or interactive (Flash)?

| Tier | Nature | Where it runs |
|---|---|---|
| 🟢 **T0** | code / docs / unit test / headless scrape — touches no order, OTP or account | **Cline plugin** session (automatic) |
| 🟡 **T1** | logic that does not touch order / OTP / tick size — needs diff audit + report | **Cline plugin** session (Plan=DeepSeek Pro · Act=DeepSeek Flash) |
| 🔴 **T2** | **order · OTP · account switch · SBL · live login · live browser · merge `main`** | **Antigravity IDE (Flash 3.8)** — never the Cline plugin |

Fast screen (answer "yes" to any item ⇒ T2 ⇒ do **not** open a Cline session):

1. Will a real order be placed / modified / cancelled on a broker?
2. Will an SMS OTP be fired, or a full login / 2FA triggered?
3. Will an account be switched, or SBL touched?
4. Will a headed browser be driven, or a real screen read for live witness?
5. Will the branch be merged into `main` (gate #2)?

> **merge `main` is always T2** → it stays in the interactive room (human gate).

## §2 Split — one plan → several work items

Split by **run mode**, not by file count:

1. **Code + unit test** portion → HEADLESS → one Cline plugin session per task
   (1 session = 1 TASK = 1 handoff doc; never two handoffs in one session).
2. **Remaining live/HITL** portion of the same task → INTERACTIVE → keep it in this room (Flash 3.8).
3. Record the mode in every handoff doc with a `- Run mode:` line:
   - `HEADLESS-CLINE (Cline plugin · T0/T1)`
   - `HITL-FLASH (Antigravity IDE · Flash 3.8 · human witness)`
   - `HYBRID (โค้ด+unit = Cline plugin · live <X> = Antigravity IDE)`

## §3 Headless → open the Cline plugin session

ไม่มี CLI/daemon — มนุษย์เปิด Cline plugin session แล้ววาง prompt นี้:

```
Task: docs/handoff/TASK-<slug>.md — start from its "Context map"; work only its scope.
Run mode: HEADLESS-CLINE.
Scope: <file1>, <file2>, <file3>
สาระสำคัญ: <what to change, given ↔ then>
Verify: .venv/bin/python scripts/verify_changes.py <file1> <file2> <file3>
ห้าม: place/modify/cancel order · SMS OTP · restart gateway · รัน live/HITL
Finish with the "Cline Report" section.
```

Rules:

- The prompt **must** carry a `Verify:` command and a `ห้าม:` list — that is what stops the
  headless agent from drifting into live/HITL work.
- Model: **Plan = `DeepSeek Pro` · Act = `DeepSeek Flash`** (ดู `docs/agent/token_workflow.md`)
- **Dependencies:** run dependent items **serially** — two Cline sessions editing the same file
  (e.g. `handlers.py`) must not run at the same time.
- **Never** open a Cline session for T2 work.
- Board bookkeeping: มนุษย์ (หรือ Argon) เพิ่ม/อัปเดตการ์ดใน `docs/board/loop_board.md`
  — Cline flip แค่ `Status` ใน handoff ของตัวเอง

### Fallback when a Cline session cannot run
ถ้า Cline plugin ใช้ไม่ได้ **re-route งานนั้นมาที่ห้อง Antigravity IDE นี้** แล้วรันด้วย
`.agents/skills/stepwise-approval` (valid เมื่องานเป็น code+unit จริง) แล้วเก็บกวาดไม่ให้ขัดกัน:

1. handoff `- Run mode:` line → `HITL-FLASH (ห้องนี้ · stepwise-approval) …`
2. แถวการ์ดใน `docs/board/loop_board.md` (§5 zero-contradiction)

## §4 Interactive → protocol inside this room

Run the full `.agents/skills/stepwise-approval` protocol:

1. **Stage A (Code Audit)** — diff matches scope; invariants checked (Anti-Mock, Zero-OTP, uptick).
2. **Stage B (Verify)** — `.venv/bin/python scripts/verify_changes.py <changed files>` = PASS.
3. **Stage C (Visual / HITL)** — human confirmation before *every* step that touches a broker:
   - state the Expected Outcome **before** acting (one line);
   - do exactly one step → capture evidence (`DISPLAY=:0` screenshot → `data/screenshots/`) → turn it into text
     (DOM text / `browser_evaluate` / short OCR) → `ask_question` for the human verdict;
   - 🚨 on anomaly: **stop** → 3-point RCA (session · live DOM · data schema) → self-anneal
     ≤ 3 attempts → escalate `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`.
4. **Stage D (Verdict + Merge)** — PASS → **ผู้ใช้ squash-merge `task/<slug>` เข้า `main`**
   (gate #2) → ลบ branch.

Pre-conditions before step 1 (all must hold): dependency cards merged + verify PASS ·
gateway live (`curl http://127.0.0.1:8000/health`) · market open · correct account.
⛔ The agent must **never** start or restart the gateway (Invariant 7/9 · LINE-RCA-011) — Admin
starts it from the main checkout.

## §5 Loop + zero-contradiction

- Work per atomic unit: `.agents/rules/loop_engineering.md` (DECOMPOSE → EXECUTE → VERIFY →
  REFLECT → REPEAT).
- Every handoff doc must carry `- Run mode: ...` (§2) and Steps `Status` reset to ⬜ before start.
- **Rollback / re-plan:** archive first (git tag + copy handoff docs + `docs/board/loop_board.md`),
  then **wipe** the previous round's `## Cline Report`, Steps `Status` ✅ marks and
  `## Verification & Stepwise Approval` — never leave ✅ that refers to code that was reverted
  (zero-contradiction).
- Cross-refs: `docs/agent/workflow_playbook.md` · `docs/agent/local_handoff.md` ·
  `docs/agent/handoff_protocol.md` · `.agents/skills/loop-engineer/SKILL.md` ·
  `.agents/skills/stepwise-approval/SKILL.md`.
