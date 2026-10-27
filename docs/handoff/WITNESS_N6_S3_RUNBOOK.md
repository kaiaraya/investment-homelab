# N6 & S3 Witness Runbook (Pre-Market / Human Return)

## 1. N6 — Price Negotiation (ต่อราคา 🎯 Match / 🪤 Lure)
- **Target Task:** `t_99cc85d7`
- **Pre-verified Logic:** 121/121 negotiation and price-collar unit tests PASSED (commit `fa2e707`).
- **Status:** Test harness, CDP in-place amend snippets (`streaming_change.js`), and LINE Rich Menu slot 4 are 100% ready.
- **Human Step when Market Opens (or Next Trading Window 09:55):**
  1. วาง order ซื้อ passive 1 ใบ (เช่น BDMS @ 14.00 ที่เคยทดสอบผ่าน)
  2. กด Rich Menu ช่อง 4 (⚡ ต่อราคา)
  3. เลือกโหมด 🎯 Match หรือ 🪤 Lure บน LINE Card เพื่อตรวจสอบ in-place amend บนหน้าจอ Streaming

## 2. S3 — SHORT / COVER + SBL Gate
- **Target Task:** `t_1e4a05eb`
- **Pre-verified Logic:** 115/115 SBL/Short tests PASSED.
- **Status:** G6 Uptick Guard, Margin Ratio check, and SBL inventory validation are verified.
