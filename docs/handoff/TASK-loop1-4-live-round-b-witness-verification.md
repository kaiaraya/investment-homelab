# TASK-loop1-4: Live Round B — Witness Verification (Falsification) ของ Loop 1

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: KSS (MARGIN 3024959) + LIB (CASH) — ของจริง ตลาดเปิด
- Status: DRAFT (RE-PLAN 2026-10-15) — รอบก่อนถูก rollback ที่ tag `archive/loop1-v1` → commit `1fe7cf8` / `6c6819b` / `a666015` ไม่มีบน `main` แล้ว; ผล Gate/witness เดิมเป็นโมฆะทั้งหมด
- Run mode: INTERACTIVE 100% HITL — ไม่มี Kanban card (live round B + human witness)
- Depends on: TASK-loop1-1, TASK-loop1-2, TASK-loop1-3
- Unblocks: — (ปิด Loop 1 → ป้อนผลเข้า Argon Analysis)
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D5
- Verify: **human witness** (runbook — ไม่มี automated verify; บังคับมีคนดูหน้าจอจริง)

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §3 (Acceptance / Round B) — การ์ดนี้คือ "พยานยืนยัน" ด้วยตลาดจริงตามหลัก falsification · เริ่มได้หลัง Card 1–3 (รอบใหม่) merge ครบ + Gate ผ่านทั้ง 4 ข้อ

## Context
การ์ด 1–3 พิสูจน์แค่ระดับ unit/mock ยังไม่ยืนยันว่าของจริงทำงาน การ์ดนี้ต้องรันกับตลาดจริง โดยมี Admin เฝ้าหน้าจอ (witness) ทุกขั้น ห้ามเชื่อ log อย่างเดียว

## Gate เงื่อนไขก่อนเริ่ม (ต้องครบทุกข้อ) — **ยังไม่เช็คในรอบ RE-PLAN นี้ (ต้อง re-check ใหม่ก่อนเริ่มขั้น 1)**
> ⚠️ **RE-PLAN 2026-10-15:** รอบก่อนถูก rollback ทั้งหมดที่ tag `archive/loop1-v1` (kanban cards `26e91`/`3dc72`/`2a3ef`/`d6c3e` ถูกลบ) → commit `1fe7cf8` / `6c6819b` / `a666015` ไม่มีบน `main` ⇒ ผล Gate/witness ของรอบก่อน **เป็นโมฆะ** ต้อง re-check Gate ใหม่ทั้งหมดหลัง Card 1–3 (รอบใหม่: `5596a`→interactive ในห้องนี้ /`2b7ff`/`045ac`) merge ครบ
- [ ] การ์ด 1–3 (รอบใหม่) merge + `verify_changes.py` PASS → ต้องมี commit **ใหม่** บน `main`
- [ ] Gateway รันอยู่ที่ `app.main:app` (`curl http://127.0.0.1:8000/health` ตอบ) — **Admin start เองจาก main checkout** (`scripts/start_homelab.py`); agent ห้าม start/restart (Invariant 7/9 · LINE-RCA-011)
- [ ] ตลาดเปิด (KSS/LIB) มี volume จริง พอทำ 6 ขั้น witness
- [ ] Account: KSS = MARGIN 3024959 · LIB = CASH (ยืนยันตอน gateway รัน)

## Steps / Task Decomposition (Runbook — 1 ขั้น/รอบ, มีพยาน)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 1 | `/orders` (KSS) | คืนออเดอร์จริง หรือ `unavailable_card` ถ้า auth fail — **ห้าม 🟢 live ปลอม** | 👁 | ⬜ |
| 2 | `/orders` (LIB) | เติม LIB + แจ้งข้อจำกัด LIB ตรงไปตรงมา | 👁 | ⬜ |
| 3 | `/nego kss <sym> ราคาดีกว่า 1 tick` | กด Change Price **in-place** — ยืนยันว่าไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่า | 👁 | ⬜ |
| 4 | `/nego kss <sym> ราคาห่าง > 3 tick` | ปฏิเสธด้วย `MAX_TICKS_EXCEEDED` — **ไม่กดจริง** | 👁 | ⬜ |
| 5 | `/nego lib <sym>` | ราคา bid/offer ตรงหน้าจอจริง — ไม่มีราคาที่ถูกเดา | 👁 | ⬜ |
| 6 | `/nego lib <sym ผิด>` | fail-closed — ไม่กดเปลี่ยนราคา | 👁 | ⬜ |

> 🔁 **RE-PLAN 2026-10-15:** ขั้น 1–6 ทั้งหมด = **NOT RUN** (รอบก่อนหยุดที่ Gate แล้วถูก rollback) · ห้ามตีความ `⬜` เป็นผลบวก · ต้องผ่าน Gate ใหม่ทั้ง 4 ข้อก่อนเริ่มขั้น 1
>
> 📌 **Infra note (จากรอบก่อน — ยังใช้ได้):** session ที่สั่งผ่าน `kanban task start` เคยถูก `cancel` แบบ flaky (5–16 วิ) 2/3 ครั้งแรก แล้วครั้งถัดไปสำเร็จ — **ไม่เกี่ยวกับ concurrency cap** (`Scheduler concurrency = 2`) เพราะช่วงนั้นรันการ์ดเดียว · `hub-daemon.log` ไม่มี entry cancel/abort/limit ⇒ ถ้าการ์ดถูก cancel ให้ start ซ้ำได้ทันที (ไม่ต้องแก้โค้ด)

## Acceptance / Tests ที่ต้องผ่าน
- ทุกข้อ #1–#6 ตรง Expected Outcome **และ** พยาน (Admin) ยืนยันด้วยตาทุกข้อ
- ถ้าข้อใดไม่ผ่าน → **หยุดทันที** → ทำ 3-point RCA (session/context · live DOM · data schema) → แจ้ง Admin: `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`
- ห้าม self-anneal เกิน 3 ครั้งต่อข้อ

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** (ทดสอบเฉพาะ in-place change) · ห้ามยิง SMS OTP · ห้าม restart gateway ระหว่างทดลอง
- **ห้ามแก้โค้ดในการ์ดนี้** — ถ้าพบ bug ให้แยกเปิดการ์ดแก้ใหม่ (ตามหลัก 1 การ์ด = 1 งาน)

---

## Cline Report
- Git Commit(s): `TASK-loop1-N: <type>(<scope>): <summary>`
- Files changed:
- Summary:
- Tests run + result:
- Open questions:
---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED
---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
