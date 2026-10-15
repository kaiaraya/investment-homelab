# TASK-loop1-4: Live Round B — Witness Verification (Falsification) ของ Loop 1

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: KSS (MARGIN 3024959) + LIB (CASH) — ของจริง ตลาดเปิด
- Status: DRAFT
- Depends on: TASK-loop1-1, TASK-loop1-2, TASK-loop1-3
- Unblocks: — (ปิด Loop 1 → ป้อนผลเข้า Argon Analysis)
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D5
- Verify: **human witness** (runbook — ไม่มี automated verify; บังคับมีคนดูหน้าจอจริง)

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §3 (Acceptance / Round B) — การ์ด 1–3 แก้ที่โค้ดแล้ว การ์ดนี้คือ "พยานยืนยัน" ด้วยตลาดจริงตามหลัก falsification

## Context
การ์ด 1–3 พิสูจน์แค่ระดับ unit/mock ยังไม่ยืนยันว่าของจริงทำงาน การ์ดนี้ต้องรันกับตลาดจริง โดยมี Admin เฝ้าหน้าจอ (witness) ทุกขั้น ห้ามเชื่อ log อย่างเดียว

## Gate เงื่อนไขก่อนเริ่ม (ต้องครบทุกข้อ)
- [ ] การ์ด 1–3 merge + `verify_changes.py` PASS แล้ว
- [ ] Gateway รันอยู่ที่ `app.main:app` (ห้าม restart ระหว่างทดลอง — LINE-RCA-011)
- [ ] ตลาดเปิด (KSS/LIB) มี volume จริง
- [ ] Account: KSS = MARGIN 3024959 · LIB = CASH

## Steps / Task Decomposition (Runbook — 1 ขั้น/รอบ, มีพยาน)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 1 | `/orders` (KSS) | คืนออเดอร์จริง หรือ `unavailable_card` ถ้า auth fail — **ห้าม 🟢 live ปลอม** | 👁 | ⬜ |
| 2 | `/orders` (LIB) | เติม LIB + แจ้งข้อจำกัด LIB ตรงไปตรงมา | 👁 | ⬜ |
| 3 | `/nego kss <sym> ราคาดีกว่า 1 tick` | กด Change Price **in-place** — ยืนยันว่าไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่า | 👁 | ⬜ |
| 4 | `/nego kss <sym> ราคาห่าง > 3 tick` | ปฏิเสธด้วย `MAX_TICKS_EXCEEDED` — **ไม่กดจริง** | 👁 | ⬜ |
| 5 | `/nego lib <sym>` | ราคา bid/offer ตรงหน้าจอจริง — ไม่มีราคาที่ถูกเดา | 👁 | ⬜ |
| 6 | `/nego lib <sym ผิด>` | fail-closed — ไม่กดเปลี่ยนราคา | 👁 | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- ทุกข้อ #1–#6 ตรง Expected Outcome **และ** พยาน (Admin) ยืนยันด้วยตาทุกข้อ
- ถ้าข้อใดไม่ผ่าน → **หยุดทันที** → ทำ 3-point RCA (session/context · live DOM · data schema) → แจ้ง Admin: `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`
- ห้าม self-anneal เกิน 3 ครั้งต่อข้อ

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** (ทดสอบเฉพาะ in-place change) · ห้ามยิง SMS OTP · ห้าม restart gateway ระหว่างทดลอง
- **ห้ามแก้โค้ดในการ์ดนี้** — ถ้าพบ bug ให้แยกเปิดการ์ดแก้ใหม่ (ตามหลัก 1 การ์ด = 1 งาน)

---

## Cline Report
- Files changed: (none — runbook)
- Summary:
- Tests run + result (ผล witness):
  - #1 ... #6 ...
- Open questions:

---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED

---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
