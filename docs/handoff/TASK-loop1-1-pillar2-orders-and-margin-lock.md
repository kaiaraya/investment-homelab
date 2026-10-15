# TASK-loop1-1: Pillar 2 เก็บตก — /orders & /port (MARGIN lock · authenticated flag · Anti-Mock)

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Krungsri TradeMan (KSS · MARGIN 3024959) + Liberator WebTrade (LIB · CASH)
- Status: DRAFT
- Depends on: —
- Unblocks: TASK-loop1-2, TASK-loop1-3
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): A3, C2 (LIB account_no), C4
- Verify: `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py app/browser/trademan_driver.py app/services/line_cli/handlers.py app/services/line_cli/cards.py`

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §2 (Pillar 2) — ไม่มีการเปลี่ยน directive เพิ่มเติม การ์ดนี้คือการเก็บตกช่องโหว่ที่ค้างจาก `TASK-cli-p0-data-integrity.md` Open questions ข้อ 1–3

## Context
ปิดช่องโหว่ Pillar 2 ที่ค้าง เพื่อให้ `/orders` และ `/port` สมบูรณ์ 100% ก่อนเริ่มต่อราคา (การ์ด 2–3):
1. `portfolio_holdings` / `current_orders` / `current_open_orders` ยังมี `else: CLICK2WIN` fallback → ส่ง platform ที่ไม่รู้จักต้อง `raise ValueError` (Broker Isolation + Anti-Mock)
2. `current_orders()` ยังไม่คืน flag `authenticated` → `_live_card("orders")` ฟันธง "อ่านไม่ได้" ไม่ได้ (ยังโชว์ 🟢 live ปลอม)
3. `portfolio_holdings` (LIBERATOR) ยังไม่คืน `account_no` → หัวการ์ด `/port lib sync` ขึ้น "LIVE" แทนเลขบัญชี
4. `trademan_driver.switch_account` branch "browser not active" คืน `SIMULATED_SWITCH` success ปลอม (Anti-Mock)

อ้างอิง RCA: `rca/shared/rca_line_cli.md` (CLI-RCA-004/007), `docs/handoff/TASK-cli-p0-data-integrity.md` §Open questions

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/mcp/pillars/pillar2_portfolio.py`
- `app/browser/trademan_driver.py`
- `app/services/line_cli/handlers.py`
- `app/services/line_cli/cards.py`
- `tests/test_line_cli_flow.py` (ปรับ/เพิ่ม assertions เท่านั้น)

## Context map
| File | Symbol / Lines | Why |
|---|---|---|
| `app/mcp/pillars/pillar2_portfolio.py` | `portfolio_get_balances` L350–470 | read: pattern ที่แก้แล้ว (`raise ValueError` L366-372 + คืน `authenticated` L445/467) → copy ไปใช้ |
| 〃 | `portfolio_holdings` L501–558 | edit: ลบ `else: CLICK2WIN` L511-512 → raise; LIBERATOR branch L524-533 คืน `account_no` + `authenticated` |
| 〃 | `current_open_orders` L561–600 | edit: normalization L567-573 ลบ `else: CLICK2WIN` L572-573 |
| 〃 | `current_orders` L602–710 | edit: normalization L623-629 ลบ `else: CLICK2WIN` L628-629; เพิ่ม `authenticated` ใน return dict |
| `app/browser/trademan_driver.py` | `switch_account` L538–620 | edit: branch "browser not active" L570-575 → `{"success": False, "status": "BROWSER_NOT_ACTIVE"}` |
| `app/services/line_cli/handlers.py` | `_live_card` "orders" L607–617 | edit: ถ้า `res.get("authenticated") is False` → `cards.unavailable_card()` ก่อน render |
| `app/services/line_cli/cards.py` | `orders_card` L321 · `unavailable_card` L300 | edit: แถวออเดอร์ 2 บรรทัด (ชื่อหุ้นตัวหนา size `md`) แก้ CLI-RCA-004 |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | แก้ `switch_account` L570-575 → `BROWSER_NOT_ACTIVE` | ไม่มี `SIMULATED_SWITCH` success ปลอม | `.venv/bin/python -m pytest tests/test_sbl_account_driver.py -q` | ✅ (96 passed incl. flow/view-order) |
| 2 | ลบ `else: CLICK2WIN` ใน 3 ฟังก์ชัน → `raise ValueError` | platform ไม่รู้จัก → error ไม่ใช่ CLICK2WIN | `.venv/bin/python -m pytest tests/test_pillar2_order_ledger.py tests/test_pillar2_portfolio_liberator.py -q` | ✅ (CLICK2WIN keep explicit → guardrail) |
| 3 | เพิ่ม `authenticated` + `account_no` ใน return | orders/port คืน flag/เลขบัญชีจริง | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ |
| 4 | `_live_card` orders + `orders_card` 2 บรรทัด | การ์ด orders ซื่อสัตย์ + ไม่ตัดขอบมือถือ | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ |
| 5 | verify ครบ 4 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py app/browser/trademan_driver.py app/services/line_cli/handlers.py app/services/line_cli/cards.py` | ✅ PASS (129 passed, 41.7s) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py app/browser/trademan_driver.py app/services/line_cli/handlers.py app/services/line_cli/cards.py`
- `.venv/bin/python -m pytest tests/test_line_cli_flow.py tests/test_pillar2_order_ledger.py tests/test_sbl_account_driver.py -q --tb=line`

## Out of scope / ห้ามแตะ
- ห้าม place/modify/cancel order · ห้ามยิง SMS OTP · ห้าม restart gateway ระหว่าง test
- ห้ามแตะ quicktrade/nego logic (การ์ด 2–3) · ห้ามแตะ tick-size/uptick logic

---

## Cline Report
- Files changed:
  - `app/mcp/pillars/pillar2_portfolio.py` — `portfolio_holdings` / `current_open_orders` / `current_orders`: removed every `else: CLICK2WIN` fallback → explicit `CLICK2WIN` branch + `raise ValueError` for an unknown platform; `portfolio_holdings` (LIBERATOR) now returns `account_no` + `authenticated`; `current_orders` now returns `authenticated`.
  - `app/browser/trademan_driver.py` — `switch_account`: "browser not active" branch returns `{"success": False, "status": "BROWSER_NOT_ACTIVE", "account_no": None}` (no more `SIMULATED_SWITCH`); new flag `orders_scrape_authenticated` set by `scrape_all_orders` (False on no page / SignIn URL / View-Order tab unreachable).
  - `app/services/line_cli/handlers.py` — `_live_card("orders")` returns `cards.unavailable_card()` when `res["authenticated"] is False`; `_live_card("port")` uses the LIBERATOR `account_no` from the pillar payload for the header instead of the word `LIVE`.
  - `app/services/line_cli/cards.py` — `orders_card` renders 2 lines per order (bold `md` symbol line + qty/price/status line, CLI-RCA-004); `_cell()` gained an optional `size` kwarg (default `xs`, no behaviour change elsewhere).
  - `tests/test_line_cli_flow.py` — 6 assertions/tests added (no existing assertion weakened).
- Summary:
  - A3 (MARGIN lock / no Click2Win leak): all three Pillar-2 readers now raise `ValueError` on an unknown platform; `CLICK2WIN` / `C2W` stay explicit (still a truthful guardrail rejection in `current_orders`, still the real Click2Win reader in `portfolio_holdings` / `current_open_orders`). LIB default platform in `.env` is `TRADEMAN` → KSS path unchanged.
  - C4 (honest `/orders … sync`): the card is only `🟢 live` when the ledger really came off a signed-in TradeMan View Order tab; otherwise `⚠️ อ่านไม่ได้ / session หมดอายุ` + `/login kss` button. An unreadable day can no longer render as "ยังไม่มีออเดอร์ในระบบ" with a live badge.
  - C2 (LIB header): `/port lib sync` header shows the Liberator account number (`7055938`) instead of `LIVE`.
  - Anti-Mock: `switch_account` no longer invents a success + settings-derived account number when there is no browser page.
  - Broker isolation kept: no broker's selector/behaviour reused across KSS/LIB; no order/tick-size/uptick logic touched; no OTP fired; gateway not restarted; quicktrade/nego untouched.
- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py app/browser/trademan_driver.py app/services/line_cli/handlers.py app/services/line_cli/cards.py` → **PASS** (compileall OK · targeted 129 passed in 41.7s).
  - `.venv/bin/python -m pytest tests/test_line_cli_flow.py tests/test_pillar2_order_ledger.py tests/test_sbl_account_driver.py tests/test_trademan_view_order_scraper.py -q --tb=line` → **96 passed** (24.8s).
  - New tests: unauthenticated `/orders` card → `อ่านไม่ได้` (no 🟢); 2-line order row (bold `md` symbol cell, symbol line before qty line); `/port lib` shows account number; unknown platform raises in all 3 readers; `CLICK2WIN` stays a guardrail rejection; `switch_account` without a browser → `BROWSER_NOT_ACTIVE` + `account_no=None`.
- Open questions:
  1. `orders_scrape_authenticated` is derived from "page URL on `trademan.in.th` (no `signin`/`login`) AND the `div#order_btn` View Order tab was reachable" — the dropdown check `_is_authenticated_page()` cannot be reused there because `#dropDownAccountPort` only exists on `/Portfolio`, not on the View Order tab. Needs one live confirmation with a genuinely expired session (human witness) before closing C4.
  2. LIBERATOR `authenticated` uses `liberator_plugin.get_health()["is_authenticated"]` (tab-active) — the same source as `handlers._broker_session_alive`, so an expired-but-open Liberator tab is still reported as authenticated (pre-existing limitation, not widened here).
  3. The LIB account number comes from `PortfolioSnapshot.account_no` ← `settings.LIBERATOR_USERNAME` (config), not scraped off the page — same source `/cash lib` has always used. A DOM-read number would be a follow-up card.
  4. `verify_changes.py --full` at task close → **2 failed, 626 passed** (184.8s). Both failures are pre-existing/environmental, NOT this change: `tests/test_mcp_and_workflow_engine.py::{test_mcp_handle_tool_call_buffered_recording,test_mcp_json_rpc_stdio_subprocess}` fail because `app/mcp/mcp_server.py:321` (retired stdio entrypoint) launches a **headed** Chromium with no X server (`Missing X server or $DISPLAY`). No changed file appears in their stack traces.

---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED

---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
