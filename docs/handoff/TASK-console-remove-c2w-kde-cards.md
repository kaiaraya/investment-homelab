# TASK-console-remove-c2w-kde-cards: ถอดการ์ด Click2Win Sandbox + KDE Connect Bridge ออกจาก /console

- Created: 2026-10-10 by Antigravity
- Broker: N/A (UI/console only — ไม่แตะ broker driver)
- Status: DONE (UI ✅ · LINE OTP live login verified GO ✅)

## Context (Antigravity เขียน)
`/console` ยังแสดงการ์ด **Settrade Click2Win Sandbox** และ **KDE Connect Bridge** ซึ่งไม่ใช่ช่องทางหลักแล้ว
(LINE relay ผ่าน OA `@678clhio` เป็น authoritative channel ตั้งแต่ 2026-10-08 · KDE เป็น dormant)

เป้าหมาย: ถอด 2 การ์ดออกจาก UI + ถอด readiness-banner Step 1 (KDE) พร้อม renumber + ล้าง JS ที่ผูกกับ element ที่ถูกถอด
(ถ้าไม่ล้าง JS → `checkUnifiedHealth()` จะ `TypeError` เพราะ `c2wStatusPill`/`kde*` คืน null)

**Scope = UI-only** — backend `/api/v1/session/health` (ยังคืน `settrade`/`kdeconnect`),
`session_connect_all`, `/session/kdeconnect/ping` **ไม่แตะ** (KDE โค้ดยังอยู่ ไม่ลบ — Zero-Contradiction)

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/console.py`
- `tests/test_console_cockpit_api.py`

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 1 | HTML: ลบการ์ด Click2Win + renumber comment Liberator (`3.`→`2.`) + แก้ `(5 Cards)`→`(2 Cards)` | ไม่มี `<span>🎯 Click2Win Sandbox</span>` | `verify_changes.py` + grep | ✅ |
| 2 | HTML: ลบการ์ด KDE Connect Bridge | ไม่มี `<span>📱 KDE Connect Bridge</span>` | `verify_changes.py` + grep | ✅ |
| 3 | HTML banner: ลบ Step 1 (KDE) + renumber `2.`→`1.`, `3.`→`2.` (คง id `step2KssCard`/`step3ReadyCard`) | เห็น "1. Krungsri TradeMan Session" + "2. Operations Cockpit Status" | live `/console` grep | ✅ |
| 4 | JS: ลบบล็อก Click2Win + Settrade Open API (dead code) | ไม่มี `c2wStatusPill`/`openApiStatusPill` ใน JS | `verify_changes.py` | ✅ |
| 5 | JS: ลบบล็อก KDE (pill/route/channels) | ไม่มี `getElementById('kde…')` | static dangling check | ✅ |
| 6 | JS readiness: ลบ `step1Badge/step1Card`, `isKdeReady`; `if (isKdeReady && isKssReady)`→`if (isKssReady)`; ตัด pendingItems KDE | readiness Step GO ไม่พึ่ง KDE อีก | `verify_changes.py` | ✅ |
| 7 | JS: ลบ `triggerKdePing()` + `triggerKdeRefresh()` | ไม่มี `triggerKdePing` ในไฟล์ | grep = NONE | ✅ |
| 8 | Tests: ลบ positive asserts (L17, L19) + เพิ่ม negative asserts (card-specific) | test ผ่าน | `.venv/.../verify_changes.py` | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/console.py tests/test_console_cockpit_api.py` → PASS (exit 0)
- `.venv/bin/python scripts/verify_changes.py --full` → ครั้งเดียวตอนปิดงาน
- static dangling-ID check: `getElementById` target ทุกตัวต้องมี `id="…"` จริง → DANGLING: NONE

## Out of scope / ห้ามแตะ
- `app/services/otp_relay_readiness.py`, `/api/v1/session/*`, `app/browser/auth_driver.py`
- Order placement / tick size / price-volume validation — ไม่แตะเลย
- ข้อความ prose ที่ยังอ้าง Click2Win/KDE (ดู Open questions)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/console.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_console_cockpit_api.py`
- Summary:
  - ลบการ์ด **Click2Win Sandbox** (id `c2wStatusPill`/`c2wHeartbeat`) และการ์ด **KDE Connect Bridge**
    (id `kdeStatusPill`/`kdeReachable`/`kdeActiveRouteBadge`/`kdeRemoteIp`/`kdeWifiChannel`/`kdeTsChannel`) ออกจาก `/console`
  - Readiness banner: ลบ Step 1 (KDE) + renumber เป็น "1. Krungsri TradeMan Session" / "2. Operations Cockpit Status"
    (คง element id เดิม `step2KssCard`/`step3ReadyCard` เพื่อไม่ให้ JS อื่นพัง) + อัปเดต comment หัวไฟล์
  - JS `checkUnifiedHealth()`: ลบบล็อก Click2Win + Settrade Open API + KDE (route/channels) ทั้งหมด
  - JS readiness: ลบ `step1Badge`/`step1Card`/`isKdeReady`; เงื่อนไข GO เปลี่ยนเป็น `if (isKssReady)`;
    ตัด "KDE Connect" ออกจาก `pendingItems`
  - ลบ `triggerKdePing()` + `triggerKdeRefresh()` (ฟังก์ชันตายหลังถอดปุ่ม)
  - Tests: ลบ positive asserts ของ 2 การ์ด + เพิ่ม negative asserts แบบ **card-specific**

- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/console.py tests/test_console_cockpit_api.py`
    → `PASS (targeted) in 6.8s`, exit 0 (4 passed) — หลังแก้ assertion รอบแรกที่ FAIL (ดู RCA ด้านล่าง)
  - static dangling-ID check (`getElementById` targets vs `id="…"`) → `DANGLING: NONE` (54 targets / 68 ids)
  - live `/console` (gateway :8000): `🎯 Click2Win Sandbox`, `📱 KDE Connect Bridge`, `Hardware Bridge (KDE Connect)`,
    `c2wStatusPill`, `triggerKdePing`, `step1KdeCard` = **absent**; `1. Krungsri TradeMan Session`,
    `2. Operations Cockpit Status`, `Krungsri TradeMan`, `Liberator WebTrade` = **present**
  - `otp_relay_readiness.check()` → `ready=True`, `channel=line_direct`, probe `profile/U93d…bd2` = `reachable`
  - `scripts/daily_readiness.py --no-login --no-ping --json` → `NO-GO` (คาดหมาย: ข้าม login โดยเจตนา)
    relay=READY · Krungsri `session_state.json` **MISSING** (needs_fresh_login) · Liberator expired · Click2Win ไม่มีไฟล์
  - `.venv/bin/python scripts/verify_changes.py --full` → `3 failed, 365 passed, 2 warnings in 180.66s` (exit 1)
    — ทั้ง 3 failure เป็น **pre-existing** และ **อยู่นอก scope** (ดู Open questions ข้อ 4)

  - ✅ **LIVE OTP login verified (user approved, 2026-10-10 14:06–14:08)** — `scripts/daily_readiness.py` (full, ไม่มี flag):
    - Krungsri OTP **Ref `RPPL`** pushed ผ่าน LINE → session saved `data/session_state.json` (27,872 B @14:07)
    - Liberator OTP **Ref `UHGC`** pushed → `🎉 2FA OTP CAPTURED VIA line_chat! Captured OTP Code: 782123`
      → session saved `data/liberator_session.json` (3,521 B @14:08)
    - **ผลลัพธ์: `✅ GO — พร้อมทดสอบ pillar ถัดไป` (exit 0)** · OTP relay = LIVE (channel=line_direct) ·
      Krungsri = AUTHENTICATED · Liberator = AUTHENTICATED
  - ✅ ยืนยันซ้ำแบบ report-only: `scripts/daily_readiness.py --no-login --no-ping --json` → **`verdict: GO`, exit 0**
    (Krungsri `verdict=RECENT / needs_fresh_login=false`; Liberator `expired=false`) → Zero-OTP persistence ทำงาน

- RCA (PDCA) — verify FAIL รอบแรก:
  - **Symptom:** `assert "Click2Win Sandbox" not in body` FAIL แม้ถอดการ์ดแล้ว
  - **Root cause:** phrase เปล่า `Click2Win Sandbox` ยังปรากฏใน prose ของการ์ด *Order Execution* (บรรทัด ~1015)
    → assertion ระดับ phrase กว้างเกินไป ชนกับ copy ที่ยังใช้งานจริง
  - **Fix:** เปลี่ยนเป็น card-specific marker (`"🎯 Click2Win Sandbox"`, `"📱 KDE Connect Bridge"`) ซึ่ง unique ต่อการ์ดที่ถอด
  - **Edge case:** การ์ด title มี emoji นำ → ใช้ emoji+title เป็น discriminator ที่เสถียร

- Open questions:
  1. **Live OTP re-login ยังไม่ทำ** — relay พร้อม แต่ต้องยิง SMS OTP จริง + ผู้ใช้พิมพ์รหัสเข้า LINE
     (รอ HITL confirm; ไม่ยิงอัตโนมัติในรอบนี้)
  2. ข้อความ prose ที่ยังอ้างถึง (นอก scope, ไม่ได้แก้):
     - `app/console.py:~780` OTP hint: "(หาก KDE Connect ดึงผ่าน D-Bus ไม่สำเร็จ …)"
     - `app/console.py:~890` CLI card: "ระบบผ่านการตรวจสอบ Hardware Bridge และ Krungsri Session …" (อ้าง step ที่ถอดไปแล้ว)
     - `app/console.py:~1138` help text: "• KDE Connect: เชื่อมต่อ D-Bus เพื่อรับ OTP อัตโนมัติ"
     - `app/console.py:~1352` toast "เชื่อมต่อทุกโบรกเกอร์ (KDE Connect, Click2Win, TradeMan, Open API)..."
     - `app/console.py:~930-933` CLI cheat sheet "Click2Win Multi-Account Test" + `~1015/~1022` broker dropdown
       `CLICK2WIN` (ต้องคงไว้ — backend ยังรองรับ Click2Win จริง) → แนะนำแก้เฉพาะข้อความ KDE ในรอบถัดไป
  3. Gateway ถูกเปิดค้างไว้จากรอบนี้ (`uvicorn app.main:app` :8000, log `/tmp/homelab_gateway.log`)
  4. **Full suite มี 3 failure ที่มีอยู่ก่อนแล้ว (ไม่เกี่ยวกับงานนี้) — พิสูจน์แล้ว:**
     `tests/test_liberator_change_order.py::{test_negotiate_price_amends_in_place_and_never_cancels,
     test_negotiate_price_is_noop_when_already_at_target, test_negotiate_price_propagates_amend_failure}`
     - **Symptom:** `KeyError: 'action'` (L373/L392) + `assert True is False` (L407)
     - **Root cause (RCA):** `LiberatorDriver.negotiate_price()` (driver.py:1312-1324) มี weekend early-return
       `if now_bkk.weekday() in (5,6): return {"success": True, "status": "MARKET_CLOSED", "staged": True, ...}`
       ซึ่ง **ไม่มี key `action`** → pre-empt เส้นทาง amend ที่ test ต้องการตรวจ
     - **หลักฐานวัน:** `date` = `Saturday 2026-10-10`, `weekday()=5` → branch ทำงานจริง →
       **test failures นี้เป็น date-dependent (จะ fail เฉพาะเสาร์–อาทิตย์)**
     - **หลักฐานว่าไม่ใช่งานผม:** mtime `app/brokers/liberator/driver.py` และ `tests/test_liberator_change_order.py`
       = `2026-10-09 10:25` (ก่อน session นี้) ขณะที่ไฟล์ที่แก้ = `app/console.py 2026-10-10 13:44`,
       `tests/test_console_cockpit_api.py 2026-10-10 13:46`; และรัน test file เดี่ยวก็ fail เหมือนกัน
       (`3 failed, 17 passed in 7.58s`)
     - **ข้อเสนอ (นอก scope):** ใส่ `"action": "MARKET_CLOSED"` ใน branch weekend หรือให้ test freeze
       เวลา (mock `datetime`) เป็นวันทำการ
