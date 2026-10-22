# TASK-loop1-b0a — Order-Entry & Balance DOM Contract (KSS Streaming + Liberator)

**Status:** PROBE_DONE (KSS ✅ · Liberator ✅ · account_no รอ user)
**Date:** 2026-10-21 07:1x (+07)
**Method:** Headed Chrome CDP read-only (port 9333 = kss, 9334 = liberator) — human ดูหน้าจอ + พิมพ์ OTP
**Output of:** `scripts/broker_probe.py` + one-off CDP scripts (dump/locate)

---

## DOM / API Contract — KSS Settrade Streaming (port 9333)

### 1. Login (Krungsri SSO → Streaming)
- `session_daemon.py kss` → `KRUNGSRI_LOGIN_URL` → fill `#login_username` / `#login_password` → submit
- → **`/th/login/OTP_SMS.aspx`** (human พิมพ์ SMS OTP 6 หลัก) → member portal (`/th/member/CreditBalance_Announcement.aspx`)
- → open `SSO_STREAMING_URL` (Put_SSO_Settrade.aspx?Page=streaming) → lands **`wme2.settrade.com/realtime/streaming7/StreamingPage.jsp`**
- Tabs หลัง login: `[0]` Streaming · `[1]` member portal · `[2]` SBL (`/sblweb/MainSBL.aspx`)

### 2. Account switch (จำเป็น — default เปิดมาที่ Cash ไม่ใช่ Margin)
- **Default หลัง login = `3024952 (Equity)` = Cash** → Short/Cover radio **ไม่ render** บน Cash
- Switch: click `div.position-relative.cursor-pointer` (span แสดง "3024952 (Equity)") → dropdown `ul.p-0.m-0` → click `li:has-text("3024959")`
- หลังสลับ: header แสดง `3024959 (Equity)` · `A/C Type : Credit Balance` (ยืนยันแล้ว probe)

### 3. Order Ticket — side radio group `name="placeOrderRadio"`
| Side | Selector | value |
|---|---|---|
| Buy | `#equity-place-order-buy-radio-button` | `B` |
| Sell | `#equity-place-order-sell-radio-button` | `S` |
| Short | `#equity-place-order-short-radio-button` | `H` |
| Cover | `#equity-place-order-cover-radio-button` | `C` |

> `H` / `C` ตรงกับ side letter ของ QuickTrade พอดี (ยืนยัน consistency)

### 4. Order Ticket — fields
| Field | Selector |
|---|---|
| Symbol | `input[placeholder="Symbol"]` (maxlength 20) |
| Volume | `input[name="equity-place-order-vol"]` |
| Price | `input[name="price-input"]` |
| PIN | `#pin` (มี option "Click to save PIN") |
| Submit | `button:has-text("Submit")` |

### 5. Balance — header bar `div.display-flex.justify-content-center` (Margin 3024959)
- Label `<p>` + value `<p>` pairs — scrape โดย match label text:
  - `A/C Type :` → `Credit Balance` (margin) / `Cash` (cash)
  - `Credit Limit :` → [REDACTED — ตัวเลขจริงไม่ลงไฟล์]
  - `Line Available :` → [REDACTED]
  - `EE :` → [REDACTED]
- Map ลง `broker_accounts`: `account_type` (CASH_BALANCE/CREDIT_BALANCE), `credit_limit`, `line_available`, `excess_equity`

### 6. PIN source — ✅ KRUNGSRI_PIN (user ยืนยัน 2026-10-21)
- PIN field = `#pin` · key = **`KRUNGSRI_PIN`** (ตัวเดียวกับ Krungsri/TradeMan)
- ✅ `KRUNGSRI_PIN` มีใน `.env` แล้ว (user ยืนยัน 2026-10-21)

---

## DOM / API Contract — Liberator WebTrade (port 9334)

> Selectors มาจาก driver ที่ live-proven อยู่แล้ว (`app/brokers/liberator/driver.py`) — CDP probe ยืนยันหน้าโหลด (tabs: Market + Portfolio)

### 1. Login
- **Cookie resume** จาก `data/liberator_session.json` **ได้** (ยืนยัน probe — ไม่ต้อง OTP ซ้ำ) · fresh login = user/pass + SMS OTP ผ่าน LINE relay (driver จัดการ)

### 2. Tabs (Trade URL เด้งไป Market)
- `[0]` Market (`/Market`) · `[1]` Portfolio (`/Portfolio`) · order ticket อยู่บน **footer widget** ไม่ใช่หน้า `/Trade` แยก

### 3. Order Ticket (footer — BUY/SELL เท่านั้น, cash)
| Field | Selector |
|---|---|
| Side | `:text('Buy')` / `:text('Sell')` toggle |
| Symbol | `#SearchSymbolList-setBuySellFooter` |
| Volume | `#volume` |
| Price | `#price` |
| PIN | `#pin` (6 หลัก) |
| Submit | `#buttonSubmit` |
| Confirm modal | `button:has-text('Confirm')` / `button:has-text('ยืนยัน')` |
| PIN source | **`LIBERATOR_PIN`** (config, 6 หลัก) |

### 4. Balance (Portfolio page — label regex)
- `Line Available:` · `Cash Balance:` · `Credit Limit:` (scrape โดย match label text — driver `scrape_portfolio()`)
- Holdings table: thead มี `symbol` + `in port` · Orders table: `#OrderTableList`

### 5. account_no — ✅ `7055938` (ยืนยันจาก session live 2026-10-21)
- Token scan หน้า Portfolio เจอ `7055938` (และ `70559382` = เลขบัญชี + หลักถัดไปติดกัน — textContent ไม่มี whitespace ระหว่าง cell)
- "Manage Account" menu → `alternative.liberator.co.th/eservice/manageaccount`
- → เพิ่ม `LIBERATOR_ACCOUNT_NO=7055938` ใน `.env` + `config.py`

---

## Probe artifacts
- `data/probes/probe_streaming_20261021_071637.json` — order ticket (side + submit)
- `data/probes/probe_streaming_20261021_071639.json` — inputs + PIN
- `data/probes/probe_streaming_20261021_071654.json` — account selector
- `data/probes/probe_streaming_20261021_071713.json` — balance / A/C type
