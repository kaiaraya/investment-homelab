# TASK-pin-safety-20261029: PIN ถูกเผาจนบัญชี 3024959 ถูกระงับ — ทำ guard + audit + ปิดช่องยิงซ้ำ

- Created: 2026-10-29 by Argon (blocker fix, T0) — ต่อจากเหตุการณ์ยิง PIN ผิด 14:16:36 และบัญชีถูก suspend
- Status: REVIEW (unit PASS · live ยังต้อง witness หลังโบรกปลดระงับ)
- Tier: 🟢 T0 local fix
- Source: incident 2026-10-29 (LINE `DRAFT-D33B703C`, modal "Your pin is suspended", HAR `kss_order_all.har`)

## Root cause (สรุป)

1. **ไม่มีการนับ PIN ที่ถูกปฏิเสธเลย** — `order_executor.execute_order_via_cdp` คืน `result` ทิ้งเมื่อ status
   ไม่ใช่ `SUBMITTED/UNCONFIRMED` → ไม่มีแถวใน `orders` และไม่มี `session_logs` → มองไม่เห็นว่า PIN เริ่มผิดเมื่อไร
2. **alert ของหน้า Settrade ถูก Playwright dismiss เงียบ ๆ** (`page.on("dialog")` ไม่ถูกติดตั้ง) → ข้อความ
   "pin is suspended / incorrect PIN" หายไปทั้งหมด
3. **streaming_driver สร้างเลขออเดอร์ปลอม** `STM-<epoch>` แล้วรายงาน `SUBMITTED` แม้หน้าเว็บขึ้น error →
   automation คิดว่าสำเร็จและยิงต่อ
4. **amend แบบ cancel+replace เผา PIN 2 ครั้งต่อ 1 amend** (cancel 1 + replace 1) และมี retry ที่ยิง
   อีกครั้งเมื่อ re-submit ล้มเหลว → เช้า 09:55–11:11 ตัวนับเต็ม ก่อนใบจริง 14:16 จะถูกปฏิเสธ
5. **unit test suite แตะ broker จริงได้** — `order_executor` ลอง JS snippet (`streaming_place.js`) ก่อน fallback
   DOM; เมื่อ gateway เปิด Chrome อยู่ `pytest` ธรรมดาจึง POST เข้า `apigw.settrade.com` พร้อม PIN จริง
   (พบระหว่างแก้รอบนี้: 14:34 โบรกตอบ "Your pin is suspended as you have exceeded maximum pin attempts")

## Fix

1. **1.1 Freeze live orders** — `.env`: `DRY_RUN_MODE=true` (+ ค่า `PIN_GUARD_*`) และ restart gateway
   (`.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, ห้าม `--reload`)
2. **1.3 Anti-Mock** — `app/browser/streaming_driver.py`: ลบ `or f"STM-{epoch}"`; อ่านเลขออเดอร์ไม่ได้ →
   `status="UNCONFIRMED"` + `E_ORDER_NO_UNREADABLE` + `session_logs: STREAMING_ORDER_UNCONFIRMED`
3. **1.4 Dialog capture** — `order_executor._install_dialog_capture()` ติด `page.on("dialog")` ระหว่างส่งคำสั่ง
   และ `streaming_driver.execute_order` hook dialog เอง → ข้อความจากโบรกถูกเก็บทั้งก้อน (`dialog_text`)
4. **1.5 PIN guard** — โมดูลใหม่ `app/services/pin_guard.py`
   - `classify_pin_error()` แยก `E_PIN_REJECTED` / `E_PIN_SUSPENDED` (อังกฤษ + ไทย)
   - `check()` fail-closed: PIN ถูกปฏิเสธ 1 ครั้ง → quarantine broker 240 นาที (`data/pin_guard.json`)
   - `record_failure()` / `record_success()` / `reset()` — เคลียร์อัตโนมัติเฉพาะเมื่อโบรกรับออเดอร์จริง
   - เรียกใน `execute_order_via_cdp` (ก่อน validator เพื่อไม่กิน idempotency slot), `streaming_driver.execute_order`
     (ก่อนช่อง PIN ถูกกรอก), `cancel_order`, `change_order_native` (fallback_ok=False), `_lib_preflight`
5. **1.6 Persist refusal** — `orders` ได้แถว `status=REJECTED` + `error_message` เมื่อ `submitted=True`;
   `session_logs: CDP_ORDER_REJECTED` ทุกครั้ง; `OrderStatus` เพิ่ม `UNCONFIRMED`, `SIMULATED_SUCCESS`
6. **1.7 ห้ามยิงซ้ำ** — `handlers._kss_cancel_replace`: ลบ retry@old_price (1 amend = 1 PIN submit) และ
   `_lib_preflight` เลิกใช้ PIN ปลอม `"123456"`
7. **Test hygiene** — `tests/conftest.py`: autouse ปิด `js_runner.run_snippet` (ห้ามแตะ CDP จริง) และแยก
   `PIN_GUARD_STATE_PATH` ต่อ test

## Verification

- `pytest tests/test_pin_guard.py tests/test_broker_cdp_order_executor.py tests/test_streaming_driver.py` → **76 passed**
- เคสใหม่: dialog "pin is suspended" → `REJECTED` + แถว `orders` + guard ปิดการยิงครั้งถัดไป (`E_PIN_GUARD`, ไม่คลิกอะไรเลย)
- เคสใหม่: refusal ก่อน submit ต้องไม่เขียน `orders`; submit สำเร็จต้องเคลียร์ quarantine
- `scripts/pin_guard.py status|classify|reset` ใช้งานได้ (ไม่มี PIN เก็บในไฟล์ state)

## ปลดล็อกก่อนเทรดจริง

```bash
.venv/bin/python scripts/pin_guard.py status
.venv/bin/python scripts/pin_guard.py reset kss --reason "Krungsri 1.2 ปลดระงับ + ยืนยัน PIN ใน .env"
```

แล้วค่อย `DRY_RUN_MODE=false` เฉพาะตอน witness (มีคนดูหน้าจอ) เท่านั้น

## Open questions

- 14:34 API ยังตอบ "pin is suspended … exceeded maximum pin attempts" → ต้องยืนยันกับ Krungsri ว่า
  การปลดระงับมีผลแล้วหรือต้อง login ใหม่/รอรอบถัดไป (อย่าลองยิงซ้ำเอง)
- `change_order_native` (PATCH in-place) ยังไม่ได้ witness สดหลังเพิ่ม guard
