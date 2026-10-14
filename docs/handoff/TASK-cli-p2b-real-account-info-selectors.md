# TASK-cli-p2b-real-account-info-selectors: อัปเดต Selector จริงของ Account Info ใน TradeMan Driver จากผล Probe

- Created: 2026-10-14 by Antigravity (หลังรัน probe สดในตลาดเปิด 10:00–10:13)
- Broker: KSS (TradeMan) เท่านั้น. **การ์ด LIB/C2W ห้ามเปลี่ยน** (broker isolation)
- Priority: P2b ของ CLI-RCA-011 (High)
- Status: DONE (Cline code + Antigravity live verified 2026-10-14 11:10 — CLI-RCA-011 CLOSED)

## Context (Antigravity เขียน)
ผลการรัน `scripts/krungsri/probe_account_info.py` แบบ live เมื่อเวลา 10:09–10:12 (`data/probe_out/account_info_*.json`) ค้นพบ DOM แท้จริงของ TradeMan ดังนี้:

### DOM Ground-Truth (อ่านละเอียดใน `learned_workflows/krungsri/trademan_portfolio_dom.md`)
1. **แถบสรุปล่างสุด (`div.h-full.border-borderGray > div.flex.bg-darkGray`):**
   - แบ่งเป็น 3 คอลัมน์ (`div.text-center.h-full`):
     - Label: `div.text-textGrayColor.text-xs`
     - Value: `div.text-sm.font-semibold`
   - **MARGIN:** Col 1 = `Excess Equity` | Col 2 = `PP` (Purchasing Power) | Col 3 = `Equity`
   - **CASH:** Col 1 = `Credit Line` | Col 2 = `Buy Limit` | Col 3 = `Equity`

2. **ตารางกลาง Account Info (`div.w-full.font-light > table.w-full`):**
   - แต่ละแถว `tr` มี:
     - `td:nth-of-type(1)`: Label (ใน `td.text-textGrayColor.justify-between > div:nth-of-type(1)`)
     - `td:nth-of-type(2)`: Value (ใน `td.text-left` หรือ `td.text-right`)
   - **MARGIN:** มี `Excess Equity`, `Equity`, `%MM`, `Margin Required`, `Account Type`, `PP`, `Credit Line`, `Cash Balance`, `Liabilities (Loan)`
   - **CASH:** มี `Name`, `Account Type`, `Credit Line`, `Buy Limit`, `Equity`

3. **ทำไม Selector เดิมของ Driver ถึงล้มเหลว:**
   - เดิมใช้ `td:has-text('Excess Equity') + td` ซึ่ง `+ td` หาไม่เจอเพราะ DOM มีโครงสร้าง div ภายใน td หรือค่าอยู่ในแถบล่าง `bg-darkGray`

---

## Context map & สิ่งที่ต้องทำ
| # | ไฟล์ / symbol | สิ่งที่ต้องทำ |
|---|---|---|
| 1 | `app/browser/trademan_driver.py` (`scrape_account_summary`) | อัปเดต selector ให้ตรงกับ DOM จริงตามรายละเอียดด้านล่าง: <br>1. `excess_equity`: ดึงจาก `div.bg-darkGray div.text-center:has-text('Excess Equity') div.text-sm, div.bg-darkGray div.text-center:has-text('Excess Equity') div.font-semibold`, fallback `tr:has-text('Excess Equity') > td:nth-of-type(2)`<br>2. `line_available`: ดึงจาก `PP` (MARGIN) หรือ `Buy Limit` (CASH) หรือ `Line Available` ทั้งจาก `bg-darkGray` และ table `tr:has-text(...) > td:nth-of-type(2)`<br>3. `cash_balance`: เพื่อ backward compatibility กับ caller เดิม 5 จุด ให้ `summary["cash_balance"]` คืนค่า `line_available` (หากไม่มี cash_balance แท้) และเพิ่ม key `summary["real_cash_balance"]` อ่านจาก `tr:has-text('Cash Balance') > td:nth-of-type(2)`<br>4. `total_equity`: ดึงจาก `div.bg-darkGray div.text-center:has-text('Equity') div.font-semibold, tr:has-text('Equity') > td:nth-of-type(2)`<br>5. `credit_line`: ดึงจาก `div.bg-darkGray div.text-center:has-text('Credit Line') div.font-semibold, tr:has-text('Credit Line') > td:nth-of-type(2)`<br>6. คืน `account_no` เหมือนเดิม (P2a) |
| 2 | `app/mcp/pillars/pillar2_portfolio.py` (KRUNGSRI branch `portfolio_get_balances`) | `_bind(acc)`: เมื่อ `bound` เป็น True:<br>`acc["line_available"] = balances.get("line_available") or balances.get("cash_balance")`<br>`acc["cash_balance"] = balances.get("real_cash_balance")`<br>`acc["excess_equity"] = balances.get("excess_equity")`<br>`acc["credit_line"] = balances.get("credit_line")`<br>`acc["total_equity"] = balances.get("total_equity")` |
| 3 | `app/services/line_cli/handlers.py` (KSS branch ของ `_live_card` cash) | แสดงผลชัดเจน:<br>- `Line Available`: f"{float(acc['line_available']):,.2f}"<br>- ถ้า `acc.get("account_type") == "MARGIN"`: แสดง `Excess Equity` (ค่า หรือ `—`)<br>- ถ้า `acc.get("cash_balance")` ไม่เป็น None: แสดง `Cash balance`<br>- หัวการ์ด: `_account_type_label(acc.get("account_type"))` เหมือนเดิม |
| 4 | Tests | อัปเดต unit test: <br>- `tests/test_sbl_account_driver.py` หรือ `tests/test_trademan_portfolio_scraper.py`: ทดสอบ HTML mock ของ DOM ใหม่ (ทั้งแถบ bg-darkGray และ table) ตรวจว่า scrape ได้ครบทุกฟิลด์<br>- `tests/test_remote_mcp.py`: ตรวจว่า `portfolio_get_balances` ผูกค่าใหม่ได้ถูกต้อง<br>- `tests/test_line_cli_flow.py`: ตรวจสอบการ์ด KSS CASH และ MARGIN |

## Selector รายละเอียดที่แนะนำ (Playwright query_selector)
```python
# 1. Excess Equity (EE)
ee_el = await page.query_selector(
    "div.bg-darkGray div.text-center:has-text('Excess Equity') div.text-sm, "
    "div.bg-darkGray div.text-center:has-text('Excess Equity') div.font-semibold, "
    "tr:has-text('Excess Equity') > td:nth-of-type(2)"
)

# 2. Line Available / PP / Buy Limit
line_el = await page.query_selector(
    "div.bg-darkGray div.text-center:has-text('PP') div.font-semibold, "
    "div.bg-darkGray div.text-center:has-text('Buy Limit') div.font-semibold, "
    "div.bg-darkGray div.text-center:has-text('PP') div.text-sm, "
    "div.bg-darkGray div.text-center:has-text('Buy Limit') div.text-sm, "
    "tr:has-text('PP') > td:nth-of-type(2), "
    "tr:has-text('Buy Limit') > td:nth-of-type(2), "
    "tr:has-text('Line Available') > td:nth-of-type(2)"
)

# 3. Real Cash Balance (in table)
cash_el = await page.query_selector(
    "tr:has-text('Cash Balance') > td:nth-of-type(2), "
    "td:has-text('Cash Balance') + td"
)

# 4. Total Equity
eq_el = await page.query_selector(
    "div.bg-darkGray div.text-center:has-text('Equity') div.font-semibold, "
    "div.bg-darkGray div.text-center:has-text('Equity') div.text-sm, "
    "tr:has-text('Equity') > td:nth-of-type(2)"
)
```

## Steps / Task Decomposition (Loop Engineering)
1. driver: ปรับปรุง selector ใน `scrape_account_summary` + unit test mock HTML → verify
2. pillar2: อัปเดต binding ให้รับ `line_available`, `real_cash_balance` + tests → verify
3. handler: ปรับแถวการ์ด KSS cash + tests → verify
4. docs (`rca_line_cli.md`) + `--full` verify → Cline Report

Verify:
- `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py app/mcp/pillars/pillar2_portfolio.py app/services/line_cli/handlers.py`
- ปิดงาน: `.venv/bin/python scripts/verify_changes.py --full` ครั้งเดียว

## Acceptance
- verify PASS ทุกหน่วย, `--full` PASS
- driver สามารถอ่าน `Excess Equity` และ `Line Available` จาก DOM จริงของ TradeMan ได้ ไม่ตกเป็น None
- บัญชี MARGIN ได้ EE และ PP ตรงกับที่แสดงบนเว็บ
- บัญชี CASH ได้ Buy Limit ตรงกับที่แสดงบนเว็บ และไม่มีแถว EE
- การ์ด LIB ทำงานเหมือนเดิมทุกประการ
- ห้ามรัน live, ห้ามส่ง order/OTP, ห้ามรีสตาร์ท gateway (Antigravity จะทำ live re-test เอง)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/browser/trademan_driver.py` (`scrape_account_summary`): selectors re-targeted to the probed DOM (bottom `div.bg-darkGray` bar + Account Info table); new keys `line_available`, `real_cash_balance`, `credit_line`; `cash_balance` kept as an explicit mirror of `line_available`; `total_equity` guarded with `:not(:has-text('Excess'))`; scrape log line adds Real Cash.
  - `app/mcp/pillars/pillar2_portfolio.py` (KRUNGSRI `_bind()`): maps `line_available` (legacy `cash_balance` fallback), `cash_balance` ← `real_cash_balance`, `excess_equity`, `credit_line`, `total_equity` — each only when `values_bound`.
  - `app/services/line_cli/handlers.py` (KSS `/cash` branch): adds a `Cash balance` row only when `real_cash_balance` is not None (Anti-Mock: never a fabricated `0.00`).
  - `tests/test_sbl_account_driver.py`: per-field mock selectors for the new keys + **real-chromium DOM fixture** test (`_ACCOUNT_SUMMARY_HTML`) incl. the `Excess Equity` vs `Equity` collision + `1,234,567.00` totals; new-key `None` assertions on the SignIn / no-page / missing-selector paths.
  - `tests/test_remote_mcp.py`: `_bind` assertions on the new driver keys (bound MARGIN carries EE / cash / credit line / total equity; unbound is all-`None`).
  - `tests/test_line_cli_flow.py`: `_kss_balances(cash_balance=…)` + `/cash kss` MARGIN cash-row test + CASH-without-cash-row test.
  - docs (zero-contradiction): `learned_workflows/krungsri/trademan_portfolio_dom.md` (real selectors shipped + summary-key contract P2b), `rca/shared/rca_line_cli.md` (new P2b proven-fix section).
- Summary: implemented handoff items 1–4 exactly as specified. `cash_balance` semantics change only in that it is now an explicit mirror of `line_available` (the 5 legacy callers keep working); the honest cash figure is the new `real_cash_balance`. No live browser, no login, no OTP, no order, no gateway restart. LIB / C2W / Settrade code paths untouched.
- Tests run + result: `verify_changes.py` per unit — driver `47 passed` (incl. the real-chromium fixture test), `pillar2_portfolio` `16 passed`, `handlers` `59 passed`; compileall OK on every step.
- Open questions:
  1. `realized_pnl_today` still uses the legacy selector list (`td:has-text('Realized P/L') + td`) — Realized P/L is **not** in the probed Account Info table. Confirm on the live re-test whether it needs re-targeting (it stays honest `None` today).
  2. `credit_line` is scraped + bound but **not** rendered on the card (handoff item 3 lists only Line Available / EE / Cash balance). Say the word if you want it shown.
  3. The CASH account exposes no `Cash Balance` table row → `real_cash_balance` (and therefore the card row) stays `None` there **by design**.
  4. The chromium fixture test self-skips (with a message) when no ms-playwright build is resolvable; here it ran on the installed chromium (`launch(headless=True)` succeeded).
- `verify_changes.py --full`: **PASS — 575 passed in 167.35s** (final gate, `tests/`).

