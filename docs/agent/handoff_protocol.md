# Handoff protocol (Argon → Cline → Flash → Argon)

> ย้ายมาจาก AGENTS.md (คำต่อคำ) เมื่อ 2026-10-12 · อัปเดต 2026-10-16 — ต้นฉบับเต็ม: `docs/agent/full/AGENTS_full.md`
> ⛔ **ไม่มี GitHub/PR แล้ว** — medium = folder เดียวกัน · รายละเอียด loop เต็ม: `docs/agent/local_handoff.md`

- งานมาจาก `docs/handoff/TASK-<slug>.md` (template: `docs/handoff/_TEMPLATE.md`) — ทำเฉพาะ scope ที่ระบุ
- ก่อนเริ่มงาน: เขียน "Steps / Task Decomposition" (atomic steps + per-step verify) ลงในไฟล์ handoff แล้วทำทีละ step (ห้าม batch)
- เริ่มใน Plan mode, ยืนยันแผนกับผู้ใช้ แล้วจึงสลับเป็น Act mode

## Flow — ใครเขียนอะไร (ไฟล์ md เดียวต่อยอดกันทั้ง 3 app)

| STEP | Actor | เขียน | Status |
|---|---|---|---|
| 0 | **Argon** | §Directive delta · §Scope · §Context map · §Steps · §Acceptance (+ การ์ดใน `docs/board/loop_board.md`) | `DRAFT` → `READY` |
| 1 | **Human** (gate #1) | flip `Status` (ไม่มี PR) | `READY` → `IN_PROGRESS` |
| 2 | **Cline** (T0/T1) | `## Cline Report` | → `REVIEW` |
| 3 | **Flash 3.8** (T2/HITL) | `## Verification & Stepwise Approval` (+ `### Live Evidence`) | verdict |
| 4 | **Human** (gate #2) | squash `task/<slug>` → `main` | → `DONE` |
| 5 | **Argon** | `## Argon Analysis` (4 งาน) → directive delta | → STEP 0 |

## `## Cline Report` (Cline plugin เขียน — STEP 2)

- Files changed (path เต็มทุกไฟล์) · Summary ของการเปลี่ยนแปลง
- คำสั่งเทสต์ที่รัน + ผลลัพธ์
- Open questions / สิ่งที่ไม่แน่ใจ
- เจอปัญหานอก scope → บันทึกใน Open questions แทนการแก้เอง

## `## Verification & Stepwise Approval` (Flash 3.8 เขียน — STEP 3 · Stage A–D)

- Stage A audit diff vs Invariants (Anti-Mock · Zero-OTP · Uptick) · Stage B `.venv/bin/python scripts/verify_changes.py <files>`
- Stage C live/HITL ผ่าน `ask_question` · Stage D verdict = `PASS` / `CHANGES_REQUESTED`
- งาน T2 ต้องมี `### Live Evidence` (screenshot path + human witness) — ภาพอ่านผ่าน vision/OCR → ข้อความ (**ห้าม base64 เข้าโมเดล**)
- ถ้าไม่ผ่าน: **ห้าม commit ไป `main`** → `CHANGES_REQUESTED` + RCA (`docs/agent/local_handoff.md` §9)

## Token-saving additions

- Argon ต้องเขียนส่วน **`## Context map`** ในไฟล์ handoff: ไฟล์ + ช่วงบรรทัด/ชื่อ symbol ที่ต้องแก้หรืออ่าน + verify command
  → agent เริ่มงานจาก map นี้ทันที **ไม่ต้อง search ทั้ง repo ใหม่**
- ถ้า Context map ไม่พอ ให้ค้นแบบเจาะจง (ดู Token budget ใน AGENTS.md) และเติม map กลับลงไฟล์ handoff
