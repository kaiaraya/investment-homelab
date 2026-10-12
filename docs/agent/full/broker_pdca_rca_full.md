# Rule: Broker-Specific PDCA Knowledge Loop & Zero-Contradiction Policy

## 1. Broker Knowledge Isolation (การแยกส่วนองค์ความรู้รายโบรกเกอร์ 100%)
- โบรกเกอร์แต่ละราย (Krungsri TradeMan, Settrade Click2Win, Liberator WebTrade, Settrade Open API) มีสถาปัตยกรรม, วงจรชีวิตเซสชัน, ระบบ 2FA, และโครงสร้าง DOM ที่แตกต่างกันอย่างสิ้นเชิง
- ห้ามนำพฤติกรรมหรือข้อสันนิษฐานของโบรกเกอร์หนึ่งไปปะปนกับอีกโบรกเกอร์หนึ่งเด็ดขาด
- ให้บันทึกและดูแลไฟล์องค์ความรู้เฉพาะทางแยกกัน:
  - Krungsri TradeMan: `learned_workflows/rca_krungsri_trademan.md`
  - Settrade Click2Win: `learned_workflows/rca_settrade_click2win.md`
  - Liberator: `learned_workflows/rca_liberator.md`

## 2. Mandatory PDCA Incident Logging (การบันทึกประวัติการแก้ปัญหาแบบ PDCA)
ทุกครั้งที่มีการทดสอบแล้วพบ Bug, Error, หรือ Edge Case ใหม่ และได้รับการแก้ไขจนผ่านแล้ว ต้องบันทึกรายการลงในไฟล์ RCA ของโบรกเกอร์นั้นเสมอในรูปแบบ:
- **รหัสเหตุการณ์และวันที่ (Incident ID & Date)**: เช่น `KSS-RCA-001 (2026-09-29)`
- **อาการที่พบ (Symptom)**: ข้อความ Error หรือพฤติกรรมที่ผิดปกติ
- **การสืบหาต้นตอ (Root Cause Analysis - RCA)**: ทำไมจึงเกิดขึ้น (เช่น ป๊อปอัปเด้งซ้อน 2 ชั้น, SPA Client Routing ไม่ไปหน้าเป้าหมาย, Tick Size ผิดช่วงราคา)
- **Edge Cases ที่พบ (Edge Cases Identified)**: เงื่อนไขพิเศษที่ต้องระวัง
- **วิธีแก้ปัญหาที่พิสูจน์แล้ว (Proven Working Solution)**: โค้ด Python และ CSS/XPath Selectors ที่แก้ปัญหาสำเร็จ
- **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context)**: บันทึกคำแนะนำของผู้ใช้เพื่อนำไปต่อยอด

## 3. Zero-Contradiction Runbook Reconciliation (การขจัดเนื้อหาขัดแย้งใน Markdown)
- เมื่อผลการทดสอบจริงหรือโค้ดล่าสุดมีการเปลี่ยนแปลง Selectors หรือขั้นตอนการทำงาน (เช่น การปิด Overlay ซ้อน หรือการเปลี่ยนลำดับคลิก) **ต้องทำการอัปเดตไฟล์ Runbook เดิมใน `learned_workflows/*.md` และเอกสารที่เกี่ยวข้องทันที**
- ห้ามปล่อยให้ Runbook เก่ามีขั้นตอนที่ขัดแย้งกับโค้ดไดรเวอร์จริง เพื่อป้องกันไม่ให้ Agent ในวันถัดไปอ่านข้อมูลผิดพลาดและแก้ปัญหาเดิมซ้ำซ้อน

## 4. Prioritize Self-Annealing Before Escalation (วิเคราะห์และแก้ปัญหาด้วยตนเองก่อน)
- เมื่อเกิดปัญหาขึ้น ให้ทำการตรวจสอบ Diagnostic Snapshot (HTML & Screenshot) เพื่อหาสาเหตุที่แท้จริงและทดลองแก้ไขผ่านกลไก Self-Annealing ทันที
- หากเกินขอบเขตที่แก้ไขได้โดยอัตโนมัติ ให้ทำการแจ้งเตือนผู้ใช้ผ่าน Actionable Notification (KDE Connect / Web Cockpit) พร้อมระบุ Root Cause ที่วิเคราะห์ได้เพื่อขอการตัดสินใจ
