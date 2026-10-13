# TASK-cli-p1-display-and-redaction: การ์ด /port ให้ถูกต้องและครบ + ปิดข้อมูลลับใน log

- Created: 2026-10-14 by Antigravity
- Broker: KSS (หลัก), LIB (เฉพาะส่วนการ์ดที่ใช้ร่วมกัน). **ห้ามเอาโค้ดหรือ selector ของโบรกเกอร์หนึ่งไปใช้กับอีกโบรกเกอร์**
- Priority: P1. Round B (`/nego`) ต้องรอข้อ 1 เสร็จ เพราะ P/L กลับเครื่องหมาย
- Status: DONE (code + unit/full verified; live re-test owned by Antigravity)
- **ไม่อยู่ในใบนี้:** RCA-011 (การ์ดเงินสด KSS / EE) ต้องรอ Antigravity probe หน้า Account Info ก่อน แล้วจะออก handoff แยก

## Context (Antigravity เขียน)
Live รอบ R (2026-10-14 04:30–04:57) หลังแก้ P0:
- ✅ RCA-006 (ได้ 15 แถว บัญชี 3024959 ยืนยันแล้ว), RCA-007 (`/cash lib` เป็นข้อมูล Liberator), RCA-008/009 (ผ่าน unit test; live ไม่ได้ทดสอบเส้นเช็ก session เก่า เพราะไม่มีไฟล์ session)
- ❌ **RCA-002 (High)**: P/L รวมบนการ์ด **กลับเครื่องหมาย** เทียบกับ Unrealized P/L ในแอป และ %P/L รายแถวของหุ้น (S) กลับเครื่องหมาย; ป้าย "P/L วันนี้" ผิด (ค่านี้คือ unrealized); ไม่มีป้าย (S)/(B)
  - แอปแสดงชื่อหุ้นแบบ `BCPG (S)`, `BCPG (B)`, `MTC (B)` โดย (B) = หุ้นที่ยืมมา (borrowed) ซึ่ง avg = 0.00
- ❌ **RCA-010 (Med)**: การ์ดแสดงแค่ 10 จาก 15 แถว
- F-5 / F-8: log มีเลข OTP เต็ม และ SSO JWT (`efin.finance/auth_sso?token=…`)
- เล็กน้อย: หัวการ์ด LIB ขึ้น enum ดิบ `CASH_BALANCE`

อ่านก่อนเริ่ม: `rca/shared/rca_line_cli.md` (002, 010), `learned_workflows/krungsri/trademan_portfolio_dom.md`

## Context map
| # | ไฟล์ / symbol | บรรทัด | สิ่งที่ต้องทำ |
|---|---|---|---|
| 1 | `trademan_driver.scrape_portfolio` ส่วนแยก side | ~L769-776 | ตอนนี้หา `(S)`/`(B)` ใน `sym_raw` อยู่แล้ว; **ยังไม่ได้ยืนยันว่าหน้าเว็บมีข้อความนี้จริง** (Open Q1) ห้ามเดา selector ใหม่; ถ้าใน cell ไม่มี marker → `position_type="UNKNOWN"` (ไม่ใช่ `LONG`) |
| 2 | `handlers._normalise_holdings` | L404-~430 (และ L364 ซ้ำ) | เก็บ `position_type` ไว้; P/L: LONG = (last−cost)/cost, SHORT = (cost−last)/cost; BORROWED (avg 0) → ไม่คำนวณ % (แสดง `—`); UNKNOWN → แสดง `—` ห้ามคิดแบบ LONG |
| 3 | `handlers._live_card` port | L455-465, L516 | P/L รวม: ใช้ผลรวมที่คิดตาม side ข้อ 2 **หรือ** ค่า Unrealized P/L ที่อ่านจากหน้าเว็บถ้ามี; เลิกใช้ `rows[:10]` → ส่งทุกแถว |
| 4 | `cards.port_card` | L170-205 | ป้าย `P/L วันนี้` → `Unrealized P/L`; ต่อท้ายชื่อหุ้นด้วย `(S)`/`(B)`; แสดงทุกแถว ใช้ **carousel** ใบละ ≤12 แถว (ใบแรกมีหัวรวม ใบถัดไปมีแค่รายการ); ใช้ได้กับ LIB ด้วย (ไม่มี side → ไม่ต้องต่อท้าย) |
| 5 | `cards.cash_card` / handler cash | handlers L470-490 | แปลง enum เป็นชื่อที่อ่านง่าย (`CASH_BALANCE` → `Cash Balance`); **ห้ามแตะการ map ค่าของ KSS** (เป็นงาน RCA-011) |
| 6 | redaction ใน log | `app/services/otp_relay_registry.py` (LINE_OTP_RECEIVED), `app/browser/auth_driver.py` (`Received OTP '…'`, `TradeMan SSO popup opened: <url>`), `LiberatorDriver` `Captured OTP` | ปิด OTP เป็น `******`; ตัด query string ของ SSO URL (`?token=` → `?token=<redacted>`); เพิ่ม helper `redact()` ที่ใช้ร่วมกัน + test |

Verify (ทีละ unit):
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py`
- `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py`
- `.venv/bin/python scripts/verify_changes.py app/browser/auth_driver.py app/services/otp_relay_registry.py`
- ปิดงาน: `--full` ครั้งเดียว ไม่ใส่ timeout

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/handlers.py`, `app/services/line_cli/cards.py`
- `app/browser/trademan_driver.py` (เฉพาะส่วนแยก side ข้อ 1)
- `app/services/otp_relay_registry.py`, `app/browser/auth_driver.py`, ไฟล์ LiberatorDriver (**เฉพาะข้อความ log**)
- tests: `tests/test_line_cli_flow.py`, `tests/test_trademan_portfolio_scraper.py` (+ test redaction ใหม่)

## Steps / Task Decomposition (Loop Engineering — บังคับ)
1. ข้อ 2: P/L ตาม side + test 4 กรณี (LONG/SHORT/BORROWED/UNKNOWN) โดย SHORT ที่ last>cost ต้องได้ค่าติดลบ → verify
2. ข้อ 3+4: P/L รวม + carousel + ป้าย + tag. Test: 15 แถว → 2 bubble, ไม่มีข้อความ "และอีก", SHORT แสดง `(S)` → verify
3. ข้อ 1: ใช้ UNKNOWN เมื่อไม่มี marker + fixture ที่มี `BCPG (S)` / `MTC (B)` → verify
4. ข้อ 5: ป้ายหัวการ์ด → verify
5. ข้อ 6: redaction + test ว่า log ไม่มีเลข 6 หลักและไม่มี `token=eyJ` → verify
6. `--full` + Cline Report

## Acceptance / Tests ที่ต้องผ่าน
- verify ของทุก unit PASS และ `--full` PASS
- live (Antigravity): `/port kss sync` → เครื่องหมาย Unrealized P/L ตรงกับแอป, มี (S)/(B), เห็นครบ 15 แถว; grep log หลัง login ไม่เจอ OTP หรือ JWT

## Out of scope / ห้ามแตะ
- RCA-011 การ์ดเงินสด KSS / EE / selector ของ Account Info (รอ probe)
- การส่ง/แก้/ยกเลิกคำสั่ง, tick size, การตรวจราคา/จำนวน
- Open questions จาก P0: SIMULATED_SWITCH, `else: CLICK2WIN` ใน `portfolio_holdings`/`current_orders`, `scrape_sbl_lots` ที่ยังใช้ `table tbody tr`, เลขบัญชี LIB, F-7 browser ใช้ร่วมกัน → เก็บไว้ทำ P2
- ห้ามยิง OTP, ห้ามรัน live, ห้ามรีสตาร์ท gateway

## Open questions (Antigravity)
- Q1: cell ชื่อหุ้นบนเว็บ TradeMan มี `(S)`/`(B)` ไหม หรือแยกเป็นคอลัมน์อื่น → Antigravity จะ probe รอบหน้าพร้อม Account Info; ระหว่างนี้ข้อ 1 ใช้ UNKNOWN ไปก่อน

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/services/line_cli/handlers.py` — new `_position_type` / `_holding_pnl_pct` / `_portfolio_totals`; `_normalise_holdings` keeps `position_type` + the DOM's `unrealized_pnl`/`market_value`; `_read_db_positions` restores `Position.position_type`; `_live_card` (port) + `_handle_read` (snapshot) use `_portfolio_totals` and pass **all** rows; new `_ACCOUNT_TYPE_LABEL` / `_account_type_label` (cash-card header)
  - `app/services/line_cli/cards.py` — `port_card`: label `P/L วันนี้` → `Unrealized P/L`, `(S)`/`(B)` suffix, `—` for unreadable %P/L, `PORT_ROWS_PER_BUBBLE = 12` carousel, `overflow` parameter removed (no "และอีก")
  - `app/browser/trademan_driver.py` — `scrape_portfolio`: unmarked symbol → `position_type="UNKNOWN"` (was the `LONG` assumption)
  - `app/services/redaction.py` **(new)** — `redact_otp()` / `redact_url()` / `redact_otp_details()`
  - `app/services/otp_relay_registry.py` — import + L269 log line redacted (**DB payload untouched**)
  - `app/browser/auth_driver.py` — import + L501 / L670 / L864 log redaction
  - `app/brokers/liberator/driver.py` — import + L479 / L525 / L547 / L566 (the console `print` of the full OTP is gone)
  - tests: `tests/test_line_cli_flow.py` (+6), `tests/test_trademan_portfolio_scraper.py` (+1 side-marker test; `cpall` now expected `UNKNOWN`), `tests/test_redaction.py` **(new, 5)**
  - `scripts/verify_changes.py` — `MODULE_TEST_MAP["app/services/redaction.py"] = ["tests/test_redaction.py"]`
  - `tests/test_sbl_account_driver.py` — hermeticity fix only, **outside the whitelist** (Open question 1)
  - docs: `rca/shared/rca_line_cli.md` (Proven fix RCA-002/010/F-5/F-8), `learned_workflows/krungsri/trademan_portfolio_dom.md` (marker + P/L + carousel rules)
- Summary:
  - Requirement 2: P/L follows the side — LONG `(last−cost)/cost`, SHORT `(cost−last)/cost`, BORROWED/UNKNOWN/no-cost → `None` → `—` (never a fabricated `0.0`). Totals prefer the page's own Unreal/Market Value columns and fall back to a side-aware `volume×(last−cost)` (inverted for SHORT).
  - Requirement 3+4: `Unrealized P/L` label, 12 rows/bubble carousel (15 rows → 2 bubbles → all rows reachable), `(S)`/`(B)` tags. LIBERATOR stays side-less (defaults `LONG`) — no cross-broker assumption.
  - Requirement 1: the driver no longer assumes `LONG`; `(S)`/`(B)` markers set the side, anything else is `UNKNOWN` (pending your live confirmation, Q1).
  - Requirement 5: `/cash lib` header shows `Cash Balance`, not `CASH_BALANCE`; balance-value mapping untouched (RCA-011).
  - Requirement 6: shared `app/services/redaction.py` masks OTPs as `******` and SSO URLs as `?token=<redacted>`; redaction is **log-only** so the cross-process relay row keeps the real code (invariant test included).
- Tests run + result: per-unit verifies all PASS — handlers+cards 40/41 passed, trademan_driver 37 passed, redaction set 50 passed; final gate `--full` → **PASS, 529 passed in 165.33s** (P0 baseline 517).
- Open questions:
  1. **Out-of-whitelist test edit** `tests/test_sbl_account_driver.py::test_scrape_account_summary_dry_run`: it called `scrape_account_summary()` for real, so `ensure_browser_ready()` restored the live session in `data/session_state.json` (untracked) and the DRY_RUN 500 000 placeholder (returned only when `self.page is None`) was never reached → the test scraped real DOM numbers (`60641.78`) and failed. It mapped to `trademan_driver.py`, so the handoff's own unit-3 verify command was red. Fixed by patching `ensure_browser_ready` + forcing `page=None`. Revert if you prefer that test owned by Antigravity.
  2. **Q1 still open**: whether the live TradeMan holdings cell really contains `(S)`/`(B)`. Until confirmed, every unmarked symbol renders `UNKNOWN` → the `%P/L` column shows `—` for the whole book. If the page instead uses a separate column, only `_PORTFOLIO_TABLES_JS`/`_map_holdings_columns` need to change.
  3. `/port` totals for a book containing BORROWED rows: market value is summed from the DOM column, but unrealized is 0.0 when the page exposes no `Unreal` column for that row (Anti-Mock choice — not a computed guess). Confirm the live card matches the app once the marker question is settled.

