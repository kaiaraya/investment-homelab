# Handoff protocol (Antigravity → Cline → Antigravity)

> ย้ายมาจาก AGENTS.md (คำต่อคำ) เมื่อ 2026-10-12 — ต้นฉบับเต็ม: `docs/agent/full/AGENTS_full.md`

- งานมาจาก `docs/handoff/TASK-xxx.md` (template: `docs/handoff/_TEMPLATE.md`) — ทำเฉพาะ scope ที่ระบุ
- ก่อนเริ่มงาน: เขียน "Task Decomposition" (atomic steps + per-step verify) ลงในไฟล์ handoff แล้วทำทีละ step (ห้าม batch)
- เริ่มใน Plan mode, ยืนยันแผนกับผู้ใช้ แล้วจึงสลับเป็น Act mode
- เมื่อเสร็จต้องเติมส่วน `## Cline Report` ในไฟล์ handoff:
  - Files changed (path เต็มทุกไฟล์ — repo นี้ไม่มี git จึงเป็นแหล่งเดียวที่ใช้ตรวจ)
  - Summary ของการเปลี่ยนแปลง
  - คำสั่งเทสต์ที่รัน + ผลลัพธ์
  - Open questions / สิ่งที่ไม่แน่ใจ
- ถ้าเจอปัญหานอก scope ให้บันทึกใน Open questions แทนการแก้เอง

## Token-saving additions (2026-10-12)
- Antigravity ต้องเขียนส่วน **`## Context map`** ในไฟล์ handoff: ไฟล์ + ช่วงบรรทัด/ชื่อ symbol ที่ต้องแก้หรืออ่าน + verify command
  → Cline เริ่มงานจาก map นี้ทันที **ไม่ต้อง search ทั้ง repo ใหม่**
- Cline: ถ้า Context map ไม่พอ ให้ค้นแบบเจาะจง (ดู Token budget ใน AGENTS.md) และเติม map กลับลงไฟล์ handoff
