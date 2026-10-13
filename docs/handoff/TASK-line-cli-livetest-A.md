# Live Test Report — LINE slash CLI (`0aecf8a`) · Round A (2026-10-13 คืน)

## สรุป
- ทดสอบผ่านแชท 1:1 กับ OA · 21:04–21:48 · MODE TEST · ตลาดปิด
- **ใช้ได้ดี:** router/parser, `/help`, `/status`, auth 1:1, `/login kss` + OTP relay แบบ 1:1, `sync` ไม่ login เอง (Invariant 7), `/nego` นอกเวลาถูกบล็อก (G2), `/logout kss`
- **ใช้ไม่ได้ / อันตราย:** ข้อมูล `sync` ของ KSS ผิดตาราง/บัญชี (RCA-6) · `/login lib` พัง (RCA-5) · การ์ดอ่านยาก/ข้อมูลไม่ครบ (RCA-2/3/4)
- **ห้ามทำ Round B (`/nego` ในเวลาตลาด) จนกว่าจะแก้ P0 ครบ**

## ลำดับความสำคัญสำหรับ loop ถัดไป
| P | งาน | อ้างอิง |
|---|---|---|
| P0 | ตรวจ DOM จริงของ TradeMan (watch-and-learn) → แก้ `scrape_portfolio` / `scrape_unmatched_orders` ให้เลือกบัญชี + refresh + ใช้ selector เฉพาะตาราง + ตรวจหัวคอลัมน์ | RCA-6 |
| P0 | `import os` ใน `pillar1_session.py` + ดัก exception ในงานนานแล้ว push ❌ | RCA-5 |
| P0 | เลิกใช้ค่าสำรอง 500,000 / 0.0 ในยอดเงิน KSS (Anti-Mock) | RCA-3 |
| P1 | การ์ด `/cash` แสดง CASH + MARGIN พร้อม Excess Equity | RCA-3 |
| P1 | ป้าย (S)/(B) + P/L กลับทิศสำหรับ Short (ตรวจซ้ำหลังแก้ RCA-6) | RCA-2 |
| P1 | เลย์เอาต์การ์ด `/orders` `/port` แบบ 2 บรรทัดต่อรายการ ตัวอักษรใหญ่ | RCA-4 |
| P1 | `/orders` จาก DB: กรอง broker + วันนี้ · ซ่อนปุ่ม `/nego` นอกเวลา | F-2 |
| P2 | เอาแถว kill-switch ออกจากการ์ด `/status` | B-1 |
| P2 | ใช้ 1:1 เท่านั้น: ปรับ auth gate + ข้อความ "ในกลุ่ม" | D-1 |
| P2 | `_send_reply` retry + fallback push + log ประเภท exception | RCA-1/F-3 |
| P2 | `/cash` จาก DB ไม่มีแหล่งข้อมูล · หลายคำสั่งในข้อความเดียว · audit ตอน nego ถูกปฏิเสธ · test lock แบบยิงพร้อมกัน | F-1/F-4/F-6/A11 |
| แยกการ์ด | Mask OTP ใน log | F-5 |
- หลังแก้ P0: ทดสอบ Round A ซ้ำเฉพาะ A8, A9 (LIB), A11 → ผ่านแล้วค่อยทำ Round B

## ผลราย step
| # | ผล | หลักฐาน / หมายเหตุ |
|---|---|---|
| A0 | ✅ PASS (ครั้งที่ 2) | gateway เริ่มหลัง mtime ของ source · `/health` 200 ทั้งที่ localhost และผ่าน `line.a14s.dev` · ครั้งแรกล้มเหลว — ดู H-1 |
| A1 `/help` | ✅ PASS | `POST /api/v1/webhook/line 200` · ผู้ใช้เห็นคู่มือ + ปุ่ม Quick Reply |
| A2 `/status` | ✅ PASS | การ์ดแสดงผลแล้ว · OTP relay `line_direct` 🟢 พร้อม · ผู้ใช้ขอเปลี่ยน UI → B-1 |
| A3 `/status` 1:1 | ✅ PASS | ทุก event ที่เข้ามาเป็น `source: user` (A1–A3 ล้วนมาจาก 1:1) |
| A4 `/port` | ✅ PASS | `positions` มี 0 แถว → "ℹ️ ยังไม่มี snapshot" ตรงกับที่คาด (ครั้งแรกผู้ใช้ส่ง 3 คำสั่งเป็นข้อความเดียว → F-4) |
| A4 `/cash kss` | ⚠️ FAIL → PASS เมื่อส่งซ้ำ | ครั้งแรกไม่มีอะไรตอบกลับ (`Reply error:` ข้อความว่าง) · ส่งซ้ำ 21:18 ได้ "ยังไม่มี snapshot เงินสด" → ยืนยัน RCA-1 ว่าสะดุดชั่วคราว |
| A4 `/orders lib` | ⚠️ PASS (มีข้อสังเกต) | แสดงการ์ด + ปุ่ม `/nego` แต่ข้อมูลมาจากแถว `HMPRO SHORT OPEN` ของเมื่อวาน ซึ่งไม่ได้แยก broker → F-2 |
| A5 parser | ✅ PASS | webhook 5 ครั้ง ไม่มี error · `/prot` แนะนำคำที่ใกล้เคียง · `c2w` ถูกปฏิเสธ · `/nego` มีปุ่มให้เลือก broker · `／` ใช้ได้ · `/พอร์ต` ใช้ได้ · การ์ด status ยังมีแถว kill-switch (ยืนยัน B-1) |
| A6 `/port kss sync` (ยังไม่ login) | ✅ PASS | ได้ "🔴 session หลุด — /login kss ก่อน" · log 21:21:49 ไม่มี login/OTP/browser launch (Invariant 7 ผ่าน) |
| A7 `/login kss` | ✅ PASS | ack 21:22:37 → cookie หมดอายุ (ย้ายไปเก็บแบบไม่ลบทิ้ง) → ขอ OTP ref NDVP 21:22:59 + push ไป userId → ผู้ใช้พิมพ์ OTP 21:23:15 → relay ส่งต่อให้ KRUNGSRI → SSO ผ่าน 21:23:39 → push ✅ · รวม ~63 วิ · relay แบบ 1:1 ใช้ได้จริง → F-5 |
| A8 `/login kss` (ซ้ำ) | ✅ PASS | "เชื่อมต่ออยู่แล้ว" ไม่มี SMS |
| A8 `/port kss sync` | ❌ FAIL (UX/ข้อมูล) | พอร์ตเป็นหุ้นที่ยืมมา Short แต่การ์ดไม่มีป้าย (S)/(B) → คนอ่านเข้าใจผิด → RCA-2 |
| A8 `/cash kss sync` | ❌ FAIL (ข้อมูล) | บัญชีเป็น Margin แต่ไม่มี Excess Equity → RCA-3 |
| A8 `/orders kss sync` | ❌ FAIL (UX) | ดึงข้อมูลได้ แต่ตัวอักษรเล็ก/ถูกตัดจนอ่านชื่อหุ้นไม่ออก → RCA-4 |
| A9 `/login lib` | ❌ FAIL (blocker) | ส่ง ack 21:35:21 แล้ว → `NameError: name 'os' is not defined` ใน `session_login_broker` → ผู้ใช้ไม่ได้รับข้อความอะไรต่อ · ไม่มี SMS → RCA-5 |
| A10 `/nego kss` (นอกเวลา) | ✅ PASS | ได้ "🌙 นอกเวลาที่อนุญาต" · log 21:39:30 มีแค่ reply ไม่มีการเรียก broker · ไม่มีแถว `LINE_CLI_*` ใน `session_logs` → F-6 |
| A11 lock | ❔ สรุปไม่ได้ | คำสั่งทั้ง 2 ตัวไม่ได้ทำงานซ้อนกันจริง: คำสั่งแรกจบใน 0.6 วิ (21:41:17.0→17.6) ก่อนคำสั่งที่ 2 จะมาถึง (21:41:19.0) → ทดสอบ lock ผ่านมือถือไม่ได้ ต้องใช้ test ที่ยิงพร้อมกัน · เจอบั๊กที่ร้ายแรงกว่าแทน → RCA-6 |
| A11 ข้อมูล `/port kss sync` | ❌ FAIL (critical) | ชื่อหุ้นไม่ตรงกับพอร์ตจริง (ผู้ใช้ยืนยัน) · ดึงได้ 3 ตัวทุกครั้งใช้เวลา ~40ms → RCA-6 |
| A12 | ⏭️ ข้าม | ผู้ใช้ตัดสินใจ: ไม่ทดสอบ PANIC/RESET คืนนี้ |
| A13 `/logout kss` + `/status` | ✅ PASS | `Playwright browser closed` 21:47:51 · `/status` แสดง KSS 🔴 |
| A14 | ⏭️ ข้าม | ไม่จำเป็น — A7 ยืนยันแล้วว่า OTP ไม่ถูก router `/` กลืน |

## เหตุขัดข้องจาก test harness (ไม่ใช่บั๊กของ CLI)
- **H-1** gateway ตาย ~21:00:06 ทันทีหลัง A0 → `/help` ครั้งแรกหายไป (LINE ได้ 502 จาก Cloudflare tunnel `line.a14s.dev` → `localhost:8000`)
  - Root cause: start ด้วย `nohup … &` ใน shell ของ `run_command` ที่ไม่ได้ตั้งเป็น daemon → โปรเซสลูกถูก kill พร้อม shell ตอนคำสั่งจบ
  - Fix: เปิดใหม่ด้วย `IsDaemon=true` · บทเรียน: จะ start gateway สำหรับ live test ต้องใช้ daemon/systemd เสมอ แล้วเช็คซ้ำผ่าน tunnel ไม่ใช่แค่ localhost
  - หมายเหตุ: webhook ของ LINE ชี้ไปที่ `https://line.a14s.dev/api/v1/webhook/line` (Cloudflare) **ไม่ใช่** Tailscale Funnel

## การตัดสินใจระหว่างทดสอบ
- **D-1 (21:11)** ใช้งาน CLI ผ่านแชท **1:1 กับ OA เท่านั้น ไม่ใช้กลุ่ม** → loop ถัดไป: ทบทวน auth gate (Decision A ยังอนุญาตกลุ่ม `LINE_GROUP_ID` อยู่) ตามที่ผู้ใช้ต้องการ + แก้ข้อความในการ์ด/เอกสารที่เขียนว่า "พิมพ์ OTP ในกลุ่ม" ให้เป็น "พิมพ์ในแชทนี้"
- **D-2 (21:38)** ยังไม่แก้ RCA-5 คืนนี้ → **ข้ามการทดสอบ LIB ทั้งหมด** (A9 ที่เหลือ, `/port lib sync`, `/orders lib sync`, `/logout lib`) · ไปทำ A10, A11, A13 ด้วย KSS · แก้ RCA-5 เป็นข้อแรกของ loop ถัดไป แล้วทดสอบ LIB ซ้ำ (เป็น gate ก่อน Round B `/nego lib`)

## Backlog สำหรับ loop ถัดไป (ผู้ใช้ขอ)
- **B-1** การ์ด `/status`: เอาแถว Kill-switch ออก · แสดงแถบแดง `⛔ KILL-SWITCH ACTIVE` เฉพาะตอน active
  - ยังคงไว้: คำสั่ง PANIC/RESET, guard G1 ใน `/nego`, การปฏิเสธ `/login` ตอน kill-switch active
  - ไฟล์: `app/services/line_cli/cards.py` (status builder) + test ใน `tests/test_line_cli_flow.py`

## Findings (บั๊ก/ช่องว่างในการออกแบบ)
- **F-1** `/cash` ที่ไม่มี `sync` ตอบว่า "ยังไม่มี snapshot" เสมอ — ไม่มีตารางเก็บเงินสดใน DB (`handlers.py` L513-515) → ไม่ตรงกับที่ออกแบบไว้ว่า "อ่าน DB เป็นค่าเริ่มต้น"
  - ทางเลือก: เก็บ snapshot ตอน `sync`/scheduler (ตาราง `account_snapshots`) หรือให้ `/cash` ดึงสดเสมอเมื่อ session ยัง alive
- **F-2** `_read_db_orders` (L366-394) ไม่กรอง broker และไม่กรองวันที่ → `/orders lib` แสดงออเดอร์ HMPRO ของเมื่อวาน (ไม่รู้ว่าเป็นของ broker ไหน) ภายใต้หัวข้อ "ออเดอร์วันนี้" + ปุ่ม `/nego` แม้ตลาดปิด
  - ทางแก้: เพิ่มคอลัมน์ `broker` ใน `orders`/`positions` (Cline เสนอไว้แล้ว) · กรอง `created_at >= วันนี้` · ซ่อนปุ่ม `/nego` นอกเวลา `LINE_NEGO_WINDOWS` (ตามสเปก §3.7)
- **F-3** `_send_reply` (`line_service.py` L1717-1724) log เฉพาะ `{e}` → timeout ของ httpx ได้ข้อความว่าง ไม่มีชื่อประเภท exception ไม่มี retry และไม่ fallback ไป push
- **F-4** ส่งหลายบรรทัดในข้อความเดียว → ระบบทำเฉพาะคำสั่งแรกโดยไม่แจ้งอะไร → เสนอ: รับหลายคำสั่งต่อบรรทัด (สูงสุด 5) หรือบอกว่า "ทำเฉพาะคำสั่งแรก"
- **F-5 (ความปลอดภัย · มีมาก่อน ไม่ใช่บั๊กของ CLI)** รหัส OTP เต็ม 6 หลักถูกเขียนลง log แบบไม่ปิดบัง: `otp_relay_registry` ("Received OTP 6-digits from LINE: …") และ `auth_driver` ("Received OTP '…' from line_chat") → ควร mask เหลือ `••••xx` เหมือนใน reply (อยู่นอกขอบเขต CLI — เปิดการ์ดแยก)
- **F-6** `/nego` ที่ถูกปฏิเสธทั้งคำสั่ง (G1 kill-switch / G2 นอกเวลา / G3 session หลุด) ไม่ถูกบันทึก audit — มีแค่ผลรายออเดอร์ → เสนอให้บันทึก `LINE_CLI_NEGO_REJECTED` พร้อมรหัส guard และ userId เพื่อย้อนดูได้ว่าใครสั่งตอนไหน

## RCA (step ที่ FAIL)
### RCA-1 — `/cash kss` ไม่มีข้อความตอบกลับ (21:14:12)
- อาการ: webhook เข้า 21:14:12 → `Reply error: ` (ข้อความว่าง) 21:14:17 · คำสั่งถัดไป (21:14:36) ตอบได้ปกติภายใน 0.3 วิ
- หลักฐาน: ห่างกัน 5.0 วิพอดี = `httpx.AsyncClient(timeout=5.0)` · ตัวจัดการ `/cash` ที่ไม่มี sync ไม่มี I/O อื่นเลย (L513-515)
- 5-Whys: ผู้ใช้ไม่เห็นข้อความ ← reply API ไม่ได้รับ ← httpx หมดเวลา 5 วิ (น่าจะเป็น connect/TLS ไป `api.line.me` สะดุดชั่วคราว) ← ไม่มี retry/fallback ← `_send_reply` ถูกออกแบบให้ยิงครั้งเดียวแล้วเงียบ
- Root cause: เครือข่ายไป LINE API สะดุดชั่วคราว (ไม่ใช่ logic ของ CLI) + ช่องว่างเรื่อง resilience/observability ใน `_send_reply` (F-3) — จะยืนยันโดยส่งซ้ำ
- ทางแก้ที่เสนอ: log `type(e).__name__` + retry 1 ครั้ง (backoff 0.5s) · ถ้า reply ล้มเหลวให้ fallback ไป `push_message` ที่ source เดิม · test: mock httpx timeout → assert มี retry + push

### RCA-2 — `/port kss sync` ไม่แยกหุ้น Short (ยืม SBL) กับหุ้นที่ถืออยู่
- อาการ: หุ้น Short แสดงเหมือนหุ้นที่ถือปกติ · %P/L จึงกลับทิศในสายตาคนอ่าน
- หลักฐาน: driver ส่ง `position_type` มาให้แล้ว (`trademan_driver.py` L503) แต่ `_normalise_holdings` (`handlers.py` L397-406) เก็บไว้แค่ symbol/volume/cost/last/pnl_pct → field นี้หายไป · `pnl_pct = (last-cost)/cost` คิดแบบหุ้นที่ถือเสมอ
- 5-Whys: ป้ายไม่มี ← การ์ดไม่ได้รับ `position_type` ← ตัว normalise ทิ้งไป ← สเปก §3.5 เขียนแค่ `AP⇣S` เป็นตัวอย่าง ไม่ได้เขียนเป็นกฎ ← test ใช้ fixture ที่มีแต่หุ้น LONG
- Root cause: ตัว normalise ทิ้ง field `position_type` + สเปก/test ไม่ได้บังคับเคส SHORT
- ทางแก้: เก็บ `position_type` ไว้ → แสดง `PTT (B)` / `AP (S)` · หุ้น SHORT คิด P/L กลับทิศ `(cost-last)/cost` · แยกยอดรวม Long/Short · test fixture ที่มีหุ้น SHORT

### RCA-3 — `/cash kss sync` ไม่แสดง Excess Equity ของบัญชี Margin
- หลักฐาน: handler เลือกบัญชีจาก `is_active` (`handlers.py` L467) · ค่าเริ่มต้น `krungsri_active = CASH` (`schemas/account.py` L106) → ได้ dict ของบัญชี CASH (`pillar2_portfolio.py` L391-399) ซึ่ง**ไม่มี key `excess_equity`** → แถว EE จึงหาย (L473)
- Root cause: การ์ดแสดงเฉพาะ "บัญชีที่ active" ซึ่งค่าเริ่มต้นเป็น CASH ทั้งที่ผู้ใช้ใช้ MARGIN (SBL) เป็นหลัก
- ความเสี่ยงที่เกี่ยวข้อง (Anti-Mock):
  - `pillar2_portfolio.py` L395-406 ใช้ `balances.get(..., 500_000.0)` → ถ้าไม่มี key จะได้ตัวเลขปลอม 500,000
  - `scrape_account_summary` (`trademan_driver.py` L1986-2008) ตั้งค่าเริ่มต้นเป็น 0.0 และ selector เป็นการเดา (`td:has-text('EE') + td`) → ถ้าหาไม่เจอจะขึ้น 0.00 เหมือนเป็นค่าจริง
- ทางแก้: แสดงทั้ง 2 บัญชีของ KSS (CASH + MARGIN พร้อม EE) · เปลี่ยนค่าสำรองเป็น `None` แล้วให้การ์ดแสดง "อ่านไม่ได้" · ตรวจ DOM จริงของ TradeMan แล้วเขียน selector ใหม่ (watch-and-learn)

### RCA-4 — การ์ด `/orders` ตัวอักษรเล็ก อ่านชื่อหุ้นไม่ออก
- หลักฐาน: `_cell` ใช้ `size: xs` และไม่ wrap (`cards.py` L62) · หนึ่งแถวมี 3 คอลัมน์ คอลัมน์แรก (flex 3/10) บรรจุ emoji + side + symbol (L257) → LINE ตัดด้วย "…" จนชื่อหุ้นหาย · คอลัมน์ท้ายใส่ status ดิบที่ยาวจาก broker
- Root cause: เลย์เอาต์แบบตารางที่ออกแบบมาสำหรับจอกว้าง ไม่ได้เทสบนมือถือจริง (unit test ตรวจแค่ว่า JSON ถูกต้อง)
- ทางแก้: 1 ออเดอร์ = 2 บรรทัด (บรรทัดบน `SYMBOL` ตัวหนา size `md` + side badge สี · บรรทัดล่าง จำนวน@ราคา + สถานะสั้น) · bubble `mega` · ใช้แบบเดียวกันกับการ์ด `/port` ด้วย

### RCA-5 — `/login lib` ค้าง ไม่มีข้อความตอบผล (21:35:20)
- อาการ: ส่ง ack แล้วเงียบ ไม่มี SMS ไม่มี ✅/❌ ตามมา
- หลักฐาน: traceback `pillar1_session.py` L139 `os.path.exists(liberator_driver.session_path)` → `NameError: name 'os' is not defined` · import ที่หัวไฟล์ (L10-18) ไม่มี `import os` · `git log` ของไฟล์มีแค่ baseline `f87cf34` (commit `0aecf8a` ไม่ได้แก้ไฟล์นี้)
- 5-Whys:
  1. ผู้ใช้ไม่ได้ผล ← exception หลุดออกจาก `_handle_login` โดยไม่มี try/except แล้ว push ❌
  2. exception เกิด ← สาย LIBERATOR ใน `session_login_broker` ใช้ `os` ที่ไม่ได้ import (บั๊กที่มีมาตั้งแต่ baseline)
  3. ไม่มีใครเจอ ← ก่อนหน้านี้ LIB login เข้าทางอื่น (`daily_readiness` / `start_homelab`) ไม่ผ่าน pillar1
  4. test ไม่จับ ← `test_line_cli_flow.py` mock `session_login_broker` ทั้งตัว → โค้ดจริงสาย LIB ไม่เคยถูกรัน
- Root cause: (a) บั๊กที่มีมาก่อนคือลืม `import os` ใน `pillar1_session.py` · (b) CLI ไม่มีตัวดัก exception หลังส่ง ack → เงียบหายแทนที่จะแจ้งความล้มเหลวตามจริง (สเปก §3.3 ให้ส่ง `❌ … เข้าระบบไม่สำเร็จ: <error>` แต่ไม่ได้ implement ตัวดัก exception)
- ทางแก้: เพิ่ม `import os` · ห่อ handler งานนาน (login/sync/nego) ด้วย try/except → push `❌ <BROKER>: <ExceptionType>: <msg>` · test ที่รัน `session_login_broker("LIBERATOR")` จริงโดย mock แค่ driver

### RCA-6 — `/port kss sync` แสดงหุ้นที่ไม่ใช่พอร์ตจริง (CRITICAL · Anti-Mock)
- อาการ: การ์ดขึ้นป้าย `🟢 live` แต่ชื่อหุ้นไม่ตรงกับพอร์ตจริง → ผู้ใช้อาจตัดสินใจจากข้อมูลผิด
- หลักฐาน:
  - log: `Scraped 3 holdings` หลัง reply แค่ ~40ms ทุกครั้ง (21:41:17, :19, :32, :33, :53) → ไม่มีการ navigate/reload
  - `trademan_driver.scrape_portfolio` (L437-440): navigate เฉพาะตอน URL ไม่มีคำว่า "Portfolio" → หลัง login หน้าเว็บอยู่ที่ `/Portfolio` อยู่แล้ว จึงอ่าน DOM เดิมซ้ำตลอด
  - L448-453: selector `table tbody tr` + กรองแค่ `td >= 8` → กวาดทุกตารางในหน้า (อาจเป็นตารางออเดอร์/SBL/ตลาด) ไม่เจาะตาราง portfolio
  - ไม่มีการเลือกบัญชีใน `#dropDownAccountPort` → อ่านบัญชีที่เปิดค้างอยู่ (ค่าเริ่มต้น CASH ตาม RCA-3) ไม่ใช่ MARGIN ที่มีหุ้น SBL
  - handler ติดป้าย `live=True` เสมอ โดยไม่ตรวจว่าได้ข้อมูลจากบัญชีไหน
- 5-Whys: หุ้นผิด ← อ่านผิดตารางหรือผิดบัญชี ← selector กว้างเกินและไม่เลือกบัญชี ← scraper เดิมเขียนไว้ใช้กับหน้าที่เปิดใหม่ทุกครั้ง (flow ตอนเช้า) ← CLI เอามาเรียกซ้ำบน session ที่เปิดค้างไว้ โดยไม่มี test บน DOM จริง
- Root cause (สมมติฐาน — ต้องตรวจ DOM จริงก่อนแก้): scraper ของ TradeMan ไม่เจาะตาราง portfolio ไม่เลือกบัญชี และไม่ refresh · คำติชมของผู้ใช้ตอน A8 ("หุ้นยืม Short") อาจมาจากตารางที่ผิดตัวเดียวกัน → RCA-2 ต้องตรวจซ้ำหลังแก้ข้อนี้
- ทางแก้:
  - (1) ตรวจ DOM จริงแบบ watch-and-learn: หา container/id ของตาราง portfolio และดูว่า dropdown เลือกบัญชีไหนอยู่
  - (2) scraper: เลือกบัญชีตาม `account_type` ที่ส่งมา → reload/refresh → รอให้ตารางโหลดเสร็จ → ใช้ selector เฉพาะตาราง → ตรวจหัวคอลัมน์ก่อน parse (ถ้าไม่ตรง = fail ไม่ใช่ส่งข้อมูลผิด)
  - (3) การ์ดแสดงเลขบัญชี + ประเภท (CASH/MARGIN) ที่อ่านมาจริงจาก DOM
  - (4) **ก่อนแก้เสร็จ ห้ามใช้ `/port kss sync` เป็นข้อมูลประกอบการตัดสินใจ** · ต้องตรวจ `/orders kss sync` และ `/nego` ด้วย เพราะอาจใช้ selector กว้างแบบเดียวกัน (`scrape_unmatched_orders` L932) — เป็น gate ก่อน Round B

---

## Round C — re-test commit `5f81cc5` (2026-10-13 22:20–22:32)

| ขั้น | คำสั่ง | ผล | หมายเหตุ |
|---|---|---|---|
| C0 | restart gateway | ✅ PASS | เริ่ม 22:20:48 หลัง mtime ของ source; `/health` 200 |
| C1 | `/login lib` + OTP | ✅ PASS | ไม่มี NameError; relay ส่ง OTP ไปที่ LIBERATOR ถูกตัว → ✅ → **CLI-RCA-005 FIXED** |
| C2 | `/port lib sync` | ✅ PASS | ชื่อหุ้นตรงกับแอป |
| C2 | `/orders lib sync` | ✅ PASS | |
| C2 | `/cash lib sync` | ❌ FAIL | แสดงข้อมูลของ Click2Win → **CLI-RCA-007 (Critical)** |
| C3 | `/login kss` | ❌ FAIL | ตอบ ✅ ทั้งที่ session หมดอายุ แล้วเด้งไป `/SignIn` → **CLI-RCA-008 (Critical)** |
| C3 | `/cash kss sync` | ❌ FAIL | ได้ 0.00 ทุกช่อง แสดงเป็น 🟢 live (อ่านจากหน้า SignIn) → **CLI-RCA-009 (Critical)**; CLI-RCA-003 แก้ได้ครึ่งเดียว (ไม่มี 500k แล้ว แต่ยังมี 0.0) |
| C4 | `/logout kss`, `/logout lib` | ✅ PASS | ปิด browser แล้ว ⚠️ F-7: log ปิด browser มีครั้งเดียว อาจใช้ Chromium ร่วมกัน → ต้องตรวจเรื่องแยกโบรกเกอร์ |

## Round D — probe DOM ของ TradeMan แบบอ่านอย่างเดียว (22:33–22:52)
- runbook: `learned_workflows/krungsri/trademan_portfolio_dom.md`
- หัวตารางกับข้อมูลอยู่คนละ `<table>`; selector เดิม `table tbody tr` td≥8 จับได้ 15 แถวหุ้น + 1 แถวยอดรวม
- dropdown เปลี่ยนบัญชีใช้ Tailwind แล้ว: `.v-list-item` **ใช้ไม่ได้แล้ว** (ที่ driver L366 ด้วย) → ตัวที่ถูกคือ `#dropDownAccountPort div.absolute span:text-is("<acc>")`
- popup What's new กลับมาบังการคลิก
- ตาราง View Order: คอลัมน์ Symbol = คอลัมน์ที่ 3
- ยังขาด: โครงสร้าง DOM ของ holdings บัญชี CASH, คอลัมน์บอกฝั่ง LONG/SHORT, selector ของสรุปบัญชี (cash/EE)
- ต้องใช้ OTP เพิ่ม 2 ครั้ง เพราะ probe รอบแรกหยุดกลางทาง → รอบหน้าให้ probe บันทึก session ไว้ใน scratch แล้วใช้ซ้ำ (ผู้ใช้ไม่อยากใช้ OTP บ่อย)

## ลำดับความสำคัญที่อัปเดต
- P0: RCA-006 (scraper + เลือกบัญชี, ใช้ runbook ด้านบน), RCA-007 (route LIB cash), RCA-008 (ตรวจ session ผิดเป็นผ่าน), RCA-009 (เลิกคืน 0.0 เป็นค่าจริง)
- P1: RCA-002 (S)/(B), RCA-003 EE, RCA-004 การ์ด orders, F-5 OTP ใน log, F-7 browser ใช้ร่วมกัน
- Round B (`/nego`) ยังต้องรอ P0 ให้เสร็จทั้งหมด

---

## Round R — live re-test after P0 fix (2026-10-14 04:30–05:01)
| ขั้น | คำสั่ง | ผล | หมายเหตุ |
|---|---|---|---|
| R0 | restart gateway | ✅ | 04:30:40 > mtime 04:16; health 200 |
| R1 | `/login kss` | ✅ | ไม่มีไฟล์ session → ขอ OTP ผ่าน LINE → SSO → /Portfolio. เส้นเช็ก session เก่า (RCA-008) ไม่ได้ทดสอบ live. F-8: log มี SSO JWT |
| R2 | `/port kss sync` | ⚠️ ข้อมูล ✅ / แสดงผล ❌ | ยืนยันบัญชี 3024959, 15 แถว (**RCA-006 FIXED**). ไม่มี (S); P/L รวมกลับเครื่องหมายเทียบกับแอป (**RCA-002 → High**); แสดงแค่ 10/15 แถว (**RCA-010**) |
| R3 | `/cash kss sync` | ❌ | ตัวเลขเดียวคือ Line Available ของ MARGIN แต่ขึ้นเป็น CASH cash+buying power; ไม่มี EE (**RCA-011**). ไม่เจอ 0.0 แล้ว (RCA-009 OK) |
| R4 | `/login lib` + `/cash lib sync` | ✅ | ใช้ session เดิม; ข้อมูลเป็นของ Liberator (**RCA-007 FIXED**); หัวการ์ดขึ้น enum ดิบ |
| R5 | `/logout kss`, `/logout lib` | ✅ | |
- F-9 ปิด (ผู้ใช้เปิดแท็บ Settrade streaming เอง)
- ถัดไป: `TASK-cli-p1-display-and-redaction.md` (Cline); probe Account Info + side marker (Antigravity, ช่วงตลาดเปิด, ใช้ session จาก scratch) → handoff RCA-011
