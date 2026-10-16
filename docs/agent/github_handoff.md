# GitHub-Mediated Two-Agent Handoff (DEPRECATED)

> ⛔ **DEPRECATED (2026-10-16)** — ปลด GitHub ออกจาก loop แล้ว (ไม่มี PR / ไม่มี Issue)
> ใช้ **`docs/agent/local_handoff.md`** แทน: folder เดียวเป็น medium · 3 actor · ไม่มี Kanban
> ไฟล์นี้เก็บไว้เป็นประวัติเท่านั้น — **ห้ามอ้างอิงในขั้นตอนทำงานใหม่**

**เหตุผลที่เปลี่ยน:**
1. Argon ย้ายมารันบน **Antigravity (local)** → ทั้ง loop ใช้ folder เดียวกันได้ ไม่ต้อง push/pull ผ่าน GitHub
2. `cline-kanban` ไม่เสถียร (hub-daemon / packaging bug) → แทนด้วย `docs/board/loop_board.md`
3. แยกบทบาทชัดเป็น 3 actor: Argon (plan) · Flash 3.8 (T2/HITL) · Cline plugin (T0/T1)

→ ดู SOP ปัจจุบัน: `docs/agent/local_handoff.md` · `docs/agent/workflow_playbook.md`
