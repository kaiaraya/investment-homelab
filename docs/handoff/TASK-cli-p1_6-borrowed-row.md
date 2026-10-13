# TASK-cli-p1_6-borrowed-row: การ์ด /port แสดง Amount + หุ้นยืมคงเหลือ (B)

- Created: 2026-10-14 by Antigravity (revised after grill-me 06:20; ทับฉบับ "ทางที่ 3" ที่ยังไม่ได้ส่ง)
- Broker: KSS (TradeMan) สำหรับส่วน (B); การ์ดใช้ร่วมกับ LIB. **ห้ามเอา logic ของ (B) ไปใช้กับ LIB**
- Priority: P1 (เล็ก)
- Status: DONE (2026-10-14, Cline) — code + unit verified; live re-test owned by Antigravity

## Context (Antigravity เขียน)
Live P1.5 (2026-10-14 06:10): `Market Value` บนการ์ดอ่านจากตารางยอดรวมบนเว็บ (นับเฉพาะ (S)) ซึ่งไม่ตรงกับแอปมือถือที่นับรวม (B)
ผู้ใช้ตัดสินใหม่ว่า**ไม่สนใจ Market Value** เพราะสุดท้ายต้องคืนหุ้นยืมตามจำนวนอยู่แล้ว สิ่งที่ต้องการ:

| # | Decision (ล็อกแล้ว) |
|---|---|
| D1 | ใบแรกแสดงแค่ `Amount` + `Unrealized P/L` **ไม่มี Market Value**. Amount: ใช้ `trademan_driver.portfolio_totals["amount"]` (จากตารางยอดรวมบนเว็บ) → ถ้าเป็น None คำนวณ `_portfolio_amount()` (Σ vol×avg, ไม่รวม BORROWED) → ถ้าเป็น None อีกให้แสดง `—`. Unrealized ใช้สูตร P1 เดิม |
| D2 | ย้ายแถว (B) **ออกจากตารางหุ้นหลัก** (ตารางเหลือ SHORT/LONG/UNKNOWN) แล้วแสดงเป็นหัวข้อ `หุ้นยืมคงเหลือ (B)` ในใบแรก ใต้ Unrealized P/L |
| D3 | แต่ละตัวแสดงเป็น `MTC  1,700 หุ้น` **ไม่มีจำนวนเงิน**; ไม่แสดงตัวที่ volume = 0 (เช่น BCPG (B)); ถ้าไม่มีเลย → ไม่แสดงหัวข้อ |

อ่านก่อนเริ่ม: `rca/shared/rca_line_cli.md` (RCA-013 + "Live re-test P1.5"), `learned_workflows/krungsri/trademan_portfolio_dom.md` (ส่วน card rendering)

## Context map
| # | ไฟล์ / symbol | สิ่งที่ต้องทำ |
|---|---|---|
| 1 | `app/services/line_cli/handlers.py` ฟังก์ชันใหม่ `_split_borrowed(rows)` | คืน `(main_rows, borrowed)`: `main_rows` = แถวที่ `position_type != "BORROWED"`; `borrowed = [{"symbol", "volume"}]` เฉพาะ BORROWED ที่ volume > 0 เรียงตามชื่อหุ้น |
| 2 | `handlers._live_card` (port) + `_handle_read` (snapshot) | เรียก `_split_borrowed`; ส่ง `rows=main_rows`, `borrowed=borrowed` (เฉพาะ KSS/TRADEMAN; LIB → `[]`); **เลิกส่ง `market_value`**; Unrealized/%P/L คำนวณเหมือนเดิม (BORROWED ไม่มีผลอยู่แล้ว) |
| 3 | `app/services/line_cli/cards.py` `port_card` | ลบพารามิเตอร์ `market_value` และแถว `_kv("Market Value", …)`; เพิ่ม `borrowed: Optional[List[Dict]] = None` → ถ้ามีรายการ ให้ต่อหลัง `Unrealized P/L`: หัวข้อ `_cell("หุ้นยืมคงเหลือ (B)", MUTED, weight="bold")` + `_kv(symbol, f"{volume:,} หุ้น")` ทีละตัว; altText เปลี่ยนเป็น `📊 {broker} พอร์ต Amount {_money(amount)} ({len(rows)} ตัว)` |
| 4 | driver | **ไม่ต้องแตะ**: `portfolio_totals["market_value"]` เก็บต่อได้ แต่ไม่ต้องใช้ |

ตัวอย่าง diff (cards):
```diff
-    market_value: Optional[float],
+    borrowed: Optional[List[Dict[str, Any]]] = None,
 ...
         _kv("Amount", _money(amount)),
-        _kv("Market Value", _money(market_value)),
         _kv("Unrealized P/L", ...),
+    # + borrowed section (only when non-empty), then separator
```

Verify:
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py tests/test_line_cli_flow.py`
- ปิดงาน: `.venv/bin/python scripts/verify_changes.py --full` ครั้งเดียว ไม่ใส่ timeout

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/handlers.py`, `app/services/line_cli/cards.py`, `tests/test_line_cli_flow.py`
- docs: `rca/shared/rca_line_cli.md` (Proven fix RCA-013 final), `learned_workflows/krungsri/trademan_portfolio_dom.md` (card rendering: เลิกแสดง Market Value, ย้าย (B) ออก)

## Steps / Task Decomposition (Loop Engineering — บังคับ)
1. handlers: `_split_borrowed` + unit test (SHORT 2 + BORROWED vol>0 + BORROWED vol 0 → main 2 แถว, borrowed 1 ตัว) → verify
2. handlers + cards: ต่อสาย `borrowed` เข้าการ์ด และลบ `market_value` → แก้ test เดิมที่ยัง assert `Market Value` (เช่น `test_port_card_header_labels_match_the_app`, `test_live_port_card_prefers_dom_totals_row`, `test_port_card_totals_render_dash_when_the_page_exposed_nothing`) ให้ตรงกับ D1 → verify
3. tests ใหม่: (a) ใบแรกมี `Amount`, `Unrealized P/L`, `หุ้นยืมคงเหลือ (B)`, `MTC`, `1,700 หุ้น` และ**ไม่มี** `Market Value` หรือแถว (B) ในตาราง; (b) ไม่มี BORROWED → ไม่มีหัวข้อ; (c) LIB → ไม่มีหัวข้อ; (d) Amount None → `—` → verify
4. docs + `--full` + Cline Report

## Acceptance
- verify PASS, `--full` PASS
- live (Antigravity): `/port kss sync` ใบแรก → `Amount` + `Unrealized P/L` ตรงกับแอป; หัวข้อ `หุ้นยืมคงเหลือ (B)` มีแค่ `MTC 1,700 หุ้น`; ตารางมีแต่ (S); ไม่มี Market Value

## Out of scope / ห้ามแตะ
- driver / scraper / การอ่านตารางยอดรวม
- สูตร Unrealized / %P/L
- RCA-011 (การ์ดเงินสด / EE), การส่ง/แก้/ยกเลิกคำสั่ง, tick size
- ห้ามยิง OTP, ห้ามรัน live, ห้ามรีสตาร์ท gateway; test ห้ามแตะ `data/session_state.json` (F-10)

## Open questions (Antigravity)
- Amount บนการ์ดรอบ 06:10 ตรงกับแอปไหม: รอผู้ใช้ยืนยันตอนทดสอบ live รอบนี้ (ไม่ block งานนี้)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/services/line_cli/handlers.py` — new `_split_borrowed(rows) -> (main, borrowed)`; `_live_card`(port)
    and `_handle_read`(snapshot) now pass `rows=main_rows, borrowed=…` and no longer pass `market_value`
    (loans gated to `KRUNGSRI`/`TRADEMAN`, LIB → `[]`).
  - `app/services/line_cli/cards.py` — `port_card`: dropped `market_value`, added
    `borrowed: Optional[List[Dict[str, Any]]] = None`; rendered as `หุ้นยืมคงเหลือ (B)` (muted bold) +
    `_kv(symbol, "N หุ้น")` right under `Unrealized P/L`; altText → `📊 {broker} พอร์ต Amount {_money(amount)} (N ตัว)`.
  - `tests/test_line_cli_flow.py` — 5 new tests (`_split_borrowed` ×2, LIB `(B)`-free live card,
    borrowed-section render, no-loans → no heading); updated 6 existing tests that still asserted
    `Market Value` / passed `market_value=`; renamed `…_and_dom_totals_win` →
    `test_portfolio_amount_excludes_borrowed_but_totals_include_it` and
    `test_port_card_tags_side_…` → `test_port_card_tags_short_side_…`.
  - `rca/shared/rca_line_cli.md` — RCA-013 "Live re-test P1.5" closed → new "Proven fix P1.6" section
    (D1/D2/D3 + code/evidence + invariants).
  - `learned_workflows/krungsri/trademan_portfolio_dom.md` — card-rendering + totals-row sections updated
    (main table = `(S)` only; `(B)` section; `market_value` scraped but no longer rendered).
- Summary: first bubble now shows `Amount` → `Unrealized P/L` → (if any) `หุ้นยืมคงเหลือ (B)` with
  `MTC  1,700 หุ้น`; `Market Value` is gone; `(B)` rows left the main holdings table and zero-volume loans
  (BCPG 0) are dropped. Driver/scraper/`portfolio_totals` untouched; P/L formula and `%P/L` `cost_base`
  unchanged (still computed over all rows, where `(B)` contributed 0.0).
- Tests run + result:
  - per unit — `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py tests/test_line_cli_flow.py` → PASS (Unit 1: 50 passed; Unit 2/3: 53 passed)
  - close — `.venv/bin/python scripts/verify_changes.py --full` → **PASS** (`549 passed, 1 warning in 161.88s`; `PASS (full) in 166.8s`). No 87%-hang this run.
- Open questions:
  - Live confirmation still owed (non-blocking, per handoff): `/port kss sync` first bubble — `Amount` vs the
    app's Portfolio > Total, and whether the web totals row's Market Value counted `(B)` (now moot for the
    card, since it is no longer rendered).
  - Snapshot path (`/port all`, merged ledger) maps to platform `LIBERATOR` → no `(B)` section in the
    combined view, same as LIB. Flagged in the plan; not changed here.
