# TASK-loop2 — Implementation Plan: Async Queue, Value-Based Trading, Rich Menu UI & SBL Intelligence (Phase B ต่อ)

**Status:** PLAN — APPROVED (2026-10-21) · **Owner:** Argon · **Target Readers:** Argon, Cline, Flash 3.8, Jules
**Scope:** ต่อยอด Phase B (Order Entry) — ไม่ใช่ Loop 2 "Model Data Engine" ของ `TASK-loop2-autotrade-roadmap.md` (ตัวนั้นแยก track)

---

## 0. การตัดสินใจที่ล็อกแล้ว (จากผู้ใช้ 2026-10-21)

| ข้อ | การตัดสินใจ |
|---|---|
| 1. ขอบเขต | **Phase B ต่อ** (LINE UX + SBL manual assist) — ไม่รัน roadmap Model Data Engine |
| 2. SBL `/borrow` `/return` | = **T2** (live account + PIN) → ต้อง witness + **แก้ directive ปลด Pillar 4** |
| 3. แหล่งราคา (quote) | **CDP tab** (`connect_cdp` 9333/9334) ไม่ใช่ gateway browser |
| 4. `DRY_RUN_MODE` | **`false`** (คง armed) — ทุกเส้นทาง live ยังต้องผ่าน confirm card + executor guard |

---

## 1. เป้าหมาย (Done when ของทั้ง loop)

- คำสั่ง `/buy /sell /short /cover` รองรับ **value mode** (`50k`, `1.2m`, `฿`) → resolve เป็นจำนวนหุ้นจาก CDP quote → confirm card → executor (SHORT ผ่าน G6 uptick)
- **Async Queue** ต่อจริง: webhook คืน 200 ไว, งาน CDP scrape/login รัน off-request, timeout + push ผลกลับ
- **Rich Menu**: `/quicktrade` (alias `/trade`) แสดง side-selector card (มี card แล้ว ยังไม่ wiring)
- **SBL read-only**: `/sbl` `/sbl sync` `/sbl pool <sym>` อ่านจาก DB + CDP tab (ไม่แตะเงิน)
- **SBL manual assist (T2)**: `/borrow` `/return` ทำงานบน Krungsri SBL ด้วย PIN + witness (รอ directive ปลด Pillar 4)

---

## 2. การ์ด (card · tier/model · files · done-when)

| Card | Tier / Model | Files | Done when |
|---|---|---|---|
| **2.0** ปลด Pillar 4 (SBL manual assist) ใน directive | 🟡 T1 · Jules 3.1 Pro | `directive/master_directive_v2.md` | directive §3 ระบุ SBL read + borrow/return = T2 witness-gated, ไม่ "Dormant" อีก |
| **2.1** Async Queue wiring | 🟡 T1 · Jules 3.1 Pro | `app/services/line_cli/queue.py`, `handlers.py`, `line_service.py` | webhook 200 ไว + worker push ผล + `/halt` ไม่ติดคิว |
| **2.2** Value-Based resolution (CDP quote) | 🟡 T1 · Jules 3.1 Pro | `app/services/line_cli/handlers.py`, `tests/test_line_cli_value_orders.py` | `50k`→หุ้นจาก quote, board-lot round, G6, unit ผ่าน |
| **2.3** Rich Menu quick-trade selector | 🟢 T0 · Jules 3.6 Flash | `parser.py`, `handlers.py`, `cards.py` | `/quicktrade` แสดง selector card + unit |
| **2.4** SBL read-only commands | 🟡 T1 · Jules 3.1 Pro | `handlers.py`, `pillar4_sbl.py` (read) | `/sbl`/`/sbl sync`/`/sbl pool` อ่าน DB+CDP read-only |
| **2.5** SBL `/borrow` `/return` executor + witness | 🔴 T2 · Flash + Human | `broker_cdp/`, `handlers.py` | borrow/return บน Krungsri SBL ด้วย PIN + witness (blocked) |

---

## 3. Dependency map

```
2.0 (directive) ──┬──► 2.4 (SBL read) ──► 2.5 (SBL borrow/return · T2 blocked)
                  └──► 2.5
2.1 (async queue)  (อิสระ)
2.2 (value resolve) ──► 2.3 (rich menu)   # 2.2/2.3 แตะ handlers.py/parser.py เดียวกัน → serialize
```

**Parallel-safe lanes (คนละไฟล์):** `2.1 ∥ 2.4` — 2.1 แตะ queue/line_service, 2.4 แตะ handlers/pillar4
**Serialize:** `2.2 → 2.3` (handlers.py + parser.py ซ้อนกัน)

---

## 4. Guardrails ที่บังคับ (ห้ามละเมิด)

1. **Kill-switch ต้องไม่ติดคิว** — `/halt` และ `kill_switch_service` ต้อง bypass queue (เช็คก่อนเริ่ม job แต่ละตัว หรือแยก path) — อย่าให้ CDP scrape 120s ปิดกั้น `/halt`
2. **Value mode ไม่ auto-submit** — `target_value`→หุ้น แค่ fill confirm card; ยิงจริงต้องผ่าน postback confirm → `execute_confirmed_order` เหมือนเดิม
3. **Quote จาก CDP tab เท่านั้น** (`connect_cdp`) — ไม่ใช้ gateway browser (`_quote_via_gateway_browser` สงวนไว้ cancel+replace)
4. **SHORT ต้องมี `last_trade_price`** — G6 uptick ไม่ข้ามเงียบ (`E_NO_QUOTE` ถ้าไม่มี)
5. **SBL read = read-only** — `/sbl` ไม่เปิดหน้า borrow/return, ไม่ขอ PIN, ไม่เขียน DB (อ่าน `sbl_borrow_lots` + CDP inventory)
6. **DRY_RUN_MODE=false อยู่** → ทุก executor path ยังมี per-call `dry_run` guard เดิม (หลัง validate ก่อนแตะตั๋ว)
7. **ไม่แตะโมดูล Dormant อื่น** — Scheduler/Agentic/Console ยังปิด (ปลดเฉพาะ Pillar 4 ตามข้อ 2.0)

---

## 5. หมายเหตุ (สิ่งที่ต้องระวัง)

- Async Queue เป็น **in-memory, single-process** (จงใจ) — restart ล้างคิว = fail-safe (คำสั่งที่ค้างถูกดรอป ไม่ยิงซ้ำ) เหมือน `_DRAFTS`
- Value resolve ต้อง round ลงเป็น board lot (`floor(value/price/100)*100`) และ reject ถ้า < 1 lot หรือเกิน `validate_order_value`
- Rich Menu จริง (ปุ่มล่าง persistent ของ LINE) เป็น config ฝั่ง LINE Messaging API (upload menu) — การ์ดนี้ทำแค่ command + card; ถ้าจะมี persistent menu จริง ให้เปิด side-quest แยก
