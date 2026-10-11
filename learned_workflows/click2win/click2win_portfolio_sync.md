# Learned Workflow: Click2Win Portfolio Sync
**Workflow Name:** `click2win_portfolio_sync`  
**Recorded At:** 2026-09-23 14:30:00 UTC  
**Status:** `VERIFIED`  

## Description
ขั้นตอนการตรวจสอบและซิงก์ข้อมูลพอร์ตโฟลิโอบน Settrade Click2Win สำหรับบัญชีหุ้น (Equity) และอนุพันธ์ (Derivatives/TFEX)

## Execution Steps
| Step | Action | Target Selector | Value / Arguments | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `CLICK` | `button:has-text('Portfolio'), a:has-text('Portfolio'), span:has-text('Portfolio')` | - | สลับไปยังแท็บ Portfolio บนแถบนำทางหลัก |
| 2 | `WAIT` | `.ReactVirtualized__Grid__innerScrollContainer, .bg-color-portfolio-secondary` | `2000` | รอข้อมูลตารางพอร์ต ReactVirtualized โหลดเสร็จสมบูรณ์ |
| 3 | `SCRAPE` | `.ReactVirtualized__Grid__innerScrollContainer ul` | `Symbol, Vol, AvgCost, MktPrice, UnrealizedPL` | กวาดข้อมูลหุ้นแต่ละตัว (AOT01P2612A, AWC01P2701A, ฯลฯ) |
| 4 | `SCRAPE` | `div:has-text('Cash Balance'), div:has-text('Line Available')` | `Cash, Line, Credit Limit` | ดึงข้อมูลวงเงินและเงินสดคงเหลือของบัญชี |
| 5 | `SAVE` | `SQLite positions table` | - | บันทึกประวัติสถานะพอร์ตและคำนวณ Unrealized P/L รวม |

## Health Verification Rules
- [x] All target selectors must be present and visible in DOM
- [x] No unhandled error modal overlays

---
*Maintained automatically by Playwright MCP Learning Loop (Self-Annealing)*
