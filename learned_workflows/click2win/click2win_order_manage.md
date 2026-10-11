# Learned Workflow: Click2Win Order Status & Cancel / Modify
**Workflow Name:** `click2win_order_manage`  
**Recorded At:** 2026-09-23 09:05:00 UTC  
**Status:** `VERIFIED`  

## Description
ขั้นตอนการตรวจสอบสถานะคำสั่งซื้อขายที่รอคิว (Queuing / Open Orders), การกดยกเลิกคำสั่ง (Cancel Order), และการปรับราคา (Price Negotiation) บนกระดาน Settrade Click2Win Streaming

## Execution Steps
| Step | Action | Target Selector | Value / Arguments | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `INSPECT` | `table tbody tr, .orders-table tr` | `Order No, Symbol, Status` | สแกนแถวคำสั่งที่รอคิวอยู่ในตาราง Open Orders ด้านล่างจอ Streaming |
| 2 | `MATCH` | `tr:has-text('{target_order_no_or_symbol}')` | `{order_no}` | ค้นหาแถวคำสั่งที่ต้องการจัดการ (ตรวจสอบสถานะ เช่น `Queuing(SX)`) |
| 3 | `CLICK` | `tr:has-text('{order_no}') a:has-text('Cancel')` | - | คลิกลิงก์ 'Cancel' ที่อยู่ท้ายแถวของคำสั่งเป้าหมาย |
| 4 | `CONFIRM` | `button:has-text('Confirm'), button:has-text('ตกลง'), button:has-text('OK')` | - | กดยืนยันการยกเลิกคำสั่งในกล่องข้อความแจ้งเตือน (Modal) |
| 5 | `VERIFY` | `tr:has-text('{order_no}') td:has-text('Cancelled(CX)')` | `Cancelled(CX)` | ตรวจสอบว่าสถานะคำสั่งเปลี่ยนเป็น Cancelled(CX) สำเร็จ |
| 6 | `UPDATE` | `SQLite orders table` | `status = "CANCELLED"` | ปรับปรุงสถานะคำสั่งในฐานข้อมูล Homelab พร้อมคืนวงเงินซื้อ (Line Available) |

## Health Verification Rules
- [x] Target order row exists with Queuing(SX) or Open status before cancel
- [x] Cancel link successfully triggers cancel flow and disappears after confirmation
- [x] Order status transitions to `Cancelled(CX)` with Balance = 0 and Cancelled = Total Vol
- [x] Line Available refunds money to Cash Balance

---
*Maintained automatically by Playwright MCP Learning Loop (Self-Annealing)*
