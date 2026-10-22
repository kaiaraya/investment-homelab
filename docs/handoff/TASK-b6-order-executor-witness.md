# TASK-b6 — Order executor (execute_order_via_cdp): LIVE witness passed (order 11010191)

**Status:** CODE_DONE · DRY_RUN_VERIFIED (live tabs) · **LIVE WITNESS PASSED 2026-10-21 10:18** —
order **11010191** (`TU Cover 12.60 × 3,100`, `Queuing(O)`) recorded as
`CDP-KRUNGSRI-11010191`, `source=bot_cdp`
**Date:** 2026-10-21 ~10:2x (+07)
**Card:** B.6 (T2 — LIVE MONEY, ห้าม auto-dispatch)
**File:** `app/services/broker_cdp/order_executor.py` (+ `tests/test_broker_cdp_order_executor.py`)

---

## 1. What was built

`execute_order_via_cdp(broker, side, symbol, volume, price, *, pin, account_no,
last_trade_price, dry_run, bypass_dry_run, record)` — the only gateway code allowed to
move money. Exact sequence:

```
kill-switch (G1)
  → normalise side (B/S/H/C ⇄ BUY/SELL/SHORT/COVER)
  → validator.validate_all  (odd-lot · SET tick · value ceiling · strict short uptick G6 · idempotency)
  → SHORT: SBL borrow-lot check (sbl_borrow_lots ACTIVE remaining_qty ≥ volume)
  → PIN present (KRUNGSRI_PIN / LIBERATOR_PIN, 6 หลัก)
  → DRY_RUN guard   ★ หลัง validate ก่อนแตะตั๋ว
  → manager.get_tab (per-(broker,target) lock + tab resolve)
  → account switch + verify (SHORT/COVER → 3024959 margin; header re-read)
  → ledger snapshot ก่อนส่ง (ถ้าอ่านไม่ได้ = ไม่ส่ง)
  → fill side → symbol → volume → price → PIN
  → Anti-DW read-back (symbol/volume/price ต้องตรงเป๊ะ ไม่ตรง = abort ก่อน submit)
  → Submit → confirm modal (ถ้ามี)
  → อ่านเลขออเดอร์ใหม่จาก ledger (4 ครั้ง × 1.2s, ต้องเป็นแถวใหม่ที่ match symbol+side+vol+price)
  → บันทึก `orders` (status=SUBMITTED, source='bot_cdp') → `sync_orders_from_cdp(broker)` (นอก lock)
```

Helper `execute_confirmed_order(draft)` map payload จาก B.5 (`trade_draft_confirm` →
`{cmd, symbol, volume, price, broker, account, account_no}`) → `execute_order_via_cdp`.
**ยังไม่ต่อเข้า webhook** (การต่อ postback → executor เป็น change ที่ต้องมี witness แยก).

`status` ที่คืน: `DRY_RUN` · `REJECTED` (ยังไม่ส่ง) · `SUBMITTED` (อ่านเลขได้) ·
`UNCONFIRMED` (ส่งแล้วแต่พิสูจน์เลขไม่ได้) · `RECORD_FAILED` · `FAILED`.
`error_code` : `E_BAD_BROKER / E_BAD_SIDE / E_UNSUPPORTED_SIDE / E_BAD_ORDER / E_KILL_SWITCH /
E_VALIDATOR / E_NO_QUOTE / E_NO_SBL / E_NO_PIN / E_BAD_PIN / E_TICKET_INCOMPLETE /
E_WRONG_ACCOUNT / E_LEDGER_UNREADABLE / E_ANTI_DW / E_SUBMIT_FAILED / E_CONFIRM_FAILED /
E_ORDER_NO_UNREADABLE`.

## 2. Guardrails — decisions (ตรวจก่อน merge)

| ประเด็น | ที่ทำ | เหตุผล |
|---|---|---|
| `DRY_RUN_MODE` | หยุด **หลัง validate ก่อนพิมพ์อะไรลงตั๋ว** — เปิดแท็บแบบ read-only ทำ preflight (selector ครบ? account อะไร?) แล้วคืน `DRY_RUN` ไม่มีเลขออเดอร์ ไม่เขียน DB | ตั๋วที่กรอกค้างไว้ = ระเบิดเวลา (human เผลอกด Submit ถัดไป) · Liberator driver เดิมก็ตัดก่อนแตะเบราว์เซอร์ |
| Anti-Mock เลขออเดอร์ | รับเฉพาะแถว ledger **ใหม่** ที่ match symbol+side+volume+price และไม่อยู่ใน snapshot ก่อนส่ง · อ่านไม่ได้ = `UNCONFIRMED` + `broker_order_no=None` | `streaming_driver` เดิมใส่ `STM-<timestamp>` ปลอม — executor นี้ไม่ทำ |
| SHORT / SBL | **block** (`E_NO_SBL`) ไม่ใช่แค่เตือน | naked short = broker reject/settlement พัง · ตรงกับ pre-trade check ของ B.5 |
| G6 uptick | SHORT ต้องส่ง `last_trade_price` มา ไม่งั้น `E_NO_QUOTE` | `validator.validate_short_uptick` ข้ามเงียบ ๆ เมื่อ quote = None → ต้องบังคับให้มี |
| บัญชี | SHORT/COVER → `STREAMING_ACCOUNT_NO_MARGIN` (3024959) + verify header ก่อน submit; สลับไม่ได้ = `E_WRONG_ACCOUNT` ไม่ส่ง | กัน short หลุดไป Cash (radio H/C ไม่ render บน Cash) |
| idempotency | dry-run ไม่เขียน idempotency cache (`record_idempotency=not dry`) | ไม่งั้น dry-run จะ block ของจริงใน 60 วิถัดมา |
| Liberator | SHORT/COVER → `E_UNSUPPORTED_SIDE` | footer ticket เป็น cash buy/sell เท่านั้น |
| market hours | เป็น **warning** ไม่ block | โบรกเกอร์เป็นผู้ตัดสิน; 09:55–12:30 / 14:25–16:30 (+07) |

## 3. สิ่งที่ verify แล้ว (ของจริง ไม่ใช่ mock)

1. **Unit tests — 24 passed** (`tests/test_broker_cdp_order_executor.py`)
   ครอบ: side/dry-run/validator/SBL/quote/PIN/kill-switch/anti-DW/ledger-unreadable/
   account-switch fail/UNCONFIRMED ไม่แต่งเลข/DB row `source='bot_cdp'`/adapter B.5.
2. **Project verify hook — PASS**
   `.venv/bin/python scripts/verify_changes.py app/services/broker_cdp/order_executor.py
   app/services/broker_cdp/sync_service.py .env.example` → targeted 48 passed
   (`order_executor` 24 + `order_sync` 11 + `sync` 13). `tests/test_verify_changes.py` 17 passed.
3. **DRY_RUN ยิงใส่แท็บจริง** (probe: workspace `b6_dryrun_probe.py`, ทุกข้อ PASS)
   - KSS (port 9333): tab resolve ได้ · ticket ครบทุก selector (`missing=[]`) · header = **3024959** (margin) → `status=DRY_RUN`, ไม่มี `broker_order_no`, ไม่มี `order_id`
   - LIB (port 9334): tab resolve ได้ · footer ticket ครบ (`missing=[]`) → `DRY_RUN`
   - live-mode 150 หุ้น (odd-lot) → `E_VALIDATOR` **โดยไม่ได้เปิดแท็บเลย** (get_tab ถูก patch ให้ raise ถ้าถูกเรียก — ไม่ raise = ไม่เคยเรียก)
   - live-mode SHORT ไม่ส่ง quote → `E_NO_QUOTE` · lib SHORT → `E_UNSUPPORTED_SIDE`
   - `orders` count 0 → 0 (dry-run/refusal ไม่เขียนอะไรเลย)

## 4b. LIVE WITNESS RESULT — 2026-10-21 10:18 (+07) ✅

ยิงจริง 1 ไม้บนแท็บ Streaming ที่คนดูอยู่: **COVER 3,100 TU @ 12.60**
(12.60 = bid 1 tick ใต้ตลาด 12.70 → ค้าง Queuing ไม่ match ตามที่สั่ง)

| # | ข้อ | ผล |
|---|---|---|
| 1 | ฟอร์มถูกกรอก symbol/vol/price/PIN + Submit | ✅ COVER / TU / 3,100 / 12.60 / PIN (anti-DW read-back ผ่าน) |
| 2 | แถวใหม่ใน Order ledger | ✅ `11010191 · 21/10 10:18:36 · TU · Cover · 12.60 · 3,100 · Matched 0 · Bal 3,100 · Queuing(O)` |
| 3 | `status` | ✅ `SUBMITTED` (หลังแก้ bug #2 ข้างล่าง) — attempt แรกได้ `UNCONFIRMED` เพราะ 2 bug นี้ |
| 4 | `broker_order_no` = เลขบนจอ | ✅ `11010191` ตรงทุกหลัก |
| 5 | แถวใน `orders` | ✅ `CDP-KRUNGSRI-11010191` · `status=SUBMITTED` · `source=bot_cdp` · `acct=3024959` |

**2 bug จริงที่ witness เปิดโปง (แก้แล้ว + มี unit test):**

1. **ปุ่ม Submit ไม่ได้ชื่อ "Submit"** — พอเลือก side แล้วปุ่มจะเปลี่ยนชื่อเป็นชื่อ side
   (`button.bg-color-buy-20` / `-sell-` / `-short-` / `-cover-`) → selector เดิม
   `button:has-text('Submit')` ไม่เจอปุ่ม → `E_SUBMIT_FAILED` ทุกครั้ง
   · แก้: `KSS_SUBMIT_BY_SIDE[side]` (class ของ side ก่อน, "Submit"/"Send" เป็น fallback)
2. **ปุ่มยืนยันใน modal ก็ชื่อ side** (`[role=dialog] button:has-text('Cover')`) และ
   Order Confirmation เป็น ReactModal ที่ต้องกดยืนยันก่อนออเดอร์จะไปถึงตลาด
   · แก้: `KSS_CONFIRM_BY_SIDE[side]` + `_confirm_modal()` ที่ลอง 5 ครั้ง, และถ้า
   "มี modal แต่กดไม่ได้" → คืน `E_CONFIRM_FAILED` (ไม่ส่ง) **ไม่ไปอ่านเลขผี**
3. **ตัว scrape order ledger อ่าน 0 rows ทั้งที่มีออเดอร์จริง** — แถว order มี checkbox
   เป็น cell แรก (`""`) และมี action cell ท้ายแถว (`Change/Detail/Cancel`) ทำให้
   cell เลื่อน 1 ตำแหน่งและติด `/^\d{5,}$/` ไม่ผ่าน → `_read_new_order_no` และ
   `sync_orders_from_cdp` (B.7) มองไม่เห็นออเดอร์ที่บอทเพิ่งส่ง
   · แก้: `_normalise_kss_order_cells()` (strip checkbox + action cells, fail-closed
   ถ้า cell < 11) + JS strip แบบเดียวกัน

หมายเหตุ: การกดยืนยันในรอบ witness นี้ **คนกดเอง** (user กด Cover ในราคา 12.60) —
เส้นทาง `_confirm_modal` ของบอทจึงพิสูจน์ด้วย unit test ในรอบนี้ และจะถูกพิสูจน์สดใน B.8

**หลัง witness:** `scrape_orders_from_cdp("kss")` → 1 order (11010191) ·
`sync_orders_from_cdp("kss")` → `scraped=1, new_manual_count=0` (ไม่สร้างแถวซ้ำ) ·
unit 54 passed (executor 28 + order_sync 13 + sync 13) · `scripts/verify_changes.py` PASS

## 4. LIVE WITNESS — runbook (human ต้องนั่งดูจอ)

**Prep (ทำตามลำดับ)**

1. Login เองจนถึง Streaming (headed) ตามปกติ + OTP — อย่าให้ session หมดอายุระหว่างเทส
2. ตรวจ `.env`: `DRY_RUN_MODE=false` (ปัจจุบันเป็น false อยู่แล้ว), `KRUNGSRI_PIN`/`LIBERATOR_PIN` = 6 หลัก
3. เลือกหุ้น/ราคาที่**ถูก tick + board lot + มูลค่าไม่เกินเพดาน** และพร้อมขาดทุนจริงถ้าพลาด

**Dry-run ซ้ำ (ไม่มีอะไรถูกส่ง)**

```bash
.venv/bin/python ~/.hermes/kanban/boards/investment-homelab/workspaces/t_8bd9cbfb/b6_dryrun_probe.py
```
คาดหวัง: `RESULT: ALL CHECKS PASSED`

**ยิงจริง 1 ไม้เล็ก (BUY before COVER/SHORT — ปลอดภัยที่สุด)**

```python
# scratch: .venv/bin/python <ไฟล์นี้>
import asyncio, sys, os
sys.path.insert(0, "/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab")
os.chdir("/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab")
from app.services.broker_cdp.order_executor import execute_order_via_cdp

async def main():
    res = await execute_order_via_cdp(
        "kss", "BUY", "TU", 100, 12.70,          # ← แก้ symbol/vol/price ตามที่ตาเห็น
        dry_run=False,                            # ← ยิงจริง
    )
    for k in ("success","status","broker_order_no","order_id","account_no","error_code","error","sync"):
        print(f"{k:16} = {res.get(k)}")

asyncio.run(main())
```

**จุดที่ต้องเห็นด้วยตา (5 ข้อ = done-when ของการ์ด)**

| # | ดูอะไร | ผ่านเมื่อ |
|---|---|---|
| 1 | ระหว่างรัน: ฟอร์มถูกกรอก symbol/vol/price/PIN และมี Submit | เห็นค่าตรงกับที่สั่ง |
| 2 | หลัง submit: หน้า View Order มีแถวใหม่ | มีแถวใหม่ ไม่ใช่แถวเก่า |
| 3 | `status` ที่ print | `SUBMITTED` |
| 4 | `broker_order_no` เทียบกับเลขบนหน้าจอ | **ตรงกันทุกหลัก** |
| 5 | `sqlite3 investment_homelab.db "select order_id,broker_order_no,status,source from orders order by created_at desc limit 3"` | มีแถว `CDP-KRUNGSRI-<เลข>` · `status=SUBMITTED` · `source=bot_cdp` |

**ถ้าได้ `UNCONFIRMED`** (ส่งแล้วแต่อ่านเลขไม่ได้): อย่ารันซ้ำ — ไปดู View Order ด้วยตา
ถ้าเลขขึ้นครบให้ `sync_orders_from_cdp("kss")` แล้วบันทึกด้วยมือ; แจ้งกลับใน card ด้วย
(นี่คือ anti-mock ที่ทำงานถูก ไม่ใช่ bug — แต่ต้องรู้ว่า grid render ช้าแค่ไหนจริง)

**ถ้าได้ `E_WRONG_ACCOUNT`**: dropdown ยังไม่กาง/`li` ยังไม่ขึ้น — ถ่าย DOM ของ dropdown มาด้วย
**ถ้าได้ `E_TICKET_INCOMPLETE`**: `preflight.missing` บอกว่า selector ไหนหาย — ส่งชื่อมา

## 5. เรื่องที่ต้องตัดสินใจต่อ

- `DRY_RUN_MODE=false` ใน `.env` อยู่แล้ว = เส้นทางยิงจริง armed ตลอดเวลา ใครเรียก
  `execute_order_via_cdp(..., dry_run=False)` จะยิงจริง — แนะนำเปิด `true` เป็นค่าปกติ
  แล้ว override เฉพาะตอน witness (โค้ดรองรับ `dry_run=` ราย-call อยู่แล้ว) · **ยังไม่ได้แก้ .env**
- **ยังไม่ต่อ webhook**: `/buy`…/`cover` confirm ยังไม่ยิงออเดอร์ (B.5 คืน `draft_id` เฉย ๆ) —
  executor พร้อมแล้ว (adapter `execute_confirmed_order`) เหลือต่อ 1 จุดใน `line_service`
  ซึ่งควรทำเป็น card ถัดไป (ต้องมี witness เพราะเป็นการเปิดเส้นทางเงินอัตโนมัติ)
- COVER/SHORT witness: COVER ผ่านแล้ว (11010191 ค้าง Queuing) · SHORT ยังไม่เคยยิงจริง
  (ต้องมี SBL lot ก่อน) — B.8 ยังไม่ต้องใช้
- **`_confirm_modal` ยังไม่เคยถูกกดโดยบอทในของจริง** — รอบ witness คนกดเอง ให้ B.8
  เฝ้าดูจุดนี้เป็นพิเศษ (ถ้าค้าง modal จะได้ `E_CONFIRM_FAILED` ไม่ใช่การอ่านเลขผี)
