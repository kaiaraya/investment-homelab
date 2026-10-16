# TASK-sq2: Liberator Halt/Pre-Open Zero Price Guard

- Created: 2026-10-16 by Argon (Complex Task Owner · Antigravity)
- Loop: 1  (board: `docs/board/loop_board.md` — Section 6 Side-Quests)
- Broker: Liberator WebTrade (LIB · CASH)
- Tier: 🟢 T0
- Implementer: JULES (`Gemini 3.6 Flash`)
- Pre-Coding Probe: NONE  (pure python driver numeric sanitization; quote API contract already proven in LIB-RCA-020)
- Git Branch: `task/sq2-liberator-halt-zero-price-guard`
- Status: READY
- Verify: `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py tests/test_liberator_change_order.py`

## Directive delta (Argon เขียน — STEP 0)
อ้างอิง `directive/master_directive_v2.md` §4 Invariant 1 (Anti-Mock Fail-Closed) และ Open question ข้อ 4 จาก `TASK-loop1-3`:
- เมื่อหุ้นอยู่ในสถานะ Halt, Pre-open หรือไม่มี Bid/Offer ในกระดาน API `/vb/stock/info` ของ Liberator จะส่ง `bp="0"` หรือ `op="0"`
- ฟังก์ชัน `get_market_bid_offer()` ต้องไม่คืนค่าราคา `0.0` เป็นราคาตลาด — หากค่าที่แปลงได้ `<= 0.0` ต้องแปลงเป็น `None` ทันที และหากทั้ง `bid_1`, `offer_1`, และ `last` เป็น `None` ต้อง fail-closed ด้วย `_quote_unavailable` (สถานะ `QUOTE_UNAVAILABLE`)

## Context (Argon เขียน — STEP 0)
ใน `app/brokers/liberator/driver.py` เมธอด `get_market_bid_offer()` (L924-927) ใช้ `self._to_float(record.get("bp"))` ซึ่งเมื่อได้ `"0"` จะคืนค่าเป็น `0.0` แม้ว่าในชั้น Handler จะมี G4 tick-size สกัดไว้ แต่ในระดับ Driver ควร fail-closed อย่างซื่อสัตย์ ไม่คืนราคา `0.0` ออกมาตั้งแต่ต้นทาง

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/brokers/liberator/driver.py`
- `tests/test_liberator_change_order.py`

## Context map
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `app/brokers/liberator/driver.py` | `get_market_bid_offer` L924-931 | edit: ถ้า `bid_1 <= 0` ให้เป็น `None`, ถ้า `offer_1 <= 0` ให้เป็น `None`, ถ้า `last <= 0` ให้เป็น `None` |
| `tests/test_liberator_change_order.py` | `test_get_market_bid_offer_*` | edit/add: เพิ่มเคสทดสอบ `bp="0"`, `op="0"`, `l="0"` ต้องได้ `success=False` / `QUOTE_UNAVAILABLE` |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | ปรับ `get_market_bid_offer` ใน `driver.py` | ราคา `<= 0` กลายเป็น `None` และถ้าไม่มีราคาบวกจะคืน `_quote_unavailable` | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 2 | เพิ่ม Unit Test ใน `test_liberator_change_order.py` | ทดสอบ payload ที่มี `"bp": "0"`, `"op": "0"` คืน `QUOTE_UNAVAILABLE` | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 3 | รัน verify_changes.py | PASS ครบทุกเทสต์ | `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py tests/test_liberator_change_order.py` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py tests/test_liberator_change_order.py`
- `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q`

## Out of scope / ห้ามแตะ
- ห้ามแก้ selector DOM หรือ flow อื่นของ Liberator
- ห้ามยิง API จริง (รันผ่าน unit/mock บน Cloud VM)

---

## Jules Report (Jules เขียนบน Cloud VM — STEP 2a · Gemini 3.6 Flash)
- Git Commit(s): Pending submit
- Files changed:
  - `app/brokers/liberator/driver.py`
  - `tests/test_liberator_change_order.py`
  - `docs/handoff/TASK-sq2-liberator-halt-zero-price-guard.md`
- Summary:
  - Updated `get_market_bid_offer` in `app/brokers/liberator/driver.py` to convert non-positive `bid_1`, `offer_1`, and `last` values (`<= 0.0`) to `None`.
  - Enforced fail-closed behavior returning `_quote_unavailable` with status `QUOTE_UNAVAILABLE` when all bid/offer/last values are `None`.
  - Added unit tests in `tests/test_liberator_change_order.py` covering full zero prices and partial zero prices.
- Tests run + result (Cloud VM):
  - `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` (37 passed)
  - `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py tests/test_liberator_change_order.py` (79 passed, PASS)
- Open questions: None

---

## Cline Triage Report (Cline plugin เขียนในเครื่อง — STEP 2b)
- Local Branch Checked:
- Invariant & Scope Audit:
- Local Verify Result:
- Triage Verdict & Summary for Argon:
