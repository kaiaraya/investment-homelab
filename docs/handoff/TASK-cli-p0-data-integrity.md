# TASK-cli-p0-data-integrity: แก้ข้อมูลผิดใน LINE CLI (RCA-006/007/008/009)

- Created: 2026-10-13 by Antigravity
- Broker: KSS (TradeMan) + LIB (Liberator). **ห้ามเอาโค้ดหรือ selector ของโบรกเกอร์หนึ่งไปใช้กับอีกโบรกเกอร์**
- Priority: P0. Round B (`/nego`) เริ่มไม่ได้จนกว่างานนี้จะเสร็จ
- Status: TODO

## Context (Antigravity เขียน)
Live test รอบ C/D (2026-10-13) พบว่า `sync` ตอบข้อมูลผิดแต่ขึ้นป้าย 🟢 live ซึ่งผิด Anti-Mock และกฎแยกโบรกเกอร์ มี 4 เรื่อง:
- **RCA-006**: `/port kss sync` ได้หุ้นผิด / ปนแถวยอดรวม และเลือกบัญชีไม่ได้
- **RCA-007**: `/cash lib sync` ได้ข้อมูลของ Click2Win
- **RCA-008**: `/login kss` ตอบ ✅ ทั้งที่ session หมดอายุ (หน้าเว็บเด้งไป `/SignIn`)
- **RCA-009**: `/cash kss sync` อ่านจากหน้า SignIn แล้วคืน 0.0 ทุกช่องเหมือนเป็นค่าจริง

อ่านก่อนเริ่ม: `rca/shared/rca_line_cli.md` (แถว 006–009), `learned_workflows/krungsri/trademan_portfolio_dom.md` (selector จริงจาก probe), `docs/handoff/TASK-line-cli-livetest-A.md` (รอบ C/D)

## Context map
| # | ไฟล์ / symbol | บรรทัด | สิ่งที่ต้องทำ |
|---|---|---|---|
| 1 | `app/mcp/pillars/pillar2_portfolio.py` `portfolio_get_balances` | L350-361, block LIBERATOR ที่ L419+ | normalise ชื่อ `LIBERATOR`/`LIB` → `"LIBERATOR"`; ค่าที่ไม่รู้จักต้อง `raise ValueError`; **ห้าม `else: CLICK2WIN`**. grep หา fallback `else`→C2W ที่เหลือในไฟล์ แล้วรายงาน (แก้เฉพาะที่ถูกเรียกจาก CLI) |
| 2 | `app/browser/auth_driver.py` เช็ก saved-session | L195-240 | ตรวจ URL ให้ครอบ `signin` (ไม่สนตัวพิมพ์) ด้วย ไม่ใช่แค่ `login`; รอ ~3s ให้หน้าเสถียร แล้วเช็กซ้ำว่า URL ยังไม่ใช่ SignIn **และ** `#dropDownAccountPort > div.flex.w-full.justify-between > div` มีเลขบัญชี 7 หลัก; ถ้าไม่ผ่าน ทำตามเส้นทาง fail เดิม (quarantine, Invariant 8) |
| 3 | `app/browser/trademan_driver.py` `switch_account` | L294-417 (selector เก่าอยู่ L366) | เปลี่ยน `.v-list-item:has-text(...)` → `#dropDownAccountPort div.absolute span:text-is("<acc>")`; ปิด popup ก่อนคลิก; หลังคลิกต้องเช็กว่าเลขบัญชีปัจจุบันตรงเป้า ถ้าไม่ตรงคืน error |
| 4 | `trademan_driver.scrape_portfolio` | L418-~530 (เลิกใช้ `table tbody tr` ที่ L449 และ L531) | (a) เช็ก auth เหมือนข้อ 2; (b) เลือกบัญชีตาม `account_type` ด้วยข้อ 3; (c) reload หน้าแม้ URL มี `Portfolio` อยู่แล้ว; (d) หาตารางหัวจาก `thead th` ที่มี `Symbol`+`On Hand`+`Market Value` แล้วใช้ตาราง body ที่อยู่ข้างกัน (`div.overflow-y-auto.scrollbar-container.section > table`) ใน container เดียวกัน; (e) map คอลัมน์ตามชื่อหัว; (f) ข้ามแถวยอดรวมและแถว placeholder; (g) ผลต้องมี `account_no` ที่อ่านจาก DOM |
| 5 | `trademan_driver.scrape_account_summary` | L1957+ | ถ้า auth ไม่ผ่านหรือหา selector ไม่เจอ ต้องคืน `None` ต่อ field (ห้าม `0.0`); log ว่าหา selector ไหนไม่เจอ **ห้ามเดา selector ใหม่** (ยังไม่ได้ probe) ให้ส่งค่า None ไปที่การ์ด |
| 6 | `app/services/line_cli/handlers.py` ส่วน sync | cash L470-485; port/orders L440-468 | ถ้าได้ `None` ทั้งหมด หรือ driver แจ้ง unauthenticated → การ์ดแสดง `⚠️ อ่านไม่ได้ / session หมดอายุ — /login kss` และ **ห้ามติด 🟢 live**; การ์ด port แสดงเลขบัญชีที่อ่านจาก DOM |
| 7 | `trademan_driver._scrape_view_order_rows` / `scrape_unmatched_orders` | L851-1000 | **อ่านอย่างเดียว เพื่อยืนยัน**: Symbol = คอลัมน์ที่ 3 (`Order No.\|Side\|Symbol\|Volume\|Price\|Matched\|Status\|Time\|Quote`) ถ้าโค้ดใช้คอลัมน์ผิด → แก้ด้วยวิธี map ตามชื่อหัวเหมือนข้อ 4 ถ้าถูกอยู่แล้ว → ไม่ต้องแตะ |

Verify (ทีละ unit):
- `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py`
- `.venv/bin/python scripts/verify_changes.py app/browser/auth_driver.py`
- `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py`
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py`
- ปิดงาน: `.venv/bin/python scripts/verify_changes.py --full` **ไม่ใส่ timeout** รันครั้งเดียว

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/mcp/pillars/pillar2_portfolio.py` (เฉพาะ `portfolio_get_balances`)
- `app/browser/auth_driver.py` (เฉพาะส่วนเช็ก saved-session)
- `app/browser/trademan_driver.py` (`switch_account`, `scrape_portfolio`, `scrape_account_summary`, `_scrape_view_order_rows` ถ้าจำเป็น)
- `app/services/line_cli/handlers.py`, `app/services/line_cli/cards.py` (แสดงสถานะ "อ่านไม่ได้")
- tests ที่เกี่ยวข้อง (เพิ่ม/แก้): `tests/test_line_cli_flow.py`, `tests/test_pillar2_portfolio_liberator.py` และ test ของ trademan_driver/auth_driver ตาม `MODULE_TEST_MAP`

## Steps / Task Decomposition (Loop Engineering — บังคับ)
1. RCA-007: แก้ normalise ใน pillar2 + test ว่า `portfolio_get_balances(platform="LIBERATOR")` เรียก liberator และ **ไม่เรียก** click2win; ค่าที่ไม่รู้จักต้อง raise → verify
2. RCA-008: เช็ก URL/DOM ใน auth_driver + test 3 กรณี (URL `/SignIn`; dropdown โผล่แล้ว redirect; session ใช้ได้จริง) → verify
3. RCA-009: `scrape_account_summary` คืน `None` เมื่อ unauthenticated / หา selector ไม่เจอ + การ์ดแสดง "อ่านไม่ได้" + test → verify
4. RCA-006a: selector ของ `switch_account` + เช็กเลขบัญชีหลังเลือก + test ด้วย mock page → verify
5. RCA-006b: `scrape_portfolio` ใช้ตารางคู่หัว/body + map ตามชื่อหัว + ข้ามแถวยอดรวม + เลือกบัญชี + reload. Test ด้วย HTML fixture ที่จำลองโครงสร้างจาก runbook: ตารางหัว, body 15 แถว, ตารางยอดรวม 1 แถว, `#draggable-table-stocks` → ต้องได้ 15 แถว ไม่ใช่ 16 → verify
6. ตรวจ view-order (Context map ข้อ 7) แก้เฉพาะเมื่อผิด → verify
7. `--full` ครั้งเดียว + เติม Cline Report

## Acceptance / Tests ที่ต้องผ่าน
- verify ของทุก unit ด้านบน PASS (exit 0) และ `--full` PASS
- ไม่มีที่ไหนคืน `0.0` / `500_000` / ข้อมูลของ C2W เป็นค่าจริงของ KSS/LIB อีก
- ตอน Antigravity ทดสอบ live ซ้ำ (A8/A9/A11 + C2/C3) จะเช็กว่า `/cash lib sync` = ข้อมูล Liberator, `/login kss` กับ session หมดอายุ → ขอ OTP (ผ่าน relay) ไม่ใช่ ✅ ปลอม, `/port kss sync` = 15 แถวของบัญชีที่เลือก

## Out of scope / ห้ามแตะ
- การส่ง/แก้/ยกเลิกคำสั่ง, tick size, การตรวจราคา/จำนวน — **ห้ามแตะ**
- RCA-002 (S)/(B), RCA-003 EE, RCA-004 การ์ด orders, F-5 OTP ใน log, F-7 browser ใช้ร่วมกัน → เป็น card P1 แยก
- selector สรุปบัญชี (cash/EE) ใหม่ — ยังไม่ได้ probe ห้ามเดา
- ห้ามยิง SMS OTP ระหว่างเทสต์ (Invariant 9); เทสต์ต้อง mock driver/page ทั้งหมด
- ห้ามรีสตาร์ท gateway หรือรัน live; Antigravity เป็นคนทำ

## Open questions (Antigravity)
- โครงสร้าง holdings ของบัญชี CASH ยังไม่ได้ probe (สันนิษฐานว่าใช้ component เดียวกับ MARGIN) → โค้ดต้องไม่ผูกกับประเภทบัญชี
- แถวที่ชื่อหุ้นซ้ำ (BCPG×2, VGI×2) น่าจะเป็น LONG/SHORT → ข้อ 5 ต้องเก็บทุกแถว ห้าม dedupe ตามชื่อหุ้น

---

## Cline Report (Cline เขียน)

Status: **DONE** — code + unit verify + `--full` ผ่านทั้งหมด (2026-10-14, Cline); เหลือ Antigravity live re-test (A8/A9/A11 + C2/C3)

### Files changed
- `app/browser/trademan_driver.py`
  - ใหม่: `_extract_account_no`, `_parse_float`, `_parse_int`, `_hkey`, `_map_holdings_columns`, `_is_placeholder_or_totals_row`, `_pair_holdings_tables`, `_PORTFOLIO_TABLES_JS`, `_read_current_account_no`, `_select_account_on_page`
  - `switch_account` (RCA-006a): selector `#dropDownAccountPort div.absolute span:text-is("<acc>")` + เช็กเลขบัญชีหลังคลิก + ล้มเหลว = `success=False` / `ACCOUNT_SWITCH_FAILED` (เดิมคืน success ปลอม)
  - `scrape_portfolio` (RCA-006b): auth gate → เลือก/ยืนยันบัญชี → reload ทุกครั้ง → pair ตารางหัว/body → map ตามชื่อหัว → ข้าม totals/placeholder → `account_no` ต่อแถว + `portfolio_scrape_authenticated`
  - `scrape_account_summary` (RCA-009, Unit 3): `None` ต่อ field ที่อ่านไม่ได้ + `authenticated`
  - `__init__`: `portfolio_scrape_authenticated = False`
- `app/browser/auth_driver.py` — `verify_saved_session` (RCA-008, Unit 2)
- `app/mcp/pillars/pillar2_portfolio.py` — `portfolio_get_balances` (RCA-007, Unit 1; เฉพาะ symbol นี้)
- `app/services/line_cli/handlers.py` — `_live_card`: port (kss) ต้อง `portfolio_scrape_authenticated` จริง + แสดงเลขบัญชีจาก DOM; cash ต้อง `authenticated is not False` และมีค่าจริง ไม่งั้นส่ง `unavailable_card`
- `app/services/line_cli/cards.py` — `unavailable_card()` + `UNAVAILABLE_HINT = "อ่านไม่ได้ / session หมดอายุ"`
- `scripts/verify_changes.py` — `MODULE_TEST_MAP["app/browser/trademan_driver.py"]` += `tests/test_sbl_account_driver.py`, `tests/test_trademan_portfolio_scraper.py`
- tests: `tests/test_sbl_account_driver.py` (+5 switch_account, autouse state fixture), `tests/test_trademan_portfolio_scraper.py` (ใหม่ 11), `tests/test_line_cli_flow.py` (+5 live-card), `tests/test_auth_session_nondestructive.py` (+3, Unit 2), `tests/test_action_center.py` (แก้ mock 1 test — ดูหมายเหตุใน Tests run)
- docs: `rca/shared/rca_line_cli.md` (Proven fix), `learned_workflows/krungsri/trademan_portfolio_dom.md` (Implementation status)

### Summary
- Unit 6 (Context map ข้อ 7) = **อ่านอย่างเดียว, ไม่ต้องแก้**: `_VIEW_ORDER_ROWS_JS` หาตารางจาก `thead th` (Order No./Status/Symbol) แล้วใช้ body table ใน `div.overflow-y-auto.scrollbar-container` อยู่แล้ว และ `_scrape_view_order_rows` ใช้ `cells[2]` = Symbol ตรงกับคอลัมน์ที่ยืนยันสด → ไม่แตะ
- Unit 5 เพิ่ม `_select_account_on_page()` ให้ `switch_account` (authenticate ก่อน) และ `scrape_portfolio` (ห้าม login/OTP — Invariant 9) ใช้ร่วมกัน = single source of truth
- Anti-Mock: ไม่มีที่ไหนคืน 0.0 / 500_000 / ข้อมูล C2W เป็นค่าจริงใน path ที่แก้; การ์ดขึ้น "⚠️ อ่านไม่ได้ / session หมดอายุ — /login kss" และไม่ติด 🟢 live
- `scrape_portfolio` คง return type `List[Dict]` (เพิ่ม key `account_no`) → caller เดิมไม่พัง
- Test state isolation: driver เป็น singleton — เพิ่ม autouse fixture save/restore `active_account_no`/`active_account_type` (เจอ test pollution จริงระหว่าง Unit 4→5)

### Tests run + result
- `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py` → PASS (Unit 1)
- `... app/browser/auth_driver.py tests/test_auth_session_nondestructive.py` → PASS (Unit 2)
- `... app/browser/trademan_driver.py tests/test_sbl_account_driver.py` → PASS 20 passed (Unit 3), PASS 25 passed (Unit 4), PASS 25 passed (Unit 5 refactor)
- `... app/browser/trademan_driver.py tests/test_trademan_portfolio_scraper.py scripts/verify_changes.py` → PASS 53 passed (Unit 5; browser fixture รันจริงผ่าน chromium fallback = ไม่ skip)
- `... app/services/line_cli/handlers.py app/services/line_cli/cards.py` → PASS 30 passed (Unit 7)
- `... handlers.py cards.py tests/test_line_cli_flow.py` → PASS 35 passed (Unit 7+8)
- `--full`: **PASS — 517 passed in 166s** (รันครั้งเดียวตอนปิดงาน ไม่ค้างที่ ~87%)
- ระหว่าง `--full` เจอ 1 fail: `tests/test_action_center.py::test_auth_driver_session_reuse_active_tab` → mock ของ `#dropDownAccountPort` ไม่ได้ให้ `inner_text()` เป็นข้อความ (เป็น MagicMock) จึงไม่มีเลขบัญชี 7 หลักตามเงื่อนไข RCA-008 ที่ handoff บังคับ → **แก้ที่ mock** (`inner_text = "3024959"`) ไม่ได้ผ่อนเงื่อนไขในโค้ด

### Open questions
1. `switch_account` ยังมี branch "browser not active" ที่คืน `{"success": True, "status": "SIMULATED_SWITCH", "account_no": <จาก settings>}` — เป็นข้อมูลที่ไม่ได้อ่านจากจอ (Anti-Mock) และทำให้ caller ที่เชื่อ success ทำงานต่อ; อยู่นอก scope ของข้อ 3 (handoff สั่งแค่ selector + post-check) → ต้องให้ Antigravity ตัดสินใจว่าจะให้คืน error หรือคงไว้
2. การ์ด orders (`current_orders`) ยังไม่มี auth signal จาก pillar2 → ยังฟันธง "อ่านไม่ได้" ไม่ได้; `portfolio_holdings`/`current_orders` ยังมี `else: CLICK2WIN` ของตัวเอง (ตามคำสั่ง: grep + report เท่านั้น — ไม่ได้แก้)
3. การ์ด port ของ lib ยังขึ้น account `"LIVE"` (ไม่ใช่เลขบัญชี) เพราะ `portfolio_holdings` (LIBERATOR) ไม่คืน `account_no` ออกมา — kss ได้เลขจาก DOM แล้ว
4. `scrape_sbl_lots` (L829) ยังใช้ `query_selector_all("table tbody tr")` (RCA family เดียวกับ 006) — อยู่นอก scope
5. Browser ของ Playwright ในเครื่องเป็น revision 1200 แต่ driver คาด 1234 → test ที่ต้องใช้ DOM จริงจะ skip ในเครื่องอื่น ถ้าไม่มี fallback; ในเครื่องนี้รันได้ (มี `_find_local_chromium()`)

