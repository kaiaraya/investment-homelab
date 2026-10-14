# TASK-cli-p2a-cash-honest-mapping: `/cash kss` ผูกค่ากับบัญชีที่อ่านได้จริง + สคริปต์ probe Account Info

- Created: 2026-10-14 by Antigravity (after grill-me/plan 07:13–07:22, user-approved)
- Broker: KSS (TradeMan) เท่านั้น. **การ์ด LIB/C2W ห้ามเปลี่ยน** (broker isolation)
- Priority: P2a (ส่วนที่ทำก่อนตลาดเปิด) ของ CLI-RCA-011 (High) — ส่วน selector จริง + live = P2b (Antigravity)
- Status: P2a DONE (Cline, 2026-10-14 — code + unit + `--full` PASS); P2b (real selectors + live) = Antigravity

## Context (Antigravity เขียน)
Live P1 พบว่า `/cash kss sync` แสดงตัวเลขเดียว (= Line Available ของบัญชี MARGIN) เป็นทั้ง `Cash balance` และ `Buying power` ใต้หัวการ์ด `CASH` และไม่มีค่า EE
สาเหตุมี 3 ข้อ:
- selector ของ `cash_balance` ใน driver (`trademan_driver.py` ~L2451) ลองหา `Line Available` เป็นตัวแรก ดังนั้น **key `cash_balance` ที่ได้จริงคือ Line Available**
- `portfolio_get_balances` (KRUNGSRI branch ~L400-431) เอาค่านี้ไปใส่ทั้ง `cash_balance` และ `line_available` ของ CASH และเอา `excess_equity` ไปใส่ `line_available` ของ MARGIN
- บัญชีที่ "active" มาจาก `account_context` (state ในหน่วยความจำ) ไม่ใช่จากบัญชีที่เลือกอยู่ใน dropdown ซึ่งเป็นที่มาของตัวเลข

| # | Decision (ล็อกแล้ว) |
|---|---|
| D1 | รอบนี้**ไม่แก้ selector** ของ EE/cash/pnl/equity (รอผล probe ใน P2b) และไม่เปลี่ยนชื่อ key `cash_balance` ใน driver (มี caller อื่นอีก 5 จุด) |
| D2 | driver คืน `account_no` ที่อ่านจาก dropdown ผ่าน `_read_current_account_no` (พิสูจน์แล้วใน RCA-006a) แล้ว pillar2 ใส่ค่าให้**เฉพาะบัญชีที่เลขตรงกัน** ถ้าอ่านเลขไม่ได้หรือเลขไม่ตรง ทั้ง 2 บัญชีได้ค่า None → การ์ดขึ้น "อ่านไม่ได้" |
| D3 | การ์ด KSS: หัวการ์ด = ประเภทของบัญชีที่ผูกค่าได้ · แถว `Line Available` · MARGIN เพิ่มแถว `Excess Equity` (ค่า หรือ `—`) · **ไม่มี** แถว `เงินสด / Cash balance` และ `กำลังซื้อ / Buying power` |
| D4 | สคริปต์ probe อยู่ใน repo: `scripts/krungsri/probe_account_info.py` มี pure `sanitize()` + unit test + mapping · ผลลัพธ์เขียนที่ `data/probe_out/` (อยู่ใน .gitignore) |

อ่านก่อนเริ่ม: `rca/shared/rca_line_cli.md` (CLI-RCA-011), `learned_workflows/krungsri/trademan_portfolio_dom.md` (dropdown / account switch)

## Context map
| # | ไฟล์ / symbol | สิ่งที่ต้องทำ |
|---|---|---|
| 1 | `app/browser/trademan_driver.py` `scrape_account_summary` (L2387-2486), `_unreadable_summary` | หลังเช็ก `_is_authenticated_page` ให้ใส่ `summary["account_no"] = await self._read_current_account_no(page)` (เป็น None ได้) · `_unreadable_summary()` เพิ่ม `"account_no": None` · ใส่ comment ที่ selector cash ว่า "value is Line Available (selector order), see CLI-RCA-011" · **ห้ามแตะ selector และ path dry-run** |
| 2 | `app/mcp/pillars/pillar2_portfolio.py` `portfolio_get_balances` KRUNGSRI branch | ผูกค่าตามเลขบัญชี (ดู diff ด้านล่าง) · `is_active` ยังมาจาก `account_context` เหมือนเดิม · response เพิ่ม `scraped_account_no` |
| 3 | `app/services/line_cli/handlers.py` cash branch ของ `_live_card` (~L604-625) | แยกโค้ดตาม broker: **KSS/TRADEMAN** ใช้กฎ D3 · **LIB ใช้โค้ดเดิมทุกบรรทัด** |
| 4 | `app/services/line_cli/cards.py` `cash_card` (L284) | น่าจะไม่ต้องแก้ (รับ rows อยู่แล้ว) ถ้าต้องแก้ให้แก้แบบที่ LIB ยังได้ผลเหมือนเดิม |
| 5 | `scripts/krungsri/probe_account_info.py` [NEW] | ดูข้อกำหนด probe ด้านล่าง |
| 6 | `scripts/verify_changes.py` `MODULE_TEST_MAP` | เพิ่ม `"scripts/krungsri/probe_account_info.py": ["tests/test_probe_account_info.py"]` |

diff ที่ต้องการ (pillar2):
```diff
-        cash_acc = { ..., "line_available": balances.get("cash_balance"),
-                          "cash_balance": balances.get("cash_balance"), ... }
-        margin_acc = { ..., "excess_equity": balances.get("excess_equity"),
-                            "line_available": balances.get("excess_equity"),
-                            "cash_balance": balances.get("cash_balance"), ... }
+        scraped_no = balances.get("account_no") if isinstance(balances, dict) else None
+        def _bind(acc):
+            bound = scraped_no is not None and str(scraped_no) == str(acc["account_no"])
+            acc["values_bound"] = bound
+            # CLI-RCA-011: driver key "cash_balance" is really Line Available (selector order).
+            acc["line_available"] = balances.get("cash_balance") if bound else None
+            acc["cash_balance"] = None          # not scraped honestly yet -> P2b
+            acc["excess_equity"] = balances.get("excess_equity") if bound else None
+            return acc
+        cash_acc, margin_acc = _bind(cash_acc), _bind(margin_acc)
+        ... "scraped_account_no": scraped_no,
```

กฎการ์ด KSS (handler):
```python
acc = next((a for a in accounts if a.get("values_bound") is True), None)
if res.get("authenticated") is False or acc is None or acc.get("line_available") is None:
    return cards.unavailable_card(...)      # "—" alone never counts as readable
rows = [{"label": "Line Available", "value": f"{float(acc['line_available']):,.2f}"}]
if acc.get("account_type") == "MARGIN":
    ee = acc.get("excess_equity")
    rows.append({"label": "Excess Equity", "value": f"{float(ee):,.2f}" if ee is not None else "—"})
# title: _account_type_label(acc["account_type"])
```

## ข้อกำหนดสคริปต์ probe (`scripts/krungsri/probe_account_info.py`)
- Antigravity จะรันเองตอนตลาดเปิดพร้อมผู้ใช้ (P2b) **Cline ห้ามรัน** ตรวจแค่ compile + unit test
- เปิด Chromium แบบ headed ด้วย `executable_path=settings.PLAYWRIGHT_CHROME_EXECUTABLE`
- `browser.new_context(storage_state=settings.SESSION_STATE_PATH)` เป็นการอ่านอย่างเดียว **ห้ามเรียก `context.storage_state(path=...)` หรือเขียนไฟล์ session ใด ๆ** (Invariant 8)
- ไปที่หน้า `/Portfolio` แล้วปิด popup และ**รอ `input()` (Enter) ระหว่างทุกขั้น**
- ถ้า session หมดอายุ (เจอหน้า SignIn): พิมพ์บอกให้ผู้ใช้ login เองในหน้าต่าง แล้วรอ Enter **ห้ามมี auto-login, ห้ามยิง OTP**
- วนทีละบัญชี (`settings.TRADEMAN_ACCOUNT_NO_CASH`, `settings.TRADEMAN_ACCOUNT_NO_MARGIN`)
  - เลือกบัญชีผ่าน `#dropDownAccountPort div.absolute span:text-is("<acc>")`
  - dump แถบล่าง → คลิก chevron เพื่อขยาย Account Info → dump อีกครั้ง
- label ที่ต้องหา (ทั้งไทยและอังกฤษ): Trading A/C, Credit Limit, Line Available, Excess Equity, Margin Required, %MM, Cash Balance
  - เก็บทุก label ที่เจอในแผง ไม่ใช่แค่ใน list นี้
- **คลิกได้แค่ 2 อย่าง: dropdown เลือกบัญชีกับ chevron** ห้ามมีโค้ด order / amend / cancel / login
- pure `sanitize(items: list[dict]) -> list[dict]` (import playwright ภายใน `main()` เท่านั้น)
  - คืน `{label, selector_path, value_shape}` โดย `value_shape` เป็น `"#,###.##"` / `"-#,###.##"` / `"#.##%"` / `"empty"` / `"text"`
  - **ห้ามมีตัวเลขเงินจริงหลุดออกมา**
- เขียนผลที่ `data/probe_out/account_info_<CASH|MARGIN>_<YYYYmmdd-HHMM>.json` ห้ามใส่เลขบัญชีในชื่อไฟล์หรือเนื้อหา (ใช้แค่ประเภทบัญชี)

## Steps / Task Decomposition (Loop Engineering — บังคับ)
1. driver: `account_no` ใน summary + `_unreadable_summary` → test (mock page: dropdown อ่านได้ → มี account_no; อ่านไม่ได้ → None) → verify
2. pillar2: `_bind` + tests ใน `tests/test_remote_mcp.py`
   - (a) account_no ตรงกับ MARGIN → ค่าอยู่ที่ MARGIN อย่างเดียว ส่วน CASH ทุกฟิลด์เป็น None
   - (b) account_no None → ทั้ง 2 บัญชีเป็น None และ `values_bound` เป็น False
   - (c) `cash_balance` ของทุกบัญชีเป็น None
   - test เดิมที่ L262/L463 ต้องผ่าน
   - → verify
3. handler: การ์ด KSS + tests ใน `tests/test_line_cli_flow.py`
   - (a) MARGIN ผูกค่าได้ + EE None → มี `Line Available`, `Excess Equity` คู่กับ `—`, หัวการ์ดเป็น Margin และ**ไม่มี** `Buying power` / `Cash balance`
   - (b) ไม่มีบัญชีไหนผูกค่าได้ → `อ่านไม่ได้` และไม่มี `🟢 live`
   - (c) CASH ผูกค่าได้ → ไม่มีแถว EE
   - (d) test การ์ด LIB เดิม (~L828) ผ่านโดยไม่แก้
   - test KSS เดิมที่ L505/L526 ต้องผ่าน (ถ้าต้องเพิ่ม `values_bound` ใน fixture ทำได้ แต่ห้ามลด assertion)
   - → verify
4. probe script + `tests/test_probe_account_info.py`
   - sanitize ต้องไม่มีตัวเลขเงินหลุด · `%` ได้ shape ที่ถูก · label ไทย/อังกฤษยังอยู่ครบ · import module ได้โดยไม่ต้องมี playwright หรือ browser
   - เพิ่ม mapping
   - → verify
5. docs + `--full` + Cline Report

Verify:
- รายหน่วย: `.venv/bin/python scripts/verify_changes.py <changed files>`
- ปิดงาน: `.venv/bin/python scripts/verify_changes.py --full` ครั้งเดียว ไม่ใส่ timeout

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/browser/trademan_driver.py` (เฉพาะ `scrape_account_summary` / `_unreadable_summary`)
- `app/mcp/pillars/pillar2_portfolio.py` (เฉพาะ KRUNGSRI branch ของ `portfolio_get_balances`)
- `app/services/line_cli/handlers.py` (cash branch), `app/services/line_cli/cards.py` (ถ้าจำเป็น)
- `scripts/krungsri/probe_account_info.py` [NEW], `scripts/verify_changes.py` (mapping 1 บรรทัด)
- tests: `tests/test_remote_mcp.py`, `tests/test_line_cli_flow.py`, `tests/test_sbl_account_driver.py` หรือ `tests/test_trademan_portfolio_scraper.py`, `tests/test_probe_account_info.py` [NEW]
- docs:
  - `rca/shared/rca_line_cli.md`: RCA-011 → "Partial fix P2a — honest binding; selectors pending P2b"
  - `learned_workflows/krungsri/trademan_portfolio_dom.md`: note ว่า key `cash_balance` = Line Available และลิงก์ไปที่ probe

## Acceptance
- verify PASS ทุกหน่วย, `--full` PASS
- ไม่มีทางที่ตัวเลขเดียวจะไปแสดงพร้อมกันใน 2 แถวของการ์ด KSS
- ไม่มีทางที่ค่าจากบัญชีหนึ่งจะไปแสดงใต้หัวการ์ดของอีกบัญชี
- การ์ด LIB เหมือนเดิมทุกอย่าง
- สคริปต์ probe ไม่มีโค้ดที่เขียน session และไม่มีโค้ด order/login/OTP (Antigravity จะ grep ตรวจ)

## Out of scope / ห้ามแตะ
- selector ของ EE / cash / realized P/L / total equity (P2b)
- การเปลี่ยนชื่อ key `cash_balance` ใน driver และ caller อื่น (`live_probe.py`, `krungsri/cli.py`, `krungsri/plugin.py`, `eod_service.py`, `mcp_server.py`)
- การสลับบัญชีอัตโนมัติตอน `/cash sync` · path dry-run · การ์ด/โค้ดของ LIB และ C2W
- การส่ง/แก้/ยกเลิกคำสั่ง, tick size, OTP
- ห้ามรัน live, ห้ามรันสคริปต์ probe, ห้ามรีสตาร์ท gateway
- test ห้ามแตะ `data/session_state.json` (F-10)

## Open questions (Antigravity)
- dry-run: summary ไม่มี `account_no` → `/cash kss` ในโหมด dry-run จะขึ้น "อ่านไม่ได้" ผู้ใช้รับได้ (ไม่ต้องแก้ในรอบนี้)
- ถ้า dropdown โหลดช้า `_read_current_account_no` อาจคืน None บ่อย จะดูผลจริงตอน live ใน P2b

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/browser/trademan_driver.py` — `scrape_account_summary` (summary now carries `account_no` via `_read_current_account_no`), `_unreadable_summary` (`account_no: None`), comment on the cash-selector block (value = Line Available, key name + selector order untouched)
  - `app/mcp/pillars/pillar2_portfolio.py` — KRUNGSRI branch of `portfolio_get_balances`: `_bind()` + `values_bound` + `scraped_account_no`; `cash_balance` always `None`; `line_available`/`excess_equity` only for the matched account
  - `app/services/line_cli/handlers.py` — `_live_card` cash: explicit KSS/TRADEMAN branch (D3 rows, `unavailable_card` when nothing is bound); LIB path left verbatim
  - `scripts/krungsri/probe_account_info.py` [NEW] — read-only Account Info probe + pure `sanitize()`
  - `scripts/verify_changes.py` — 1-line `MODULE_TEST_MAP` entry for the probe
  - tests: `tests/test_sbl_account_driver.py`, `tests/test_remote_mcp.py`, `tests/test_line_cli_flow.py`, `tests/test_probe_account_info.py` [NEW]
  - docs: `rca/shared/rca_line_cli.md` (RCA-011 marked partial P2a + new "Proven fix P2a" section), `learned_workflows/krungsri/trademan_portfolio_dom.md` (new section: `cash_balance` = Line Available + P2a binding + probe link)
- Summary: A figure can no longer be shown under the wrong account header. The driver reports the
  account number it actually read off the dropdown (`None` when unreadable); pillar2 binds the scraped
  figures to that number only (`values_bound`), leaves every other account `None`, and never exposes a
  `cash_balance` (the driver key is really Line Available until P2b). The KSS card renders only the bound
  account — `Line Available` + (`MARGIN` only) `Excess Equity` (value or `—`) — and shows `อ่านไม่ได้`
  (no 🟢 live) when nothing is bound, unreadable, or unauthenticated. LIB is byte-for-byte unchanged.
  No selector, URL, or key name was touched (D1). `cards.py` needed no change.
- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py` → **PASS** (46 passed)
  - `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py` → **PASS** (16 passed)
  - `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py` → **PASS** (57 passed)
  - `.venv/bin/python scripts/verify_changes.py scripts/krungsri/probe_account_info.py scripts/verify_changes.py` → **PASS** (23 passed)
  - `.venv/bin/python scripts/verify_changes.py --full` → **PASS** (562 passed in 161.7s; P1.6 baseline was 549 → +13 new tests, exactly the number added)
  - One FAIL on the first probe run was self-inflicted: the source-grep guard rejected my own docstring
    wording (`storage_state(path=...)`); the docstring was reworded, not the guard.
- Open questions:
  - `data/probe_out/` is covered by the existing `data/` gitignore rule — no `.gitignore` edit needed.
  - `ACCOUNT_INFO_CHEVRON_SELECTOR` in the probe is a placeholder (`button[aria-label*='Account Info' i], #accountInfoChevron`);
    P2b must confirm it live (the handoff's advisory note #1) — it is a single file-top constant on purpose.
  - P2b still owns: real Account Info selectors (+ chevron), a real cash/P&L selector so
    `cash_balance` stops being `None`, and the live `/cash kss sync` re-test.
  - Handoff line refs were slightly stale (L505/526/828 vs actual L504/523/820) — harmless; all cited
    symbols exist and behave as described.

