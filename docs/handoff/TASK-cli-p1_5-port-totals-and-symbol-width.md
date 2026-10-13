# TASK-cli-p1_5-port-totals-and-symbol-width: ยอดรวมการ์ด /port ให้ตรงกับแอป + ชื่อหุ้นไม่โดนตัด

- Created: 2026-10-14 by Antigravity
- Broker: KSS (TradeMan) ส่วนยอดรวม; การ์ดใช้ร่วมกับ LIB. **ห้ามเอาโค้ดหรือ selector ของโบรกเกอร์หนึ่งไปใช้กับอีกโบรกเกอร์**
- Priority: P1.5 (Low/Med; ไม่ block Round B, แต่ต้องเสร็จก่อนใช้การ์ดตัดสินใจ)
- Status: DONE (code + unit verified; live re-test owned by Antigravity)

## Context (Antigravity เขียน)
Live P1 (2026-10-14 05:34) การ์ด `/port kss sync` ข้อมูลถูกแล้ว (Unrealized P/L ตรงกับแอป, (S)/(B), carousel) แต่ยังเหลือ 2 เรื่อง:
- **CLI-RCA-013**: "มูลค่ารวม" บนการ์ดนับต่างจากแอป
  - การ์ด = Σ(vol×last) **เฉพาะแถว (S)**
  - แอป *Market Value* = ค่าเดียวกัน **+ แถว (B)** (ตัวอย่าง MTC (B) 1,700×28.75)
  - แอป *Amount* = Σ(vol×avg) = ต้นทุน
  - Unrealized ในแอป = Amount − Market(S) ซึ่งการ์ดคำนวณถูกแล้ว ห้ามแตะ
  - **ผู้ใช้เลือก:** ให้แสดง **Amount** และ **Market Value** เหมือนแอป โดยอ่านจาก**ตารางยอดรวมบนหน้าเว็บ**
- **CLI-RCA-012**: ชื่อหุ้นยาวที่มี suffix โดนตัด (`DOHOME …` แทน `DOHOME (S)`)

อ่านก่อนเริ่ม: `rca/shared/rca_line_cli.md` (012, 013 และหัวข้อ "Live re-test P1"), `learned_workflows/krungsri/trademan_portfolio_dom.md` (ตารางหัว / body / ยอดรวม)

## Context map
| # | ไฟล์ / symbol | บรรทัด | สิ่งที่ต้องทำ |
|---|---|---|---|
| 1 | `trademan_driver._PORTFOLIO_TABLES_JS` / `_pair_holdings_tables` | L54-~160 | ให้คืน**ตารางยอดรวม**ด้วย: `table.w-full.h-[2rem]` อยู่ใน container เดียวกับตารางหัว มี 1 แถว ≥8 td; ระบุด้วยตำแหน่งใน container เดียวกัน **ห้ามใช้ global selector** |
| 2 | `trademan_driver.scrape_portfolio` | L658-~810 | อ่าน cell ยอดรวมตาม**ตำแหน่งคอลัมน์ของตารางหัว** (`_map_holdings_columns`): `Cost` → `amount`, `Market Value` → `market_value`, `Unreal` → `unrealized_pnl`; parse ไม่ได้ / ว่าง → `None`; เก็บไว้ที่ `self.portfolio_totals = {"amount", "market_value", "unrealized_pnl", "account_no"}`; คืนค่าแบบ `List[Dict]` เหมือนเดิม |
| 3 | `handlers._portfolio_totals` / `_live_card` (port) | L452-~480 | KSS: ใช้ `trademan_driver.portfolio_totals` ก่อน; ถ้าเป็น `None` → fallback: Amount = Σ(vol×avg) ของแถว SHORT+LONG, Market Value = Σ(vol×last) **ทุกแถวรวม BORROWED**; ถ้าคำนวณไม่ได้ → `—` (ห้ามใส่ 0.0). Unrealized ใช้ logic เดิม. LIB: Market Value = Σ market value, Amount = Σ cost (ถ้ามี), ไม่ต้องใช้ DOM |
| 4 | `cards.port_card` | L196+ (const L166) | หัวการ์ด: แทน `มูลค่ารวม` ด้วย 2 แถว `Amount` และ `Market Value` แล้วตามด้วย `Unrealized P/L` (ลำดับเหมือนแอป); ยังรับ `None` ได้ → `—` |
| 5 | `cards.port_card` แถวหุ้น | ใน L196+ (`_cell` L61) | RCA-012: ชื่อหุ้นต้องไม่โดนตัด → เพิ่ม `flex` ของคอลัมน์ชื่อหุ้น และ/หรือย้าย suffix `(S)`/`(B)` ไปอยู่บรรทัดหรือ span เล็กแยก; ห้ามลดขนาดตัวเลขจนอ่านยาก; test: `DOHOME (S)` ต้องอยู่ครบใน text node และ `wrap` หรือ flex พอสำหรับ 10 ตัวอักษร + suffix |

Verify (ทีละ unit):
- `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py`
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py`
- ปิดงาน: `.venv/bin/python scripts/verify_changes.py --full` ครั้งเดียว ไม่ใส่ timeout

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/browser/trademan_driver.py` (เฉพาะ `_PORTFOLIO_TABLES_JS`, `_pair_holdings_tables`, `scrape_portfolio` ส่วนยอดรวม)
- `app/services/line_cli/handlers.py`, `app/services/line_cli/cards.py`
- tests: `tests/test_trademan_portfolio_scraper.py`, `tests/test_line_cli_flow.py`

## Steps / Task Decomposition (Loop Engineering — บังคับ)
1. ข้อ 1+2: เพิ่มยอดรวมใน fixture HTML (ตารางยอดรวมที่คอลัมน์ Cost/Market Value/Unreal มีค่า) → `portfolio_totals` ต้องอ่านค่าได้ถูก; กรณีตารางยอดรวมว่างหรือไม่มี → `None` ทุก field → verify
2. ข้อ 3: test fallback: แถว SHORT 2 + BORROWED 1 → Market Value รวม BORROWED, Amount ไม่รวม BORROWED (avg 0); ข้อมูลไม่พอ → `None` → verify
3. ข้อ 4: ใบแรกของการ์ดมี `Amount`, `Market Value`, `Unrealized P/L` และไม่มี `มูลค่ารวม` → verify
4. ข้อ 5: test ชื่อหุ้นยาว + suffix ไม่ถูกตัด (ตรวจ JSON ของ Flex) → verify
5. `--full` + Cline Report

## Acceptance / Tests ที่ต้องผ่าน
- verify ทุก unit PASS และ `--full` PASS
- live (Antigravity): `/port kss sync` → Amount และ Market Value ตรงกับแอป (เทียบหน้า Portfolio > Total), Unrealized ยังตรง, `DOHOME (S)` แสดงครบ

## Out of scope / ห้ามแตะ
- สูตร Unrealized P/L และ %P/L ตาม side (ทำเสร็จใน P1 แล้ว)
- ความต่าง %P/L รายแถว 0.02–0.11 จุดที่น่าจะมาจากค่าธรรมเนียม (ยังไม่มีข้อมูล ห้ามเดาสูตร)
- RCA-011 การ์ดเงินสด / EE / Account Info (รอ probe)
- การส่ง/แก้/ยกเลิกคำสั่ง, tick size, การตรวจราคา/จำนวน
- ห้ามยิง OTP, ห้ามรัน live, ห้ามรีสตาร์ท gateway; test ห้ามแตะ `data/session_state.json` (F-10)

## Open questions (Antigravity)
- Q1: ตารางยอดรวมบนเว็บนับแถว (B) รวมใน Market Value เหมือนแอปมือถือไหม → ตรวจตอนทดสอบ live; ถ้าไม่ตรง Antigravity จะออก follow-up

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/browser/trademan_driver.py` — `_PORTFOLIO_TABLES_JS` + `cls`; new `_parse_float_or_none()` (blank/`-` → `None`); new `_find_totals_row()` (summary table = single ≥8-td row after the holdings pair, matched by `h-[2rem]` class **or** a totals token; an unlabelled single-row table is refused); `_pair_holdings_tables()` returns `pair["totals"]`; `__init__` gains `portfolio_totals` (reset to `None` at the start of every `scrape_portfolio`, filled from the summary row via the header column positions `Cost/Market Value/Unreal` + `account_no`)
  - `app/services/line_cli/handlers.py` — new `_portfolio_amount()` (Σ vol×avg, BORROWED excluded, `None` when no cost base); `_live_card` (port) reads `trademan_driver.portfolio_totals` **only for KSS/TRADEMAN** and only when the cell is not `None`, else falls back to computed Amount / Market Value; `_handle_read` (DB snapshot) passes `amount` + `market_value`; `port_card` call-sites use the new kwargs (`total_value` removed)
  - `app/services/line_cli/cards.py` — new `_money()` (`None` → `—`); `_cell()` gains `wrap`; `port_card(amount, market_value, ...)` header rows are `Amount` / `Market Value` / `Unrealized P/L` (legacy `มูลค่ารวม` gone), `altText` uses `_money`; RCA-012: `_port_header_row`/`_port_row` symbol `flex 3→4` + `wrap=True`, qty `flex 3→2` (number size stays `xs`)
  - tests: `tests/test_trademan_portfolio_scraper.py` (fixture totals row now carries Cost/Market Value/Unreal + `cls`; `portfolio_totals` added to the isolation fixture; 7 new tests), `tests/test_line_cli_flow.py` (2 call-sites updated; 6 new tests + the unavailable-card assertion extended to `Amount`)
  - docs: `learned_workflows/krungsri/trademan_portfolio_dom.md` (rule 4b + new "Totals row → `portfolio_totals`" section + RCA-012 note), `rca/shared/rca_line_cli.md` (new "Proven fix — 2026-10-14 (Cline, TASK-cli-p1_5…)": CLI-RCA-012/013 + invariants)
- Summary:
  - Unit 1 (driver): `_find_totals_row()` identifies the on-page summary table **by position inside the holdings group** (never a global `table` selector). `scrape_portfolio` stores `{"amount" (Cost), "market_value", "unrealized_pnl", "account_no"}`; unreadable cells stay `None` (never `0.0`) and the dict is cleared at the start of every scrape so a failed scrape cannot leak the previous account's figures.
  - Unit 2/3 (handlers + card): KSS/TRADEMAN prefer the DOM row, LIB is untouched (broker isolation). Fallback = Amount Σ(vol×avg) of non-BORROWED rows, Market Value Σ(vol×last) **including** `(B)` rows. Card header now mirrors the app (`Amount`, `Market Value`, `Unrealized P/L`) and renders `—` when a figure is unknown.
  - Unit 4 (RCA-012): symbol column widened to `flex=4` + `wrap=True` (qty yields to `flex=2`) — `DOHOME (S)` stays in one text node and wraps instead of clipping; the raw detector's other pages use the same helper so both bubbles agree.
  - Unrealized P/L + per-side `%P/L` logic untouched (P1); `portfolio_totals["unrealized_pnl"]` is stored but not used for rendering (handoff says keep the P1 formula).
- Tests run + result:
  - `scripts/verify_changes.py app/browser/trademan_driver.py tests/test_trademan_portfolio_scraper.py` → PASS (45 targeted)
  - `scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py tests/test_line_cli_flow.py` → PASS (48 targeted)
  - `scripts/verify_changes.py --full` → **PASS (544 passed, 1 warning, 162 s)** — run once at close, no timeout, no SQLite lock hang
  - One self-anneal during Unit 1: my first `_find_totals_row()` returned the best candidate unconditionally, so an unlabelled single ≥8-td row was claimed as the portfolio total. Fixed by requiring the `h-[2rem]` class **or** a totals token; `test_find_totals_row_ignores_unlabelled_single_row_table` guards it.
- Open questions:
  1. **Live confirmation (Antigravity)** — does the web summary table's *Market Value* really include the `(B)` rows (MTC 1,700×28.75) like the mobile app? If it does not, the card now follows the page, and the follow-up belongs to the totals-row definition, not the CLI (out-of-scope to guess here).
  2. `portfolio_totals["unrealized_pnl"]` is scraped but unused by the card (handoff: keep the P1 side-aware formula). Say the word if you want the card to show the page's own Unreal instead.
  3. **Live symbol marker** — RCA-012 assumes the live cell is `DOHOME (S)`. The wrapper now fits ~12 characters; if a real ticker+suffix is longer than that, the next step is a smaller suffix span, not a narrower number column.
  4. Pending user decision (from P1): commit P1 + P1.5 together or as two commits. Nothing is committed yet.
