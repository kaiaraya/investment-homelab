# TASK-pillar2-order-ledger: Pillar 2 — Order Ledger (Matched vs Unmatched)

- Created: 2026-10-07 by Cline
- Broker: Krungsri (TradeMan) + Liberator (multi-broker)
- Status: **DONE (U1–U5, U7)** — U6: Liberator live PASS ✅ · Krungsri login/switch/balance PASS ✅ แต่ Order Ledger parser ยังต้องแก้จาก DOM จริง (ดู Follow-up 2026-10-07 late)

## Context
ผู้ใช้ขอความสามารถใหม่ใน Pillar 2: **ดูรายการ Order ที่ส่งไปแล้วให้ Broker และแยกให้เห็นว่าอันไหน Matched / Unmatched**
ต่างจาก `current_open_orders` ที่คืนเฉพาะ unmatched (ไว้ให้ Pillar 6 ต่อราคา) ตัวใหม่นี้อ่านสถานะครบรวม terminal rows.

ขอบเขตที่ผู้ใช้ยืนยัน: **ดึงสดจาก Krungsri (TradeMan) + Liberator เท่านั้น** (Click2Win ยังไม่ทำ).

## Verified facts (ก่อนเริ่ม)
- Liberator: `driver.scrape_portfolio()["orders"]` มี field ครบ `order_no,time,symbol,side,price,volume,matched,balance,cancelled,status`
  (driver.py L489-511) → matched/unmatched แยกได้ทันทีจาก `matched`/`balance`.
- Krungsri: `trademan_driver.scrape_unmatched_orders()` (L711) สแกน Order Status tab แล้ว **กรองเหลือแต่ Open**
  (ตัด `M`=Matched ทิ้ง) → ต้องมีเมธอดใหม่ที่เก็บทุกแถว.
- Routing: Pillar 2 `current_open_orders` route KRUNGSRI→`trademan_driver`, LIBERATOR→`liberator_plugin` แล้ว.

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/brokers/liberator/plugin.py` (เพิ่ม `get_all_orders`)
- `app/browser/trademan_driver.py` (เพิ่ม `scrape_all_orders`)
- `app/mcp/pillars/pillar2_portfolio.py` (เพิ่ม `_classify_order_category` + tool `current_orders` + register)
- `app/mcp/mcp_server.py` (เพิ่ม agent MCP tool `scrape_orders`)
- `tests/test_pillar2_order_ledger.py` (ใหม่)
- `learned_workflows/krungsri/trademan_order_submit.md`, `learned_workflows/liberator/liberator_portfolio.md` (อัปเดต runbook)

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|-------------|------------------|--------|--------|
| U1 | Liberator `get_all_orders()`: normalize + คงทุกแถว (ไม่กรอง terminal) | คืน canonical rows ครบ matched/open/cancelled | `pytest tests/test_pillar2_order_ledger.py -q` | ✅ |
| U2 | Krungsri `trademan_driver.scrape_all_orders()`: สแกน Order Status tab เก็บทุกแถว + status code M/O/C | คืนทุกแถวพร้อม status + volumes | pytest (mock DOM) | ✅ |
| U3 | Pillar 2 `_classify_order_category()` (single source of truth: MATCHED/PARTIALLY_MATCHED/UNMATCHED/CANCELLED/REJECTED/UNKNOWN) | mapping ถูกต้องทุก combo | unit test matrix | ✅ |
| U4 | Pillar 2 `current_orders(platform, account_type, include_closed)` + counts + register | route KRUNGSRI/LIBERATOR, คืน counts | pytest | ✅ |
| U5 | Agent MCP `scrape_orders` tool (mcp_server.py) → เรียก `current_orders` | tool ลงทะเบียน + คืน ledger text | `python -c "import app.mcp.mcp_server"` + เรียกจริง | ✅ |
| U6 | Live E2E บนเซสชันจริง (Krungsri + Liberator) | หลักฐานจริง + human confirm | screenshot/log | 🟡 Liberator PASS ✅ · Krungsri login/switch/balance PASS ✅ · Order parser ✗ (แก้จาก DOM จริง) |
| U8 | Fix `verify_saved_session()` non-destructive (Invariant 8 / `KSS-RCA-013`) | transient timeout ไม่ลบ session; validation miss → quarantine | `pytest tests/test_auth_session_nondestructive.py -q` | ✅ (ขยาย scope โดยผู้ใช้) |
| U7 | อัปเดต runbook 2 ไฟล์ (Zero-Contradiction) | ไม่มีขั้นตอนขัดกับโค้ด | diff review | ✅ |

## Verification convention
- Unit: `.venv/bin/python -m pytest tests/test_pillar2_order_ledger.py -q`
- Full targeted: `.venv/bin/python -m pytest tests/test_pillar2_portfolio_liberator.py tests/test_remote_mcp.py -q`

## Cline Report

### Files changed
- `app/brokers/liberator/plugin.py` — เพิ่ม `LiberatorBrokerPlugin.get_all_orders()` (normalize ทุกแถว, คง terminal rows)
- `app/browser/trademan_driver.py` — เพิ่ม `TradeManDriver.scrape_all_orders()` (สแกน Order Status tab เก็บทุกแถว + status token M/O/C)
- `app/mcp/pillars/pillar2_portfolio.py` — เพิ่ม `_classify_order_category()` + tool `current_orders()` + register ใน `register_portfolio_pillar`
- `app/mcp/mcp_server.py` — เพิ่ม agent MCP tool `scrape_orders` (TOOLS schema + `handle_tool_call` branch)
- `tests/test_pillar2_order_ledger.py` — **ใหม่** (5 tests: classifier matrix + Liberator/Krungsri routing + include_closed + Click2Win notice)
- `learned_workflows/krungsri/trademan_order_submit.md` — เพิ่ม §5 Order Ledger (Zero-Contradiction note: unmatched scraper ตัด Matched ทิ้ง)
- `learned_workflows/liberator/liberator_portfolio.md` — เพิ่ม §7 Order Ledger (get_orders/get_open_orders/get_all_orders)
- `docs/handoff/TASK-pillar2-order-ledger.md` — ไฟล์นี้
- `app/browser/auth_driver.py` — `verify_saved_session()` non-destructive + `_quarantine_session_file()` (Invariant 8 / `KSS-RCA-013`)
- `tests/test_auth_session_nondestructive.py` — **ใหม่** (3 tests: transient timeout คงไฟล์ / validation miss → quarantine / ไม่มีไฟล์ → False)
- `rca/krungsri/rca_krungsri_trademan.md` — เพิ่ม `KSS-RCA-013` (registry + deep dive)

### Summary
เพิ่ม **Pillar 2 Order Ledger** — ดูรายการ Order ที่ส่งไปแล้วให้ Broker ครบทุกสถานะ พร้อมแยก
`MATCHED / PARTIALLY_MATCHED / UNMATCHED / CANCELLED / REJECTED / UNKNOWN`.
- `current_open_orders()` เดิม **คงไว้ไม่แตะ** (Pillar 6 ใช้ต่อราคา) → ไม่มี breaking change.
- จำแนกสถานะใช้ `_classify_order_category()` เป็น single source of truth (volume-truth ก่อน แล้วค่อย raw status).
- Routing: KRUNGSRI→`trademan_driver.scrape_all_orders()`, LIBERATOR→`liberator_plugin.get_all_orders()`.
- เรียกได้ 2 ทาง: Pillar-2 MCP tool `current_orders()` (SSE gateway) และ agent MCP `scrape_orders` (playwright-homelab).

### Tests run + results
- `pytest tests/test_pillar2_order_ledger.py tests/test_pillar2_portfolio_liberator.py tests/test_remote_mcp.py tests/test_escalation_and_annealing.py tests/test_account_capability_liberator.py -q` → **29 passed**
- `python -c "from app.mcp.mcp_server import TOOLS; ..."` → `scrape_orders in TOOLS: True`
- **Live verification (zero-risk, no OTP):** `current_orders(platform="LIBERATOR")` → คืน order จริง 1 รายการ
  `THAI SELL 3400 @ ฿5.75, matched 3400/3400, balance 0` → category `MATCHED` ✅
- `current_orders(platform="KRUNGSRI")` → `total: 0` (ไม่มี live TradeMan page; คืน `[]` ปลอดภัย ไม่ trigger 2FA OTP)

### Open questions / ไม่แน่ใจ
- **U6 Krungsri live** ต้องมี TradeMan session ที่ login อยู่ (live page) — ยังไม่ได้รัน E2E จริงเพราะปัจจุบันไม่มี live page
  (การ login ใหม่จะ trigger SMS OTP → ไม่ทำเองโดยไม่มีการยืนยันจากผู้ใช้ ตาม Invariant 9).
- `scrape_all_orders()` ของ Krungsri แยก volume/matched/balance ด้วย heuristic จากข้อความแถว (เหมือน `scrape_unmatched_orders` เดิม);
  ค่า `status` (M/O/C) เชื่อถือได้ แต่ตัวเลข matched/balance อาจต้องปรับเมื่อเห็น DOM จริง (จะยืนยันตอน live E2E).
- FastAPI server (port 8000) ตอนนี้ **DOWN** ตาม preflight — ถ้าจะเรียก `current_orders` ผ่าน SSE gateway ต้อง start uvicorn ก่อน.

---

## Follow-up 2026-10-07 (late) — Krungsri live E2E (U6) + Invariant 8 fix (U8)

ผู้ใช้สั่ง "login ให้เอง" → รัน U6 (Krungsri live) จริงบนเซสชันที่ผู้ใช้ยืนยัน SMS OTP (Invariant 9 ผ่าน: D-Bus `isReachable=true`).

### U6 Krungsri live — หลักฐานจริง
- **Login:** fresh login (session เดิมหมดอายุ → เด้ง `/SignIn`), OTP `807258` ป้อนผ่าน browser DOM (`browser_dom_manual`) → SSO → `trademan.in.th/Portfolio` (`#dropDownAccountPort` visible) → `AUTHENTICATED` ✅
- **Account switch:** CASH `3024952` ✅ · MARGIN `3024959` ✅
- **Balances:** MARGIN EE ฿38,758.01 · Cash ฿77,516.02 · Total ฿281,133.51; CASH = 0.00 ✅
- **Order Ledger (`current_orders`):** ❌ parser ผิด — MARGIN คืน 10 แถวแต่ `symbol=UNKNOWN`, `status_raw`=เวลา (`16:29:55`), `broker_order_no=ORD-x`; CASH คืน 1 แถวขยะ (`status_raw=0.00`)
  - **RCA:** `scrape_all_orders()` ใช้ `page.query_selector_all("table tbody tr")` กว้างเกินไป (ไม่ isolate ตาราง Order Status) → ปนตารางอื่น = bug คลาสเดียวกับ LIB-RCA (Liberator แก้ด้วย table-header isolation แล้ว)
  - **ต้องแก้:** capture DOM จริงของแท็บ 'View Order' (table thead) → isolate table ที่ถูกต้อง + map คอลัมน์ให้ตรง

### U8 Invariant 8 fix (ขยาย scope โดยผู้ใช้) — `KSS-RCA-013`
- **Incident:** ระหว่าง diagnostic DOM เกิด `Page.goto: Timeout 12000ms` → `verify_saved_session()` **ลบ `data/session_state.json` ที่ยังใช้ได้ทิ้ง** (Zero-OTP session หาย → ต้อง login ใหม่)
- **Root cause:** `verify_saved_session()` มี `os.remove(SESSION_STATE_PATH)` 2 จุด (except=timeout + else=selector miss) โดยไม่มีหลักฐานว่าเซสชันหมดอายุจริง
- **Fix:** except branch → ไม่แตะไฟล์เลย; else branch → `_quarantine_session_file()` rename เป็น `*.stale.bak.json` (non-destructive); ไม่ `clear_cookies()` ใน verify path
- **Tests:** `pytest tests/test_auth_session_nondestructive.py tests/test_action_center.py tests/test_phase2_auto_reconnect.py tests/test_krungsri_session_health.py tests/test_session_drop_detection.py -q` → **31 passed**; `pytest tests/test_pillar2_order_ledger.py tests/test_remote_mcp.py tests/test_pillar2_portfolio_liberator.py -q` → **18 passed**

### Open (ยังต้องทำ)
- **U6:** แก้ `scrape_all_orders()` จาก DOM จริง (ต้อง login Krungsri อีกครั้ง = OTP) — ผู้ใช้เลือก "ยังไม่ยิง OTP" รอบนี้
- ยืนยันว่า orders ที่ MARGIN เห็น (10 แถว) เป็นของจริงหรือ placeholder หลังแก้ parser
