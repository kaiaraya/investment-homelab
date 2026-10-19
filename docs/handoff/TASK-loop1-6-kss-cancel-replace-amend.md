# TASK-loop1-6: KSS Amend ผ่าน TradeMan (Cancel + Re-submit) — ทางเลือก (A)

- Created: 2026-10-19 by Argon (Human decision A)
- Status: PROBE_NEEDED (STEP 0a — DOM contract)
- Tier: 🟡 T1 (Jules/local) + 🔴 T2 witness
- Blocks: `TASK-loop1-4` ขั้น 3–4
- Supersedes: D1 ของ Loop 1 (In-Place Only) — **ต้องแก้ acceptance ก่อน merge**

## Why (หลักฐาน)

1. QuickTrade `Change Price& Volume` มีจริง แต่ broker reject:
   `Incorrect, short in credit and/or position (side H)` (manual test 2026-10-19)
2. TradeMan ไม่มีปุ่ม Change (KSS-RCA-016, พิสูจน์สด 2026-10-09) → amend = **Cancel + Re-submit**
3. Human เลือกทาง (A): ยอมรับ cancel+replace สำหรับ KSS

## Acceptance change (ต้องอนุมัติเป็นลายลักษณ์อักษร)

- D1 เดิม: "In-place Amendment Only (ห้าม Cancel + Replace เด็ดขาด)"
- D1 ใหม่ (เสนอ): "KSS amend = Cancel + Re-submit ภายใต้ guardrails C1–C7; LIB คง in-place เดิม"
- ผลกระทบ witness ขั้น 3: expected outcome เปลี่ยนจาก `same order_no` → `new order_no + old order cancelled`

## Guardrails (C1–C7)

| # | กฎ |
|:---:|:---|
| C1 | ทำทีละออเดอร์เท่านั้น (batch หลายใบ = หยุด) |
| C2 | **ห้าม amend ถ้า `matched_volume > 0`** (partial fill) — ยกเลิกแล้ว re-submit เฉพาะ balance เสี่ยง duplicate |
| C3 | Cancel ต้องยืนยันสำเร็จก่อน (row → Cancelled) แล้วจึง re-submit |
| C4 | ถ้า re-submit ล้มเหลว → retry 1 ครั้งที่ราคาเดิม; ถ้ายังล้ม → CRITICAL alert + หยุดทั้ง batch |
| C5 | ระยะราคา ≤ `LINE_NEGO_MAX_TICKS` (3) จากราคาเดิม + ผ่าน tick size + uptick (SHORT) |
| C6 | ต่อออเดอร์ได้ไม่เกิน 2 ครั้ง/วัน (กัน cancel loop) |
| C7 | `DRY_RUN_MODE=True` → **plan only** (ไม่ cancel/ไม่ submit) แสดงการ์ด "จะยกเลิก #X แล้วส่งใหม่ที่ Y" |

## STEP 0a — Probe checklist (ต้องได้ครบก่อนเขียนโค้ด)

### ผล probe 2026-10-19 14:00 (headed)

- **Ledger สด:** เหลือ Open ใบเดียว = `11008937` BCPG **H** 6.80 (100) · PTTEP/SCB/VGI = `Matched` หมดแล้ว
- **ปุ่มยกเลิก:** `<button data-cy="activeOrder.cancel" id="cancel_active_order_btn">Cancel</button>` — id ซ้ำทุกแถว → **ต้อง scope ตาม row** (first td = order_no) · แถว Matched ปุ่ม `disabled`
- **Dialog ยืนยัน** (จาก `cancel_order()` ที่ verify 2026-10-09): title "Cancel Order Confirmation" · `input#pin` (scope ใน overlay) · ปุ่มยืนยัน `button.bg-primaryYellow-300`
- **Quote source: TradeMan ไม่มี bid/offer** — probe API จริง:
  - `loadstockinformation` / `loadstockinformations` → มี last, ceiling/floor, high/low แต่ **ไม่มี depth**
  - `getmarketinformation` → index เท่านั้น
  - DOM ของ Portfolio/View Order ไม่มี panel bid/offer
  - → ต้องใช้ **QuickTrade `get_quote` แบบ read-only** เป็นแหล่ง bid/offer (หรือหา source ใหม่ใน Loop ถัดไป)
- **Cancel/Re-submit timing:** ยังไม่ได้วัด (ต้องทดสอบสด — ใช้ DRY_RUN plan ก่อน)

- [x] View Order row: action cell HTML + selector ปุ่มยกเลิก
- [x] Cancel confirm dialog: selector + PIN (จาก `cancel_order` + `data/krungsri_cancel_confirm.html`)
- [ ] หลัง cancel สำเร็จ: row เปลี่ยนเป็น Cancelled หรือหายจาก ledger? (วัดตอน live)
- [x] Re-submit: `execute_order` selector เดิม (BUY/SELL/SHORT/COVER + PIN)
- [x] **Quote source**: TradeMan ไม่มี → QuickTrade read-only
- [ ] Order No. ใหม่ปรากฏใน ledger ภายในกี่วินาที (วัดตอน live)

## Design (草案 — รอผล probe)

```
/nego kss [SYM|order_no]
  → ledger (trademan scrape_unmatched_orders)
  → filter balance>0, matched==0
  → plan target (bid1/offer1 จาก quote source ที่ probe ยืนยัน)
  → [DRY_RUN] card plan only
  → [LIVE] cancel_order(old) → verify Cancelled → execute_order(side, balance, target, MARGIN)
           → verify new order no + price + volume → card old→new
           → fail: retry old price once → CRITICAL alert
```

## Out of scope
- ไม่แตะ LIB (คง `change_order` in-place)
- ไม่แตะ QuickTrade driver (เก็บไว้เป็น quote source ถ้าจำเป็น)

## Open questions
1. Quote source บน TradeMan — probe ต้องตอบ
2. Cancel ระหว่างตลาดมีค่าธรรมเนียม/ข้อจำกัดไหม
3. ถ้า cancel สำเร็จแต่ตลาดปิดพอดี (re-submit ไม่ได้) → policy?

## Cline Report
- (รอ probe + implementation)
