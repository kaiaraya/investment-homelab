# TASK — Unified Live Witness Runbook (2026-10-28, window 09:55–10:25)

- **Lane / Tier:** 🔴 Human at the screen (T2) · `DRY_RUN_MODE=false` เฉพาะในหน้าต่าง · headed browsers
- **Cards:** `t_1e4a05eb` (2.8 SBL) → `t_99cc85d7` (N6 nego) → `t_b6749a20` (2.7 Value BUY)
- **Board:** `hermes kanban --board investment-homelab`
- **Written:** 2026-10-27 by `@homelab-review` (draft, ยังไม่ผ่านการอนุมัติของผู้ใช้ — 3 ข้อใน §0.3 ต้องเคาะก่อน)
- **ที่มา:** รวม `WITNESS_N6_S3_RUNBOOK.md` + `TASK-loop2-hitl-round-20261026.md` + card bodies เป็น session เดียว

---

## 0. ก่อนวันงาน

### 0.1 Pre-flight (ต้องเช็คซ้ำเช้าวันจริง ไม่ใช่ใช้ค่าคืนนี้)

| check | ค่าที่ต้องเป็น | ถ้าไม่ใช่ |
|---|---|---|
| gateway `:8000` `/health` | `{"status":"healthy"}` | gateway ตาย = LINE CLI ไม่ทำงานทั้งรอบ → start ก่อน 09:40 |
| cloudflared tunnel | running | webhook ไม่ถึง LINE → หยุด |
| schedulers (Action-Exit / Orchestrator / Intraday) | **DISABLED** ทั้งหมด | isolated mode เท่านั้น ห้ามมีตัวยิงเองระหว่าง witness |
| `TRADING_MODE` / `DRY_RUN_MODE` | `LIVE` / **`true`** ก่อนเริ่ม | ดู §0.2 การสลับ |
| `QUICKTRADE_HEADLESS`, `PLAYWRIGHT_HEADLESS` | `false` (headed) | ผู้ใช้ต้องเห็นจอเพื่อ witness |
| **`KSS_AMEND_MODE`** | **`quicktrade`** (ค่า default ในโค้ด) | ⚠️ **ตอนนี้เป็น `trademan_cancel_replace` — ต้องเปลี่ยนก่อน N6** ดู §0.4 |
| CDP 9333 (KSS Streaming + SBL Real Time tab) | login แล้ว, ไม่ redirect ไปหน้า login | ต้อง login+OTP ใหม่ **สด ๆ ก่อนเริ่ม** (session เสื่อม ~45 นาที) |
| CDP 9334 (Liberator) | login แล้ว | `/port lib` ต้องเห็นเลขพอร์ต |
| SBL cache `data/krungsri_sbl_realtime.json` | mtime = วันเดียวกัน (ล่าสุด 2026-10-27 08:43) | `/sbl sync` ก่อน `/borrow` ไม่งั้นได้ `CACHE_STALE` |
| MARGIN account (KSS) | `3024959` | ผิดพอร์ต = ยกเลิกทันที |

### 0.2 การสลับ `DRY_RUN_MODE` (ทำครั้งเดียวทั้งรอบ)

`DRY_RUN_MODE` เป็น global flag ตัวเดียวสำหรับทุกคำสั่ง → ในรอบนี้ต้องเป็น `false` ทั้ง 2.8 และ 2.7
ขั้นตอน: `sed -i 's/^DRY_RUN_MODE=true/DRY_RUN_MODE=false/' .env` → restart **gateway only**
(`.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`, ห้าม `--reload`)
CDP 9333/9334 เป็น process แยกที่ถือ browser อยู่ → restart gateway ไม่ควรทำให้ session หลุด
แต่ **ห้ามถือว่าจริง** — เช็ค `/status` หลัง restart: ต้องเห็น badge `LIVE` และ session health = ok
ถ้า session หลุดหลัง restart → login+OTP ใหม่ **ก่อน** เริ่ม 2.8 (SBL ต้องสดที่สุด)
ปิดรอบ: คืน `DRY_RUN_MODE=true` + restart gateway **ทันทีที่จบใบสุดท้าย** ก่อนคุยกับใคร

### 0.3 ⚠️ 3 ข้อที่ต้องให้ @user เคาะ (ไม่มีคำตอบ = ไม่เริ่ม)

1. **วงเงินจริงสูงสุดที่ยอมเสียทั้งรอบ** — ผมเสนอ cap ตามตารางนี้ (รวม worst case ≈ ฿3,500):

   | card | instrument | ขนาด | notional โดยประมาณ | ความเสี่ยงจริง |
   |---|---|---|---|---|
   | 2.8 | borrow+short 100 หุ้น (symbol จาก SBL cache) | 100 | ~฿700–2,000 | **มีจริง**: ดอกเบี้ย SBL + ราคาไต่ขึ้นถ้า short ค้าง |
   | N6 | lure order 1 ใบ/broker (BUY ราคาต่ำกว่าตลาดมาก) | 100 | ~฿1,000/ใบ | ~0 ถ้าไม่ match — แต่ **ต้อง cancel ปิดท้าย** |
   | 2.7 | `/buy BCPG 50k` → ไม้จริง 1 ใบ | ~100 | ~฿680–1,100 | จริง เต็มจำนวน |

   ถ้าตัวเลขนี้สูงเกินไป บอก cap มา แล้วผมจะลด volume ต่อใบให้ (ทุกใบใช้ volume ปรับได้ ไม่ต้องแก้โค้ด)
2. **ใครนั่งจอ + ช่วงเวลา** — เสนอ 09:55–10:25 (window เช้า). ถ้าไม่ทัน ให้ใช้ 14:25–16:30 **แต่ห้ามข้าม 2.8 ไปทำใบอื่นก่อน** เพราะ SBL session เสื่อมไว
3. **lot TU 3,100 หุ้น (Ref B494354) ที่ค้างอยู่** — เลือก:
   - **(ก) แนะนำ**: เก็บไว้ใช้เป็นหลักฐาน `/short` (มี lot จริงอยู่แล้ว → ผ่าน `E_NO_SBL` โดยไม่ต้องยืมเพิ่ม) แล้ว `/return TU all` ปิดท้ายรอบ
   - (ข) `/return TU all` ก่อนเริ่ม แล้วยืม symbol ใหม่ทั้งหมด (ช้ากว่า ~3 นาที, เสี่ยงเจอ `OUT_OF_STOCK`)

### 0.4 ⚠️ Finding จากรีวิวโค้ด — N6 จะไม่ผ่านถ้าไม่แก้ env

`app/services/line_cli/handlers.py:407` — ถ้า `KSS_AMEND_MODE=trademan_cancel_replace`, `/nego kss` จะไปทาง
`_kss_cancel_replace()` = **cancel + re-submit เป็นออเดอร์ใหม่ (order_no เปลี่ยน)**
but N6 done-when บังคับว่า "ใบเดิมยังอยู่ (order_no เดิม), ราคาใหม่ตรง plan_price"
→ ต้องตั้ง `KSS_AMEND_MODE=quicktrade` (branches ไป `_broker_modify()` → `negotiate_order_price()` →
Settrade *Change Price & Volume* ซึ่งคง order number ไว้) **ก่อนเริ่ม N6** แล้วคืนค่าเดิมหลังจบรอบ
หมายเหตุ: branch `quicktrade` ส่ง `new_price=0.0` จาก batch path → ราคาถูกเลือกโดย passive policy ของ
Quick Trade ไม่ใช่ `plan_price` ของ handler → เวลา witness ให้อ่านราคาจริงจากหน้าจอ/ตารางออเดอร์
แล้วเทียบกับที่การ์ด LINE รายงาน (ไม่ใช่เทียบกับตัวเลขที่ handler คำนวณ) ไม่งั้นจะ "fail" ทั้งที่ระบบถูก

---

## 1. Card 2.8 — SBL borrow → short → return (`t_1e4a05eb`, ~10 นาที) — **ทำอันนี้ก่อน**

ทำใน CDP 9333 session เดียวต่อเนื่อง (OTP ครั้งเดียว) · MARGIN `3024959`

| # | action | expected | evidence |
|---|---|---|---|
| 1 | `DRY_RUN_MODE=false` + restart แล้ว → `/status` | badge `LIVE`, KSS session ok, SBL tab ok | screenshot |
| 2 | `/sbl pool` (หรือ `/sbl sync` ถ้า cache เก่า) | pool refresh, จด wall-clock | chat screenshot |
| 3 | เลือก symbol: มี `available_qty ≥ 100` และ **ไม่มี** XD/XR | จด symbol + fee% | note |
| 4 | `/sbl pool <sym>` | เห็น inventory จริงตรงกับหน้าจอ SBL Real Time | screenshot ×2 (LINE + จอ) |
| 5 | `/borrow <sym> 100` → confirm → ยืนยัน | live borrow จริง: **Ref.No. ในตาราง transaction ตรงจอ** + SBLBorrowLot `ACTIVE` (ไม่ใช่ lot ผี) | screenshot + ref no |
| 6 | `/short <sym> 100` | ผ่าน `E_NO_SBL` (เพราะมี lot จริง) — **ถ้าเป็น lot TU ให้ใช้ `/short TU 100` แทน** | screenshot |
| 7 | `/return <sym> all` → confirm → ยืนยัน | lot ปิด: `remaining=0` / `PARTIAL_RETURNED`, margin คืน | screenshot |
| 8 | เก็บ `docs/handoff/TASK-loop2-2.8-sbl-witness.json` | order/txn ref ตรงกันทุก field | — |

- **Abort if:** Ref.No. บนจอไม่ตรงกับที่รายงาน, borrow ขึ้น DRY-RUN badge (แปลว่า env ไม่ติด), lot ขึ้น ACTIVE แต่ volume ไม่ตรง, หรือ `/short` ถูกบล็อกด้วย `XD_BLOCKED` (ให้เปลี่ยน symbol ไม่ใช่ฝืน)
- **ห้าม:** retry `/borrow` ซ้ำเมื่อไม่แน่ใจว่าสำเร็จ — ไปอ่าน `/sbl` ก่อน (กัน lot ซ้อน)

---

## 2. Card N6 — HITL ต่อราคาผ่าน Rich Menu (`t_99cc85d7`, ~10 นาที)

เกิดหลัง §0.4 แล้วเท่านั้น · ต้องมี lure order 1 ใบ/broker

| # | action | expected | evidence |
|---|---|---|---|
| 1 | KSS: วาง BUY lure 1 ใบ ราคาต่ำกว่าตลาดมาก (เช่น BCPG ที่ ~-8%) | order ติด bid list, **ไม่ match** | screenshot + order_no |
| 2 | LIB (9334): วาง BUY lure 1 ใบ ทำนองเดียวกัน | เหมือนกัน | screenshot + order_no |
| 3 | มือถือ: Rich Menu ช่อง 4 (⚡ ต่อราคา) → การ์ดเลือก broker | การ์ดขึ้นครบ 2 broker | screenshot |
| 4 | เลือก KSS → โหมด 🎯 Match | **order_no เดิม**, ราคาใหม่ = Match price | screenshot ก่อน/หลัง |
| 5 | เลือก KSS → โหมด 🪤 Lure | order_no เดิม, ราคา = Lure price | screenshot |
| 6 | re-read ตารางออเดอร์หลังแก้ (Anti-Mock) | `old_price != new_price` ทุกครั้ง | screenshot + ค่าจริง |
| 7 | เลือก LIB → โหมด 🎯 Match แล้ว 🪤 Lure | ผ่านทั้งคู่ (native WebTrade Change) | screenshot |
| 8 | **cleanup: cancel lure ทั้ง 2 ใบ** | `/orders` ไม่เหลือ order ค้าง | screenshot |
| 9 | เก็บ `docs/handoff/TASK-loop2-n6-witness.json` | — | — |

- **Abort if:** order_no เปลี่ยน (แปลว่า `KSS_AMEND_MODE` ไม่ติด → กลับไป §0.4), ราคาใหม่ไม่ตรงที่การ์ดรายงาน, มีออเดอร์ถูก match ระหว่างต่อราคา, SHORT ละเมิด uptick guard
- **Rules:** ห้ามแก้โค้ดในใบนี้ — เจอ bug → เปิดการ์ดใหม่ (side-quest)

---

## 3. Card 2.7 — Value BUY จริง 1 ใบ (`t_b6749a20`, ~5 นาที)

⚠️ การ์ดนี้ติด `block_loop_detected` (limit 2/2, `kind=needs_input`) แล้ว — **ระบบจะไม่ auto-retry**
ต้อง unblock ด้วยมือ (`hermes kanban --board investment-homelab unblock t_b6749a20`) **หลัง** เห็นว่า §0.3 ข้อ 1 อนุมัติแล้วเท่านั้น
(unblock เร็วเกิน = worker ตื่นมาเจอตลาดปิดแล้ว block ใหม่ = เสียโควตา limit อีก)

| # | action | expected | evidence |
|---|---|---|---|
| 1 | `/buy BCPG 50k` (DRY_RUN ยัง `true`) | การ์ดแสดง budget + จำนวนหุ้นที่คำนวณได้ + badge 🧪 | screenshot |
| 2 | ยืนยัน (dry) | dry-run receipt เดียว ไม่มี double reply | screenshot ×2 |
| 3 | สลับ `DRY_RUN_MODE=false` + restart gateway + `/status` | badge `LIVE` | screenshot |
| 4 | `/buy BCPG 50k` → ยืนยัน 1 ครั้ง | ไม้จริง 1 ใบที่ LIB (CASH) | receipt |
| 5 | เทียบเลข order บนหน้าจอ Liberator กับ `broker_order_no` ใน DB | **ตรงกัน 100%**, `orders.source='bot_cdp'` | screenshot + query |
| 6 | `/port lib` + `/orders lib` | position ใหม่ขึ้น, ไม่มีออเดอร์ค้างซ้ำ | screenshot |
| 7 | เก็บ `docs/handoff/TASK-loop2-2.7-value-witness.json` + PNG, human เซ็น | — | — |

- **Abort if:** การ์ด LINE กับจอ broker ไม่ตรงกันเลขเดียว, มี receipt 2 ใบ, หรือ `source != 'bot_cdp'`
- ถ้าไม้จริงไม่ผ่าน → **อย่า retry ทันที** (จะกิน limit และอาจยิงซ้ำ) → บันทึก+เปิดการ์ด bug

---

## 4. ปิดรอบ (5 นาที)

1. `DRY_RUN_MODE=true` + คืน `KSS_AMEND_MODE=trademan_cancel_replace` → restart gateway → `/status` ต้องเห็น 🧪 DRY-RUN
2. `/orders` ทั้ง 2 broker = ไม่มี order ค้าง (lure ต้องถูก cancel ครบ)
3. `/sbl` = ไม่มี lot ACTIVE ค้าง (ถ้ามี → `/return` ปิดให้หมด หรือบันทึกเหตุผลไว้)
4. comment หลักฐานลงการ์ดทั้ง 3 + `hermes kanban --board investment-homelab move ... done`
5. ถ้ามี bug เจอระหว่าง witness → เปิดการ์ดใหม่ ห้ามแก้ในใบ witness

---

## 5. ลำดับความสำคัญถ้าเวลามีจำกัด

`2.8` (บังคับ — session เสื่อมไว) → `2.7` (สั้นสุด, หลักฐานเงินจริงชัดสุด) → `N6` (ย้ายไป window 14:25 ได้)
