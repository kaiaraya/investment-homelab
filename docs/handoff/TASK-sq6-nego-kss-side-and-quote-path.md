# TASK-sq6: `/nego kss` ถูก skip ทุกใบ — side code `H`/`C` ไม่รู้จัก + pre-plan ด้วย quote ที่ไม่มี bid/offer

- Created: 2026-10-19 by Argon (blocker fix, T0)
- Status: REVIEW (unit PASS · live pending)
- Tier: 🟢 T0 local fix → triage
- Blocks: `TASK-loop1-4` ขั้น 3–4 (KSS)
- Source: witness run 2026-10-19 11:28 (LINE + audit log + live ledger)

## Evidence

1. **Audit log** (`session_logs`):
   `LINE_CLI_NEGO: kss #11008937 H BCPG skip unsupported side 'H'`
2. **Live QuickTrade ledger** (`list_open_orders`, 11:32):
   ```json
   {"order_no":"11012286","side":"C","price":155.5,...}
   {"order_no":"11008937","side":"H","price":6.8,...}
   ```
   หน้าเว็บส่ง side เป็นตัวอักษรเดี่ยว `C` (cover) / `H` (short sell) แต่ `_SIDE_ALIASES` ไม่มีรหัสเหล่านี้ → `plan_negotiation` คืน `UNSUPPORTED_SIDE` ทุกใบ
3. **Quote source**: ถึงแก้ side แล้ว `_plan_nego("kss", ...)` ยังใช้ `trademan_driver.get_market_bid_offer()` ซึ่ง **คืน bid_1/offer_1 = None โดยเจตนา** (depth ไม่อยู่ใน REST endpoint) → `NO_QUOTE` ทุกใบ → ไม่เคยไปถึง Quick Trade amend

## Fix

1. `app/brokers/krungsri/quicktrade_driver.py` → `_SIDE_ALIASES` เพิ่ม `B→BUY`, `S→SELL`, `H→SHORT`, `C→COVER` + Thai labels
2. `app/services/line_cli/handlers.py` → `_handle_nego`: สำหรับ `kss` **ข้าม `_plan_nego`** แล้วเรียก `_broker_modify` ตรง (Quick Trade service resolve order + quote + G4–G6 เอง) — หลีกเลี่ยง quote ที่ไม่มี depth และลดจำนวน browser context จาก 4 เหลือ 3
3. Tests: เพิ่มเคส single-letter side mapping · ย้ายเคส G5/G6 ของ handler ไปทดสอบบน `lib` (kss ใช้ guardrails ใน service)

## Verification

- `pytest tests/test_quicktrade_driver.py tests/test_line_cli_flow.py` → **113 passed**
- `verify_changes.py` → **PASS (targeted)**
- Live: รอ witness รอบใหม่ (ต้อง restart gateway เพราะ `handlers.py` ถูก import แล้ว)

## Open questions
- G5 (`MAX_TICKS_EXCEEDED`) บน kss ตอนนี้บังคับใน service (`plan_negotiation`) — ต้องยืนยันสดด้วยออเดอร์ที่ห่าง >3 ticks (ขั้น 4)
- ยังไม่แก้ปัญหา browser context หลายตัวต่อ `/nego` 1 ครั้ง (SQ-5 open question) — ถ้า session เด้งอีกให้เปิดการ์ดแยก

## Cline Report
- Git Commit(s):
- Files changed:
- Tests run + result: 113 passed · verify PASS
- Open questions: ตามด้านบน
