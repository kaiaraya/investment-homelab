# TASK — ต่อราคาออเดอร์ค้างผ่าน Rich Menu (nego-menu)

- **Board:** `hermes kanban --board investment-homelab`
- **Written:** 2026-10-26 by planner
- **Status:** อนุมัติ 3 ข้อตัดสินแล้ว เริ่ม N0

## 0. ที่มา

2.9 witness เผยว่า Rich Menu ช่อง 4 (⚡ Quick Trade) เปิด "การ์ดเลือกฝั่งซื้อขาย" ที่เป็น dead-end
สำหรับต่อราคา: ระบบมี `/nego` ในที่อยู่แล้ว แต่ต้องพิมพ์ order_no เอง อ่านไม่รู้ว่ามีออเดอร์ค้างอะไรบ้าง
→ เปลี่ยนช่อง 4 เป็น "⚡ ต่อราคา" ที่อ่านออเดอร์ค้างแล้วให้กดเลือกโหมดแก้ราคาได้ทันที

## 1. ข้อตัดสิน (อนุมัติแล้ว)

1. **นิยาม "ล่อราคา"** = *"ต่อท้ายคิวที่ราคา bid/offer เดิม"* = ตั้งราคาไว้ฝั่งตัวเองที่ราคาดีสุดในกระดาน
   โดยไม่ข้าม spread และไม่ match ทันที (user: "ที่ไม่ Match เลย")
2. **ช่วงเวลา** = 09:55–12:30 / 14:25–16:30 (จ–ศ) ตามช่วงต่อราคาเดิม ห้ามต่อราคาช่วง ATO/ATC
3. **ขอบเขต** = แสดง **ออเดอร์ค้างทุกใบที่ยังไม่ match** ของทั้ง 2 broker (ไม่ใช่เฉพาะใบล่าสุด)

## 2. โมเดลราคา (SSOT = `validator`)

| Side | 🎯 Match เลย (ข้าม spread) | 🪤 ล่อราคา (เข้าคิวฝั่งตัวเอง) |
|---|---|---|
| BUY / COVER | = Best Offer | = Best Bid |
| SELL | = Best Bid | = Best Offer |
| SHORT | = Best Bid **เฉพาะ Bid > Last** (ไม่งั้น "Match ไม่ได้ตามกฎ uptick") | = Best Offer; ถ้า Offer ≤ Last → `next_tick(Last)` |

- อ่าน Last ไม่ได้ / quote ไม่ตรงหุ้น / ฝั่งที่ต้องใช้ว่าง → ยกเลิกทันที (fail-closed) ไม่กดอะไรที่ broker
- ราคาใหม่ == ราคาเดิม → ข้าม
- ออเดอร์ match บางส่วน → แก้เฉพาะ balance ที่เหลือ
- SHORT ใช้ `validator.validate_short_uptick()` เป็นที่เดียว (ห้ามเขียน uptick ซ้ำ)

## 3. การ์ด

| # | งาน | ไฟล์ | Tier | หมายเหตุ |
|---|---|---|---|---|
| N0 | `/port` `/orders` `/cash` อ่านผ่าน CDP scrape แบบเดียวกับ `/status` (แก้ B1: status เขียวแต่ read บอกหมดอายุ) | `handlers.py` (`_live_card`) | T1 | ตัวปลดล็อกทุกอย่าง |
| N1 | `market_clock.is_nego_window()` แหล่งเวลาเดียว | `app/services/market_clock.py` (ใหม่) | T0 | ขอบ 09:54/09:55/12:30/14:24/16:31 |
| N2 | `nego_pricer.plan_price(side, mode, bid, offer, last, old)` | `app/services/nego_pricer.py` (ใหม่) | T0 | 4 side × 2 mode + uptick + quote หาย |
| N3 | postback `nego_menu` → การ์ดรายการออเดอร์ค้าง → 2 โหมด → draft/confirm (TTL + กันกดซ้ำแบบ `/buy`) | `handlers.py`, `cards.py` | T1 | DRY_RUN |
| N4 | ส่ง `target_price` ลง `negotiate_order_price` (KSS); LIB ใช้ `change_order` อยู่แล้ว | `quicktrade_negotiation_service.py`, `_broker_modify` | T1 code → T2 witness | ห้ามราคาถูกเลือกเองโดยไม่รู้ตัว |
| N5 | เปลี่ยนช่อง 4 rich menu เป็น `action=nego_menu` "⚡ ต่อราคา" + อัปโหลดรูปใหม่ | `rich_menu.py`, `scripts/setup_rich_menu.py` | T0 | กดแล้วได้การ์ดต่อราคา |
| B2 | แก้ข้อความ short ("ปิด"→"เปิด") + XD วันที่ผ่านไปแล้วไม่บล็อก | `handlers.py`, `sbl_realtime_driver.py` | T0 | ดูหลักฐานจากภาพ |
| N6 | HITL witness ในตลาด: วางออเดอร์ล่อ 1 ใบ/broker แล้วลอง 2 โหมด | runbook ใหม่ | T2 | มีคนเฝ้าจอ, headed |

**ลำดับ:** N0 → (N1 ∥ N2 ∥ B2) → N3 → N4 → N5 → N6

## 4. กติกาการทำงาน (Lean P6)

- **Targeted test only** — รันเฉพาะ `tests/<target>.py`, ห้าม full suite
- **Do not commit** — ทิ้ง diff ใน working tree ให้ planner squash
- **Fail-closed** — cache/quote/session ผิดปกติ → หยุดทันที
- N1/N2/B2/N5 ไม่แตะเงินและไม่ต้องใช้ browser → ทำและ verify คืนนี้ได้; N4/N6 ต้องรอตลาดเปิด

## 5. หลักฐาน B1 (N0)

`/status` แสดง 🟢 ทั้ง KSS 9333 / LIB 9334 แต่ `/port all sync` → KSS "อ่านไม่ได้", `/orders all sync` → ทั้งคู่ "session หมดอายุ"
สาเหตุ: `_live_card` re-scrape ผ่าน pillar2 (ใน-process driver ที่ flag ค้างหลัง gateway restart) ทั้งที่ CDP tab ยัง authenticated
→ N0 เปลี่ยนให้ render จากการ์ด scrape ผ่าน CDP (`scrape_portfolio_from_cdp` / `scrape_orders_from_cdp`) ซึ่ง `_broker_sync_cdp` ใช้อยู่แล้ว
