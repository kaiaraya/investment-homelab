# TASK-sq5: QuickTrade Last Price อ่านจาก DOM ไม่ได้ (`last=None` → SHORT โดน NO_QUOTE)

- Created: 2026-10-19 by Argon (side-quest, T0)
- Status: READY (Probe DONE — เห็น DOM สดแล้ว)
- Tier: 🟢 T0 — local fix + triage (Cline lane) หรือ Jules `3.6 Flash`
- Owner: local implementer → Cline Triage → Human merge
- Blocks: `TASK-loop1-4` ขั้น 3 (กรณี SHORT) — G6 uptick ต้องมี `last`
- Source: SQ-4 live probe (2026-10-19 ~11:35, ตลาดเปิด)

## Context (หลักฐานสด)

หลังแก้ปุ่ม Get Quotes (SQ-4) แล้ว `get_quote()` คืน bid/offer ได้จริง แต่ `last` ยังเป็น `null`:

```
PTTEP -> {"best_bid": 155.5, "best_offer": 156.0, "last": null, ...}
BCPG  -> {"best_bid": 6.70,  "best_offer": 6.75,  "last": null, ...}
```

DOM จริงของ `#instInfoEq` คือ:

```html
<td rowspan="2" class="price bgwhite"><h2>
  <span class="last" style="color:...">156.00</span>
</h2></td>
...
Vol./Value(K) | High/Low | Ceil./Floor | Avg./Close | Open 1
```

**ไม่มี label คำว่า "Last" ในข้อความ** — `parse_market_info()` จึงคืน `None` ตามนโยบาย anti-mock (ถูกต้องที่ไม่เดา) แต่ผลคือ `compute_passive_price()` ฝั่ง SHORT คืน `NO_QUOTE` เพราะต้องมีทั้ง offer และ last:

```
BCPG SHORT @6.80 -> NO_QUOTE | "best offer and last price are both required for a short amendment"
```

## Scope

1. `app/brokers/krungsri/quicktrade_driver.py` → `_JS_QUOTE`: เพิ่ม `last_text` จาก `#instInfoEq .last` (span.last ในตาราง quote)
2. `_fetch_quote()`: ใช้ค่าจาก `last_text` ก่อน (parse เป็น float) แล้ว fallback ไป `parse_market_info(info_text)` — **ห้ามเดาจาก Avg./Close** (anti-mock เดิม)
3. `tests/test_quicktrade_driver.py`: เพิ่มเคส `last_text` + คงเคส label "Last" เดิมเป็น fallback
4. `learned_workflows/krungsri/quicktrade_native_change_order.md`: เพิ่มหมายเหตุว่า last อยู่ใน `span.last` ไม่มี label

## ห้ามแตะ
- amend/PIN/submit flow · `plan_negotiation` · guardrails G4–G6
- ห้ามใช้ Avg./Close แทน Last เด็ดขาด (จะทำให้ uptick ผิด)

## Verification

```bash
.venv/bin/python -m pytest tests/test_quicktrade_driver.py -q
.venv/bin/python scripts/verify_changes.py app/brokers/krungsri/quicktrade_driver.py tests/test_quicktrade_driver.py
```

Live read-only:

```bash
.venv/bin/python - <<'PY'
import asyncio, json
from app.brokers.krungsri.quicktrade_driver import quicktrade_driver
async def main():
    for s in ("PTTEP","BCPG"):
        print(s, json.dumps(await quicktrade_driver.get_quote(s), ensure_ascii=False))
asyncio.run(main())
PY
```

**PASS เมื่อ:** `last` เป็นตัวเลขจริงทั้ง 2 ตัว และตรงกับ `span.last` บนหน้าจอ

## Done when
- Unit test ผ่าน · live probe ได้ last จริง · merge + restart gateway ก่อน witness ขั้น 3

---

## Cline Report
- Git Commit(s): `65cc9a9` (branch `task/sq4-sq5-quicktrade-quote-path`)
- Files changed: `app/brokers/krungsri/quicktrade_driver.py` (`_JS_QUOTE` + `_fetch_quote`) · `tests/test_quicktrade_driver.py` · runbook
- Summary: `_JS_QUOTE` เพิ่ม `last_text` จาก `#instInfoEq .last`; `_fetch_quote()` ใช้ `last_text` ก่อนแล้ว fallback `parse_market_info()`; ไม่เดาจาก Avg./Close
- Tests run + result: **25 passed** (เพิ่ม 2 เคส: span.last precedence · ไม่เดา last จาก Avg./Close)
- Live verification: **PENDING** — ตอน 11:47 storage_state ถูก SSO เด้งไปหน้า login จึงยังยืนยันค่า `last` สดไม่ได้; ต้อง `/login kss` ใหม่แล้วรัน probe ซ้ำก่อน witness
- Open questions: **SSO session clone** — `quicktrade_driver` เปิด browser ใหม่ทุก method ด้วย `storage_state`; หลังใช้งานหลายรอบเซสชันถูกเด้ง login ทำให้ `/nego` อาจ fail กลาง flow (order → quote → amend เปิด 3 contexts) · ต้องทดสอบซ้ำทันทีหลัง login ใหม่ และอาจต้องย้าย quicktrade ให้ใช้ browser เดียวกับ gateway ใน Loop ถัดไป

## Verification & Stepwise Approval
- [x] Stage A (Code Audit) · [x] Stage B (Verify) · [ ] Stage C (Live) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS (unit) — live pending หลัง login ใหม่
