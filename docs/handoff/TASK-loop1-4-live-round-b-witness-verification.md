# TASK-loop1-4: Live Round B — Witness Verification (Falsification) ของ Loop 1

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: KSS (MARGIN 3024959) + LIB (CASH) — ของจริง ตลาดเปิด
- Status: IN_PROGRESS (Gate #1 PASS · กำลังรัน Pre-market ขั้น 1–2)
- Run mode: INTERACTIVE 100% HITL (🔴 T2 · Flash 3.8 / Antigravity IDE + Human Witness)
- Depends on: TASK-loop1-1, TASK-loop1-2, TASK-loop1-3
- Unblocks: — (ปิด Loop 1 → ป้อนผลเข้า Argon Analysis)
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D5
- Verify: **human witness** (runbook — ไม่มี automated verify; บังคับมีคนดูหน้าจอจริง)

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §3 (Acceptance / Round B) — การ์ดนี้คือ "พยานยืนยัน" ด้วยตลาดจริงตามหลัก falsification · เริ่มได้หลัง Card 1–3 (รอบใหม่) merge ครบ + Gate ผ่านทั้ง 5 ข้อ (G1–G5)

## Context
การ์ด 1–3 พิสูจน์แค่ระดับ unit/mock ยังไม่ยืนยันว่าของจริงทำงาน การ์ดนี้ต้องรันกับตลาดจริง โดยมี Admin เฝ้าหน้าจอ (witness) ทุกขั้น ห้ามเชื่อ log อย่างเดียว

## Gate เงื่อนไขก่อนเริ่ม (G1–G5 ต้องครบทุกข้อ) — **re-check ก่อนเริ่มขั้น 0**
> ⚠️ **RE-PLAN 2026-10-15:** รอบก่อนถูก rollback ทั้งหมดที่ tag `archive/loop1-v1` → ผล Gate/witness ของรอบก่อน **เป็นโมฆะ** ต้อง re-check Gate ใหม่ทั้งหมดหลัง Card 1–3 (รอบใหม่) merge ครบ (`7bc4bf2`, `d7bde41`, `9ed1f5a`, `28b3468`)
- [x] **G1** การ์ด 1–3 (รอบใหม่) merge + `verify_changes.py` PASS → มี commit ใหม่ครบแล้วบน `main` (`7bc4bf2` loop1-1 · `d7bde41` loop1-2 · `9ed1f5a` loop1-3 · `28b3468` F-11 isolation; `--full` 677 passed)
- [x] **G2** Gateway รันอยู่ที่ `app.main:app` (`curl http://127.0.0.1:8000/health` ตอบ `status: healthy` · PID 53622 uvicorn UP) — Admin start เอง
- [x] **G3** ตลาดเปิด Pre-open window (~09:30–09:55) พร้อมรันขั้น 0–2 · G2 window `LINE_NEGO_WINDOWS` = `09:55-12:30,14:25-16:30` (รอขั้น 3–6)
- [x] **G4** Account: KSS = MARGIN 3024959 · LIB = CASH (ตรวจยืนยันในขั้น 1–2)
- [x] **G5** โหมดทดสอบยืนยันแล้ว: `DRY_RUN_MODE=True` + `TRADING_MODE=TEST` — Admin เซ็นรับโหมด Staging (ไม่กด Submit) ผ่าน Human Gate #1

## โหมดทดสอบ (บันทึกค่าปัจจุบัน + โหมดที่จะใช้จริง)
| Key | ค่าปัจจุบัน | แหล่ง |
|---|---|---|
| `DRY_RUN_MODE` | **`True`** (default) | `app/core/config.py` L100 · `.env` **ไม่ override** |
| `TRADING_MODE` | **`"TEST"`** | `.env` L37 |
| `TRADING_PLATFORM` | **`"TRADEMAN"`** | `.env` L42 |
| `LINE_NEGO_MAX_TICKS` | `3` (default) | `config.py` L33 · ไม่ override |
| `LINE_NEGO_WINDOWS` | `"09:55-12:30,14:25-16:30"` (default) | `config.py` L35 · ไม่ override |

**เส้นทาง submit ที่ขั้น 3**: `/nego kss` (LIVE) → `_broker_modify` (`handlers.py` L188–195) → `negotiate_order_price(..., execute=True, dry_run=None)` → `amend_price(dry_run=None → settings.DRY_RUN_MODE)`
- `DRY_RUN_MODE=True` ⇒ stage ราคา + PIN แล้ว **ไม่กด Submit** → `STAGED_DRY_RUN` (`submitted=False`) — ไม่มีอะไรถึง broker
- `DRY_RUN_MODE=False` ⇒ กด Submit จริง = **in-place amend จริง** (ต้อง Admin อนุมัติ + witness ดูจอ)

**โหมดที่จะใช้จริง (default ที่เสนอ): `DRY_RUN_MODE=True` + `TRADING_MODE=TEST` ตลอดรอบ** — ทุก `/nego` วิ่ง staging (ไม่กด Submit): ขั้น 3 พิสูจน์ "ไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่า" ที่ระดับ stage, ขั้น 4/6 พิสูจน์การปฏิเสธเต็มรูปแบบ. **LIVE amend จริง (ขั้น 3 เท่านั้น)** = human gate #1 — Admin ต้องตั้ง `DRY_RUN_MODE=False` อย่างชัดเจนก่อนรัน; agent ห้ามเปลี่ยนเอง

## Test targets (symbol / order_no ที่จะทดสอบ)
- **KSS (ขั้น 3–4)**: เป้าหลัก = order_no **`11008198`** (MTC · SHORT @ 29.25 · MARGIN 3024959) — อ้างจาก live probe 2026-10-14 (`learned_workflows/krungsri/quicktrade_native_change_order.md` §0) · **ต้อง re-confirm จาก `/orders kss` (ขั้น 1) ก่อนใช้** (ออเดอร์อาจ match/หมดอายุแล้ว)
  - ถ้า `11008198` ไม่อยู่แล้ว → ใช้ออเดอร์ค้าง (`balance > 0`) ตัวแรกจาก `/orders kss` (MARGIN 3024959)
  - ⚠️ ถ้าเป้าเป็น **SHORT** ขั้น 3 ต้องผ่าน G6 (strict uptick) — ราคาเป้าต้อง **สูงกว่า** LastPrice อย่างเคร่งครัด; ถ้าไม่มีออเดอร์ non-SHORT ค้าง ให้ Admin ยืนยันก่อนรัน
- **LIB (ขั้น 5–6)**: ใช้ออเดอร์ค้างตัวแรกจาก `/orders lib` (CASH) — **ไม่มี order_no คงที่บนบันทึก**; symbol ต้องตรงกับ `n` จาก quote API (D3 gate) ก่อนกด
- **ขั้น 6 (sym ผิด)**: ใช้ symbol ที่ **ไม่ใช่** symbol ของออเดอร์ที่เลือกในขั้น 5 (เช่นเลือก `A` แต่ส่ง `/nego lib BCH`) — ยืนยัน fail-closed ไม่กด

## Steps / Task Decomposition (Runbook — 1 ขั้น/รอบ, มีพยาน) — แบ่ง ก่อน / ระหว่าง / หลัง ตลาด

### 🅰 ก่อนตลาด (Pre-open ~09:30–09:55 — read-only + ยืนยัน Gate/โหมด/เป้า)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 0 | ยืนยัน G1–G5 + จด `DRY_RUN_MODE`/`TRADING_MODE` ที่อ่านได้จาก gateway จริง (เทียบหัวข้อ "โหมดทดสอบ") | ค่าตรงกับที่บันทึก; Admin เซ็นรับโหมด (staging หรือ LIVE amend ขั้น 3) | 👁 | ✅ PASS (`DRY_RUN_MODE=True`, `TRADING_MODE=TEST`) |
| 1 | `/orders` (KSS) | คืนออเดอร์จริง หรือ `unavailable_card` ถ้า auth fail — **ห้าม 🟢 live ปลอม**; จด order_no/symbol/balance ของออเดอร์ค้าง (MARGIN 3024959) เป็นเป้าขั้น 3–4 | 👁 | ✅ PASS (พบ `11008198`: MTC · SHORT @ 29.25 · MARGIN 3024959 ค้างอยู่จริง) |
| 2 | `/orders` (LIB) | เติม LIB + แจ้งข้อจำกัด LIB ตรงไปตรงมา; จด order_no/symbol ของออเดอร์ค้าง (CASH) เป็นเป้าขั้น 5–6 | 👁 | ✅ PASS (พบ `HMPRO` ค้างอยู่จริง · ใช้ symbol `HMPRO` เป็นเป้าขั้น 5) |

### 🅱 ระหว่างตลาด (During market — เฉพาะใน G2 window `LINE_NEGO_WINDOWS`, live bid/offer เท่านั้น)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 3 | `/nego kss <order_no จากขั้น 1>` (ราคาดีกว่า 1 tick) | กด Change Price **in-place** — ยืนยันว่าไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่า (same order_no, volume เท่าเดิม); staging (DRY_RUN=True) = `STAGED_DRY_RUN` (ราคา+PIN กรอกแล้ว, ไม่กด Submit) | 👁 | ⬜ |
| 4 | `/nego kss <order_no เดิม> ราคาห่าง > 3 tick` | ปฏิเสธด้วย `MAX_TICKS_EXCEEDED` — **ไม่กดจริง** (เหตุผลระบุจำนวน tick) | 👁 | ⬜ |
| 5 | `/nego lib <order_no จากขั้น 2>` | ราคา bid/offer ตรงหน้าจอจริง — ไม่มีราคาที่ถูกเดา (gate `n == symbol` D3) | 👁 | ⬜ |
| 6 | `/nego lib <sym ผิด>` | fail-closed — ไม่กดเปลี่ยนราคา (`QUOTE_UNAVAILABLE`/`SYMBOL_MISMATCH` → `unavailable_card`) | 👁 | ⬜ |

### 🅲 หลังตลาด (After market / EOD — reconcile + sign-off)
| # | Action | Expected Outcome | Witness | Status |
|---|---|---|---|---|
| 7 | `/orders` (KSS + LIB) ซ้ำ เทียบ snapshot ก่อนตลาด | order_no/volume ยังเท่าเดิม (ไม่มีออเดอร์ใหม่/ไม่มียกเลิกเก่าจากขั้น 3–6) | 👁 | ⬜ |
| 8 | สรุป witness: ทุกข้อตรง Expected Outcome + พยานเซ็นด้วยตา → ปิด Loop 1 (D5) | Cline Report + ป้อนผลเข้า Argon Analysis | 👁 | ⬜ |

> 🔁 **RE-PLAN 2026-10-15:** ขั้น 0–8 ทั้งหมด = **NOT RUN** (รอบก่อนหยุดที่ Gate แล้วถูก rollback) · ห้ามตีความ `⬜` เป็นผลบวก · ต้องผ่าน Gate ใหม่ทั้ง 5 ข้อ (G1–G5) ก่อนเริ่มขั้น 0
>
> 📌 **Infra note (อัปเดต 2026-10-15 เย็น — root cause ปิดแล้ว):** การที่ session ที่สั่งผ่าน `kanban task start` ถูก `cancel`/`interrupted` กลางเทิร์น (และบางรอบค้าง ~30 วิ) **ไม่ใช่ flaky และไม่เกี่ยวกับ concurrency cap** — เกิดจาก **hub daemon spawn ไม่ขึ้น**: `kanban@0.1.70` ไม่ ship `dist/entry.js` ที่ `dist/cli.js` เรียก (`MODULE_NOT_FOUND` ใน `~/.cline/data/logs/hub-daemon.log`) → hub command timeout ~30 วิ → session จบเป็น `cancelled` · **แก้แล้วด้วย shim เครื่องนี้ + พิสูจน์ end-to-end แล้ว** (การ์ด smoke `f76e7` รันจบ `status: completed`) — รายละเอียด/โค้ด: `rca/shared/rca_kanban_hub_daemon.md` (KB-RCA-001) · ถ้าการ์ดถูก cancel อีก **ให้เช็ค `hub-daemon.log` ว่ามี `MODULE_NOT_FOUND` ใหม่ไหม** (ถ้ามี = shim ถูกทับหลัง npm upgrade → ติดตั้งซ้ำ)

## Acceptance / Tests ที่ต้องผ่าน
- ทุกข้อ #0–#8 ตรง Expected Outcome **และ** พยาน (Admin) ยืนยันด้วยตาทุกข้อ
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

## Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED
---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
