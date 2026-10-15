# TASK-loop1-4: Live Round B — Witness Verification (Falsification) ของ Loop 1

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: KSS (MARGIN 3024959) + LIB (CASH) — ของจริง ตลาดเปิด
- Status: BLOCKED (2026-10-15 15:42, Cline) — gate ไม่ครบ 2 ข้อ, หยุดก่อนขั้น 1 (ดู Cline Report)
- Depends on: TASK-loop1-1, TASK-loop1-2, TASK-loop1-3
- Unblocks: — (ปิด Loop 1 → ป้อนผลเข้า Argon Analysis)
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D5
- Verify: **human witness** (runbook — ไม่มี automated verify; บังคับมีคนดูหน้าจอจริง)

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §3 (Acceptance / Round B) — การ์ด 1–3 แก้ที่โค้ดแล้ว การ์ดนี้คือ "พยานยืนยัน" ด้วยตลาดจริงตามหลัก falsification

## Context
การ์ด 1–3 พิสูจน์แค่ระดับ unit/mock ยังไม่ยืนยันว่าของจริงทำงาน การ์ดนี้ต้องรันกับตลาดจริง โดยมี Admin เฝ้าหน้าจอ (witness) ทุกขั้น ห้ามเชื่อ log อย่างเดียว

## Gate เงื่อนไขก่อนเริ่ม (ต้องครบทุกข้อ) — **ผลเช็ค 2026-10-15 15:42 (Cline): 2 FAIL → หยุด**
- [ ] การ์ด 1–3 merge + `verify_changes.py` PASS แล้ว → **FAIL**: Card 1 ✅ `1fe7cf8` · Card 2 ✅ `6c6819b` (`MAX_TICKS_EXCEEDED` G5 present) · **Card 3 ❌ ยังไม่ implement** (0 hits `QUOTE_UNAVAILABLE`, handoff DRAFT, steps ⬜)
- [ ] Gateway รันอยู่ที่ `app.main:app` → **FAIL**: ไม่มี process uvicorn, ไม่มีพอร์ต 8000, `curl /health` (localhost + Tailscale `100.88.217.33:8000`) = connection refused
- [ ] ตลาดเปิด (KSS/LIB) มี volume จริง → ⚠️ เปิดอยู่แต่เหลือ ~45 นาที (SET บ่ายปิด ~16:30)
- [ ] Account: KSS = MARGIN 3024959 · LIB = CASH → UNVERIFIABLE (ต้อง gateway รันก่อน)

## Steps / Task Decomposition (Runbook — 1 ขั้น/รอบ, มีพยาน)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 1 | `/orders` (KSS) | คืนออเดอร์จริง หรือ `unavailable_card` ถ้า auth fail — **ห้าม 🟢 live ปลอม** | 👁 | ⬜ |
| 2 | `/orders` (LIB) | เติม LIB + แจ้งข้อจำกัด LIB ตรงไปตรงมา | 👁 | ⬜ |
| 3 | `/nego kss <sym> ราคาดีกว่า 1 tick` | กด Change Price **in-place** — ยืนยันว่าไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่า | 👁 | ⬜ |
| 4 | `/nego kss <sym> ราคาห่าง > 3 tick` | ปฏิเสธด้วย `MAX_TICKS_EXCEEDED` — **ไม่กดจริง** | 👁 | ⬜ |
| 5 | `/nego lib <sym>` | ราคา bid/offer ตรงหน้าจอจริง — ไม่มีราคาที่ถูกเดา | 👁 | ⬜ |
| 6 | `/nego lib <sym ผิด>` | fail-closed — ไม่กดเปลี่ยนราคา | 👁 | ⬜ |

> ⛔ **2026-10-15 15:42 — ขั้น 1–6 = NOT RUN / SKIPPED ที่ Gate** (ไม่ใช่ "ผ่าน"): การ์ดหยุดก่อนแตะ broker เพราะ gate ไม่ครบ 2 ข้อ ห้ามตีความ `⬜` เป็นผลบวก · ต้องผ่าน Gate ใหม่ทั้ง 4 ข้อก่อนเริ่มขั้น 1

## Acceptance / Tests ที่ต้องผ่าน
- ทุกข้อ #1–#6 ตรง Expected Outcome **และ** พยาน (Admin) ยืนยันด้วยตาทุกข้อ
- ถ้าข้อใดไม่ผ่าน → **หยุดทันที** → ทำ 3-point RCA (session/context · live DOM · data schema) → แจ้ง Admin: `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`
- ห้าม self-anneal เกิน 3 ครั้งต่อข้อ

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** (ทดสอบเฉพาะ in-place change) · ห้ามยิง SMS OTP · ห้าม restart gateway ระหว่างทดลอง
- **ห้ามแก้โค้ดในการ์ดนี้** — ถ้าพบ bug ให้แยกเปิดการ์ดแก้ใหม่ (ตามหลัก 1 การ์ด = 1 งาน)

---

## Cline Report
- Files changed: (none — runbook only; gate check documented here)
- Summary:
  - Gate check run FIRST (per runbook "Gate เงื่อนไขก่อนเริ่ม") → **2 of 4 gate items FAIL → no runbook step executed**, no broker page touched, gateway not started/restarted, no OTP, no orders.
  - Gate result table:
    | Gate item | Result | Evidence |
    |---|---|---|
    | การ์ด 1–3 merge + verify PASS | **FAIL** | Card 1 ✅ merged `1fe7cf8` · Card 2 ✅ merged `6c6819b` · **Card 3 ❌ ยังไม่ implement** — `grep -rn QUOTE_UNAVAILABLE app/brokers/liberator/ app/services/line_cli/ tests/` = 0 hits; `TASK-loop1-3` ยัง `Status: DRAFT`, steps 1–4 ทั้งหมด ⬜ |
    | Gateway รันที่ `app.main:app` | **FAIL** | `ps aux \| grep uvicorn` = ว่าง · `ss -ltn \| grep :8000` = ว่าง · `curl http://127.0.0.1:8000/health` และ `http://100.88.217.33:8000/health` = connection refused (curl exit 7) · `logs/uvicorn.log` = 0 byte (Oct 14 22:28) |
    | ตลาดเปิด | ⚠️ PASS (หมดเวลา) | เซสชันบ่าย SET ถึง ~16:30 · เช็คเวลา 15:42 (+07) → เหลือ ~45 นาที (ไม่พอทำ Card 3 + Card 4) |
    | Account KSS MARGIN 3024959 / LIB CASH | UNVERIFIABLE | ต้อง gateway/auth รันก่อน — ตรวจไม่ได้ตอนนี้ |
  - Card 2 code confirmed present in main: `MAX_TICKS_EXCEEDED` (G5) in `app/services/quicktrade_negotiation_service.py:43` + `handlers.py:229`. Card 1 code confirmed: `unavailable_card` auth-fail path in `app/services/line_cli/handlers.py:600/634/655/685`.
  - Verify mapping preview (dry-run only, no pytest — kanban service holds SQLite): `verify_changes.py app/services/quicktrade_negotiation_service.py app/services/line_cli/handlers.py --dry-run` → `tests/test_quicktrade_negotiation_policy.py` + `tests/test_line_cli_flow.py` + compileall.
  - HITL escalation (rule §4): reported to Admin in session — `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: gateway ไม่รัน + Card 3 (Liberator fail-closed) ยังไม่ implement` (LINE push ไม่ได้ — gateway down).
- Tests run + result (ผล witness):
  - #1–#6: **NOT RUN** — หยุดที่ Gate ตาม Acceptance ("ถ้าข้อใดไม่ผ่าน → หยุดทันที") · ไม่มี witness step ใดถูกแตะ
  - Tests run: `verify_changes.py --dry-run` (mapping preview only, exit 0) · ไม่มี pytest (กัน SQLite lock กับ `cline-kanban.service` ที่ active อยู่)
- Open questions:
  1. **Gateway start authority** — การ์ดนี้ห้าม restart แต่ gateway ไม่ได้รันเลย; ต้องให้ Admin start เองจาก main checkout (`scripts/start_homelab.py`) — Cline ไม่ได้ start เพราะเสี่ยง trigger login/2FA (Invariant 7/9) และ worktree นี้ไม่ใช่ runtime dir
  2. **Card 3 ยังไม่ implement** — `QUOTE_UNAVAILABLE` fail-closed + symbol-mismatch guard ใน `app/brokers/liberator/{driver,plugin}.py` + `handlers._broker_modify(lib)` ยังไม่มีใน main → ต้องปิด Card 3 (merge + verify PASS) ก่อน Card 4 จึงจะเริ่มได้
  3. **Window วันนี้ไม่พอ** — เหลือ ~45 นาทีก่อน SET ปิด 16:30; ถ้าจะทำ witness ครบ 6 ข้อควรเลื่อนไปรอบตลาดถัดไป (16 ต.ค. 10:00) หลัง Card 3 ปิด
  4. **Runtime จาก worktree** — gateway/probe ควรใช้ main checkout ไม่ใช่ kanban worktree `6e526` (session_state / logs คนละชุด) ต้องยืนยันกับ Admin ก่อนรันจริง


---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
  - **Blocked before Stage A** (2026-10-15, Cline): pre-condition Gate ไม่ผ่าน (gateway down + Card 3 ไม่ implement) → ไม่มีหลักฐานให้ audit/verify · ไม่ใช่ PASS และไม่ใช่ CHANGES_REQUESTED ของโค้ดการ์ดนี้
- Verdict: **BLOCKED — GATE_NOT_MET** (ยังไม่ตัดสิน PASS / CHANGES_REQUESTED)

---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
