# Learned Workflow: Portfolio Overview Sync
**Workflow Name:** `portfolio_overview_sync`  
**Recorded At:** 2026-09-17 12:45:00 UTC  
**Status:** `VERIFIED`  

## Description
ขั้นตอนการสลับไปยังแท็บ Portfolio ใน TradeMan ปิด Popup ประกาศ และกวาดรายการหุ้นคงเหลือ

## Execution Steps
| Step | Action | Target Selector | Value / Arguments | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `CLICK` | `a[href*='Portfolio'], span:has-text('Portfolio')` | - | สลับไปยังแท็บ Portfolio หลัก |
| 2 | `WAIT` | - | `1200` | รอข้อมูลตารางพอร์ตโฟลิโอโหลดเสร็จสมบูรณ์ |
| 3 | `CLICK` | `button:has-text('ปิด'), button:has-text('ตกลง'), .modal-close` | - | ปิด Popup ประกาศหากปรากฏขึ้นมา |

## Health Verification Rules
- [x] All target selectors must be present and visible in DOM
- [x] No unhandled error modal overlays

---
*Maintained automatically by Playwright MCP Learning Loop*
