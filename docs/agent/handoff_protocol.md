# Handoff protocol (Argon → Flash Probe → Jules → Cline Triage → Flash Witness → Argon)

> อัปเดต 2026-10-16 — รองรับ **4-Agent Hybrid Loop** (รายละเอียดเต็ม: `docs/agent/local_handoff.md`)

- งานมาจาก `docs/handoff/TASK-<slug>.md` (template: `docs/handoff/_TEMPLATE.md`) — ทำเฉพาะ scope ที่ระบุ
- งานที่แตะหน้าเว็บโบรกเกอร์หรือ XHR API ต้องผ่าน **STEP 0a (Pre-Coding Read-Only Probe)** โดย **Flash 3.8 + Human** เพื่อเขียน `## DOM / API Contract` ก่อนส่งให้ **Jules** เสมอ
- ก่อนเริ่มเขียนโค้ด: ต้องมี "Steps / Task Decomposition" (atomic steps + per-step verify) ในไฟล์ handoff แล้วทำทีละ step (ห้าม batch)

## Flow — ใครเขียนอะไร (ต่อยอดกันในไฟล์ `TASK-<slug>.md` เดียว)

| STEP | Actor | เขียน | Status |
|---|---|---|---|
| **0** | **Argon** | §Directive delta · §Scope · §Context map · §Steps · §Acceptance (+ การ์ดใน `docs/board/loop_board.md`) | `DRAFT` → `PROBE_NEEDED` หรือ `READY` |
| **0a** | **Flash 3.8 + Human** | `## DOM / API Contract` (Read-Only Probe อ่าน Selector/JSON จริงจากหน้าเว็บ) | `PROBE_NEEDED` → `PROBE_DONE` (`READY`) |
| **1** | **Human** (gate #1) | flip `Status` + รัน `scripts/jules_bridge.py push-plan` & `prompt` | `READY` → `IN_PROGRESS` |
| **2a** | **Jules** (Cloud T0/T1) | โค้ด + Unit Test (`T0=Gemini 3.6 Flash` / `T1=Gemini 3.1 Pro`) + `## Jules Report` | → `TRIAGE` |
| **2b** | **Cline** (Local Triage) | ดึง branch (`jules_bridge.py pull-branch`) → ตรวจ Invariants + รัน `verify_changes.py` ในเครื่อง → `## Cline Triage Report` | → `REVIEW` |
| **3** | **Flash 3.8 + Human** | (ถ้ามี T2) `## Verification & Stepwise Approval` (+ `### Live Evidence`) | verdict |
| **4** | **Human** (gate #2) | squash `task/<slug>` → `main` | → `DONE` |
| **5** | **Argon** | `## Argon Analysis` (4 งาน) → แตกการ์ดรอบถัดไป / ส่ง `Open questions` เข้าเลน `🔧 Side-Quests (Cline)` | → STEP 0 |

## `## Jules Report` (Jules เขียนบน Cloud VM — STEP 2a)
- Files changed (path เต็มทุกไฟล์) · Summary ของการเปลี่ยนแปลง
- คำสั่งเทสต์ที่รันบน Cloud VM + ผลลัพธ์
- Open questions / สิ่งที่ไม่แน่ใจ (ห้ามแก้เองนอก scope)

## `## Cline Triage Report` (Cline plugin เขียนในเครื่อง — STEP 2b)
- ดึง branch ลงมาเป็น `task/<slug>` ผ่าน `.venv/bin/python scripts/jules_bridge.py pull-branch <remote_branch> --slug <slug>`
- ตรวจ `git diff main...task/<slug>` เทียบ Scope, `## DOM / API Contract`, และ Invariants
- รัน `.venv/bin/python scripts/verify_changes.py <changed files>` ซ้ำในเครื่อง Homelab
- คัดกรอง `Open questions` ที่เป็น Low-Priority แยกไปลงตาราง **`🔧 6. Side-Quests / Open Questions`** บน `docs/board/loop_board.md` และสรุปผลสั้นกระชับให้ Argon

## `## Verification & Stepwise Approval` (Flash 3.8 เขียน — STEP 3 · Stage A–D)
- Stage A audit diff vs Invariants (Anti-Mock · Zero-OTP · Uptick) · Stage B `.venv/bin/python scripts/verify_changes.py <files>`
- Stage C live/HITL ผ่าน `ask_question` · Stage D verdict = `PASS` / `CHANGES_REQUESTED`
- งาน T2 ต้องมี `### Live Evidence` (screenshot path + human witness) — ภาพอ่านผ่าน vision/OCR → ข้อความ (**ห้าม base64 เข้าโมเดล**)
