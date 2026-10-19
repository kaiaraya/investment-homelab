# TASK-sq4: QuickTrade Quote Button Selector Drift (`#btnGetQuotes` หายจากหน้า Live)

- Created: 2026-10-19 by Argon (side-quest, T0)
- Status: READY (Probe DONE — มีหลักฐาน DOM สดแล้ว)
- Tier: 🟢 T0 — Jules (`Gemini 3.6 Flash`)
- Owner: Jules → Cline Triage → Human merge
- Blocks: `TASK-loop1-4-live-round-b-witness-verification` ขั้น 3–4 (KSS `/nego`)
- Source: pre-flight probe ของ loop1-4 (2026-10-19 11:0x, ตลาดเปิด)

## Context (หลักฐานสด)

ก่อนรัน witness ขั้น 3 ได้ probe หน้า Quick Trade จริง (storage state จาก `data/session_state.json`, mtime 2026-10-19 11:04) พบว่า:

- หน้าโหลดสำเร็จ: `https://wen062.settrade.com/realtime/fastorder/fastorder.jsp?...txtAccountNo=3024959`
- `#eqQuoteSymbol` = **มี** (1 element) · `#orderBodyEq` = **มี** (1 element)
- `#btnGetQuotes` = **ไม่มี (count 0)** → `quicktrade_driver._fetch_quote()` timeout 30s ที่ `page.click("#btnGetQuotes")`
- DOM จริงของปุ่มคือ: `<input class="refreshQuoteBtn" type="button" value="Get Quotes">` อยู่ใน `<td class="symbol">` เดียวกับ `#eqQuoteSymbol`
- ผลกระทบ: `/nego kss` ทุกครั้งจะ fail ที่ขั้นอ่าน quote (fail-closed ก่อนกด Submit — ไม่มีคำสั่งหลุดถึง broker) ทำให้ขั้น 3–4 ของ Loop 1 รันไม่ได้

`learned_workflows/krungsri/quicktrade_native_change_order.md` ระบุ selector สำรอง `input[value='Get Quotes']` ไว้แล้ว แต่โค้ดไม่ได้ใช้ fallback นี้

## Scope (แก้เฉพาะการอ่าน quote — ห้ามแตะ amend/submit)

1. `app/brokers/krungsri/quicktrade_driver.py` → `_fetch_quote()`:
   - เปลี่ยนการกดปุ่มเป็น **scoped resilient locator** ภายใต้ `<td>` ของ `#eqQuoteSymbol`:
     1. `#eqQuoteSymbol` → `locator("xpath=ancestor::td[1]").locator("input.refreshQuoteBtn")` (ตัวหลัก)
     2. fallback `#btnGetQuotes` (เผื่อ UI เก่ากลับมา)
     3. fallback `input[value='Get Quotes']` — ต้อง scope ให้เป็นปุ่มของ EQ เท่านั้น (หน้าเดียวมีปุ่มซ้ำ 2 ตัว: EQ + Derivatives)
   - ถ้าไม่พบปุ่มใดเลย → raise error ชัดเจน (`QUOTE_BUTTON_NOT_FOUND`) เพื่อให้ `/nego` รายงาน fail-closed ไม่ค้าง 30 วินาที
2. `tests/test_quicktrade_driver.py` → อัปเดต `test_fetch_quote_fills_symbol_and_reads_tables` ให้ยืนยัน selector ใหม่ (และเพิ่มเคส fallback เก่า)
3. `learned_workflows/krungsri/quicktrade_native_change_order.md` → แก้แถว Quote Button ให้ตรง DOM ปัจจุบัน (`input.refreshQuoteBtn` ภายใน td ของ `#eqQuoteSymbol`)

## ห้ามแตะ
- ห้ามแก้ `amend_price`, `_fill_amendment`, PIN flow, `_JS_QUOTE` parser
- ห้ามเปลี่ยน `plan_negotiation` / guardrails G4–G6
- ห้ามแก้ `trademan_driver.get_market_bid_offer` (คนละ path — bid/offer ไม่มีใน REST endpoint นั้นโดยเจตนา)

## Verification

```bash
.venv/bin/python scripts/verify_changes.py \
  app/brokers/krungsri/quicktrade_driver.py tests/test_quicktrade_driver.py
```

Live read-only probe (ห้าม submit):

```bash
.venv/bin/python - <<'PY'
import asyncio, json
from app.brokers.krungsri.quicktrade_driver import quicktrade_driver
async def main():
    for s in ("PTTEP", "BCPG"):
        print(s, json.dumps(await quicktrade_driver.get_quote(s), ensure_ascii=False)[:300])
asyncio.run(main())
PY
```

**PASS เมื่อ:** `success=True` และ `best_bid`/`best_offer`/`last` เป็นตัวเลขจริงทั้ง 2 ตัว (เทียบกับหน้าจอ Quick Trade ด้วยตา)

## Done when
- Unit test ผ่าน + live probe ได้ bid/offer จริง
- Cline Triage PASS → human merge → restart gateway (ทำก่อนเริ่ม witness ขั้น 3)
- แจ้ง Argon เพื่อปลดบล็อก `TASK-loop1-4` ขั้น 3–4

---

## Cline Report
- Git Commit(s): `65cc9a9` (branch `task/sq4-sq5-quicktrade-quote-path`)
- Files changed: `app/brokers/krungsri/quicktrade_driver.py` · `tests/test_quicktrade_driver.py` · `learned_workflows/krungsri/quicktrade_native_change_order.md` · `docs/handoff/TASK-sq4...` · `docs/handoff/TASK-sq5...` · `docs/board/loop_board.md`
- Summary: `_fetch_quote()` เลือกปุ่มแบบ fallback 3 ชั้น (`td:has(#eqQuoteSymbol) input.refreshQuoteBtn` → `#btnGetQuotes` → `input[value='Get Quotes']`, timeout 3s/ครั้ง) และ raise `QUOTE_BUTTON_NOT_FOUND` แบบ fail-fast; unit test อัปเดต + เพิ่มเคส fallback/fail-fast
- Tests run + result: `pytest tests/test_quicktrade_driver.py` → **25 passed** · `verify_changes.py` → **PASS (targeted)**
- Live probe: **PASS** — `get_quote("PTTEP")` → bid 155.5 / offer 156.0; `get_quote("BCPG")` → bid 6.70 / offer 6.75 (2026-10-19 ~11:22–11:35, ตลาดเปิด)
- Open questions: หลัง probe หลายรอบ storage_state เริ่มถูก SSO เด้งไปหน้า login (ดู SQ-5 report) — ต้อง `/login kss` ใหม่ทันทีก่อนรัน witness

## Verification & Stepwise Approval
- [x] Stage A (Code Audit) · [x] Stage B (Verify) · [x] Stage C (Live probe read-only) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS (unit + live quote path) — รอ human merge
