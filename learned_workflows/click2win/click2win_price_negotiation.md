# Learned Workflow: Click2Win Price Negotiation (Cancel & Re-submit Strategy)
**Workflow Name:** `click2win_price_negotiation`  
**Recorded At:** 2026-09-23 09:12:00 UTC  
**Status:** `VERIFIED`  

## Description
ขั้นตอนการไล่ราคาและต่อรองราคาคำสั่งซื้อขายอัตโนมัติ (Price Negotiation Loop) บนกระดาน Settrade Click2Win Streaming โดยใช้กลยุทธ์ **Cancel & Re-submit (ยกเลิกคำสั่งเดิมที่ค้างท่อ และส่งคำสั่งใหม่ที่ราคา Best Bid / Best Offer ทันที)** เพื่อให้คำสั่งสามารถ Match ได้อย่างรวดเร็วและปลอดภัย

## Execution Steps
| Step | Action | Target Selector | Value / Arguments | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `EVALUATE` | `table tbody tr` | `Order No, Symbol, Price, Status` | สแกนหาคำสั่งสถานะ `Queuing(SX)` ที่ตั้งไว้แต่ยังไม่ Match |
| 2 | `QUOTE` | `.market-quote-strip, table.bids-offers` | `Bid 1 / Offer 1` | ดึงราคาเสนอซื้อสูงสุด (Bid 1) หรือเสนอขายต่ำสุด (Offer 1) ล่าสุด |
| 3 | `CANCEL` | `tr:has-text('{old_order_no}') a:has-text('Cancel')` | `{old_order_no}` | คลิกลิงก์ยกเลิกคำสั่งเดิมที่รอคิว |
| 4 | `CONFIRM` | `button:has-text('Confirm'), button:has-text('ตกลง')` | - | กดยืนยันการยกเลิกคำสั่งในกล่องเตือน |
| 5 | `VERIFY_CANCEL` | `tr:has-text('{old_order_no}') td:has-text('Cancelled(CX)')` | `Cancelled(CX)` | ตรวจสอบว่าคำสั่งเดิมถูกยกเลิกและวงเงินถูกคืนเรียบร้อย |
| 6 | `RE_SUBMIT` | `input#equity-place-order-buy-radio-button, input[placeholder='Symbol'], input[name='equity-place-order-vol'], input[name='price-input'], input#pin, button:has-text('Submit')` | `Symbol, Vol, NewPrice (Bid1/Offer1), PIN` | กรอกฟอร์มและส่งคำสั่งใหม่ด้วยราคาต่อรองที่ Match ง่ายขึ้น |
| 7 | `RECORD` | `SQLite orders table` | `is_negotiated = True, negotiated_price = {new_price}` | บันทึกประวัติการปรับราคาลงฐานข้อมูลเพื่อติดตามผล |

## Health Verification Rules
- [x] Old order exists in `Queuing(SX)` status before price negotiation begins
- [x] Old order cancellation completes before new order submission to prevent double-spending
- [x] New order volume equals remaining unfilled volume of old order
- [x] Audit log recorded in `session_logs` and `orders` tables

---
*Maintained automatically by Playwright MCP Learning Loop (Self-Annealing)*
