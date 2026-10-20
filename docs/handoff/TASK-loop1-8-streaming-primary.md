# TASK-loop1-8 — Switch primary broker: TradeMan → Settrade Streaming

**สถานะ:** PLANNED (รอ Phase 0 probe)
**เปิดโดย:** 2026-10-20
**Tier:** T0 = Jules 3.6 Flash (probe), T1 = Jules 3.1 Pro (driver/route), T2 = Antigravity Flash 3.8 + human witness (live)
**บริบท:** TradeMan ขาด native amend → ต้อง cancel+replace (D1 เดิม: in-place only ถูกผ่อนเป็นทาง (A) แล้ว) และ login มีปัญหา OTP/reconnect ซ้ำ (KSS-RCA-014/015/016). ผู้ใช้เปลี่ยนให้ **Settrade Streaming เป็นตัวหลัก** แทน TradeMan — probe + dry_run ก่อน, โฟกัส nego, และเปลี่ยนฟังก์ชัน login เป็น Streaming เมื่อสั่งผ่าน LINE.

---

## ข้อสมมติฐานที่ต้องยืนยันใน Phase 0 (ห้ามถือว่าเป็นจริงจนกว่า probe)

| # | สมมติฐาน | สถานะ |
|---|---|---|
| A1 | URL = `streaming.settrade.com` (ไม่ใช่ `click2win.settrade.com` sandbox) | ✅ ยืนยันโดยผู้ใช้ (ตัวเลือก 1) |
| A2 | บัญชีเป็น **live จริง** (creds = username/password ของโบรกเกอร์) | ✅ live; โบรกเกอร์/เลขบัญชีรอ probe ยืนยัน |
| A3 | Login = username+password **+ 2FA** (SMS OTP / Streaming Token) — 2FA ครั้งแรกต่อ device อาจต้อง OTP | ✅ ยืนยันจากคู่มือ Settrade (SBITO PDF) |
| A4 | มีปุ่ม **Modify/Change** ในออเดอร์ค้าง (native in-place amend) | ⏳ probe |
| A5 | มี bid/offer depth ใน DOM (หรือ API) | ⏳ probe |

> **หมายเหตุ login:** Streaming ใช้ username/password ชุดเดียวกับระบบซื้อขายของโบรกเกอร์ + 2FA (OTP SMS หรือ Streaming Token/QR). ไม่เหมือน Click2Win sandbox ที่ login ล้วน ๆ. `click2win_auth_driver.login()` ยังไม่มี 2FA handler → ต้องเพิ่มใน Phase 1.2.

---

## Phase 0 — ผล Probe (2026-10-20, ยืนยันแล้ว)

### Login flow จริง = **Krungsri SSO → Settrade Streaming** (ไม่ใช่ Settrade direct 2FA)

1. `KRUNGSRI_LOGIN_URL` (krungsrisecurities.com) → `#login_username` + `#login_password` → submit `#login`
2. SMS OTP (6 หลัก) → member portal `CreditBalance_Announcement.aspx`
3. คลิก **"โปรแกรม Streaming"** → SSO endpoint:
   `javascript:popup('../../Put_SSO_Settrade.aspx?Page=streaming','',window.screen.width,window.screen.height)`
4. เปิด popup → `https://wma1.settrade.com/realtime/streaming7/StreamingPage.jsp`

> ทางตรง Settrade (streaming.settrade.com → broker KRUNGSRI → Settrade 2FA confirm-device/Streaming Token/QR/SMS) ก็ใช้ได้ แต่ผู้ใช้เลือกเส้น **Krungsri SSO** (เหมือน TradeMan `start_SSO.aspx?page=TM`)

### Trading DOM (StreamingPage.jsp)

| Element | Selector |
|---|---|
| บัญชี | `3024952 (Equity)` — A/C Type **Cash**, Credit Limit 500,000 (บัญชีเดียวกับ TradeMan cash) |
| Symbol | `input[placeholder='Symbol']` |
| Volume | `input[name='equity-place-order-vol']` |
| Price | `input[name='price-input']` |
| PIN | `input#pin` |
| Submit | `button` text "Submit" (class `bg-color-dark-blue-60`) |
| Side | แท็บ "Buy / Sell" ในฟอร์ม (ต้อง dump selector ละเอียดเพิ่ม — regex แรกไม่จับ) |
| Cancel | ปุ่ม "Cancel0Order(s)" (0 = จำนวนออเดอร์ที่เลือก) + ตาราง order header "Order No./Date/Time/Symbol/Side..." |
| Bid/Offer | มี panel "Volume **Bids Offers** Volume" (depth มีใน DOM) — default แสดง BIDU |
| Modify | **ยังไม่พบปุ่ม Modify/Change** — มีแค่ Cancel (แต่ตาราง order ว่าง 0 ใบ ต้องรอมีออเดอร์ค้างถึงจะเห็น action ต่อแถว) |

### สรุป A1–A5

- A1 ✅ `streaming.settrade.com` → จริง ๆ ลง `wma1.settrade.com/realtime/streaming7/StreamingPage.jsp`
- A2 ✅ live จริง บัญชี `3024952` (เดียวกับ TradeMan)
- A3 ✅ Krungsri SSO (user/pass + SMS OTP) — **ไม่ใช่** Settrade 2FA device
- A4 ⏳ ยังไม่พบ Modify native — น่าจะ cancel+replace เหมือน Click2Win (รอ test ตอนมี order ค้าง)
- A5 ✅ มี bid/offer depth panel

### Scripts probe (ทั้งหมด read-only)
- `scripts/streaming/dump_login_page.py` — ดัมป์หน้า login + broker list (33 โบรกเกอร์, มี KRUNGSRI)
- `scripts/streaming/dump_broker_list.py` — broker list
- `scripts/streaming/probe_streaming.py` — manual-login probe (7 รายการ)
- `scripts/streaming/probe_autologin.py` — Settrade direct login + 2FA drive
- `scripts/streaming/probe_krungsri_sso.py` — ดัมป์ SSO links ของ portal
- `scripts/streaming/probe_streaming_sso_full.py` — **เส้น Krungsri SSO ครบวง** (ได้ผล Phase 0)

> ⚠️ ทุก probe ยังไม่ save storage_state ตอนจบ → ต้อง re-login ทุกครั้ง. Phase 1 ต้องแก้ให้ save session (`data/streaming_session.json`) เพื่อไม่ OTP ซ้ำ.

---

## Phase 0 — Probe (read-only, headed, มนุษย์ login)

- **0.1** `scripts/streaming/probe_streaming.py` (ใหม่) — เปิด headed, login, แล้วดัมป์เป็น `docs/artifacts/streaming_probe_*.json`:
  1. URL/title/branding
  2. ฟอร์ม login (input id/name, ปุ่ม submit)
  3. order ticket: symbol box, side (Buy/Sell/Short/Cover), price input, volume input, ปุ่ม submit order
  4. ตาราง unmatched orders + ปุ่ม cancel + **ปุ่ม Modify/Change (ถ้ามี)**
  5. bid/offer depth (top 5 bid/offer ถ้า DOM มี)
  6. account selector (equity/margin), เลขบัญชี + type
  7. XHR/API endpoints ที่หน้าเรียก (เก็บไว้เผื่อใช้ REST path)
  - **Verify:** ไฟล์ artifact มีครบ 7 ข้อ + screenshot 3 รูป
  - **Done-when:** ทุก selector ในตาราง Phase 1 ถูกกรอกจาก artifact จริง (ไม่เดา)

- **0.2** ตัดสินใจ (จาก 0.1): reuse `click2win_driver.py` (ถ้า UI เดิม) vs เขียน `streaming_driver.py` ใหม่ (ถ้า UI ต่าง) — บันทึกผลการตัดสินใจลงใน comment ของการ์ดนี้

---

## Phase 1 — Driver (T1)

- **1.1** selectors refresh หรือ new module ตาม 0.2 — touch เฉพาะไฟล์ driver
- **1.2** `login()` username+password + session persist (`data/streaming_session.json`)
- **1.3** `execute_order(symbol, side, volume, price, pin)` — BUY/SELL/SHORT/COVER, Anti-DW symbol assert (คัดลอกจาก TradeMan fix `507da01`)
- **1.4** `cancel_order(order_no)`
- **1.5** nego: ถ้ามีปุ่ม Modify → **in-place amend** (D1-compliant, ไม่ต้อง cancel+replace); ถ้าไม่มี → cancel+replace ภายใต้ guardrails C1–C7 (ทีละออเดอร์, ห้าม amend ถ้า matched>0)
- **1.6** `get_market_bid_offer(symbol)` — จาก DOM/API ที่ probe พบ
- **Verify:** unit tests (FakePage) + `verify_changes.py`; full suite green

---

## Phase 2 — LINE routing (T1)

- **2.1** `_broker_open_orders()` → streaming `scrape_unmatched_orders()` (ตัด TradeMan)
- **2.2** quote source → streaming `get_market_bid_offer` (ตัด `_quote_via_gateway_browser` + QuickTrade hack ทั้งหมด)
- **2.3** `/nego stream` routing + amend mode (แทน KSS/TradeMan)
- **2.4** `/login stream` + `/status` → streaming health/auth
- **Verify:** `tests/test_line_cli_flow.py` + full suite; LINE smoke (dry-run)

---

## Phase 3 — Config (T1)

- **3.1** `TRADING_PLATFORM="CLICK2WIN"`/STREAMING, ตั้ง creds ใน `.env`, set `DRY_RUN_MODE=true` ระหว่างทำ
- **3.2** deprecate `KSS_AMEND_MODE` + QuickTrade quote path (ทำเครื่องหมาย, ยังไม่ลบ)

---

## Phase 4 — Dry-run (T2, มนุษย์, headed)

- **4.1** `execute_order` + `modify` แบบ DRY_RUN บน Streaming — expect `SIMULATED_SUCCESS` + log tier
- **4.2** `/nego stream` ผ่าน LINE แบบ DRY_RUN — expect plan เท่านั้น, ไม่แตะ broker

---

## Phase 5 — Live witness (T2, มนุษย์, headed)

- **5.1** SHORT + COVER BCPG (หุ้นถูก ~6.80, 100 หุ้น) — 1 cancel + 1 new order
- **5.2** verify ledger + `session_logs/` + audit row ก่อนปิดการ์ด

---

## Guardrails (คงเดิม)

- C1: ทีละออเดอร์เท่านั้น; C2: ห้าม amend ถ้า `matched_volume > 0`
- ห้าม retry อัตโนมัติหลัง error (กัน order ซ้ำ) — ตรวจ log/ledger ทีละขั้น
- Live mode ต้องมีมนุษย์อยู่ด้วยเสมอ; probe/dry-run ไม่รันคู่กับ witness
