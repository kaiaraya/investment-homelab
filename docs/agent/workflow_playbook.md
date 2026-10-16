# InvestmentHomelab — Agent Workflow & Loop Board Playbook (SOP)

คู่มือ SOP สำหรับ **Development Loop 3-agent บน folder เดียวกัน** ระหว่าง
**Argon (Antigravity · Complex Task Owner — directive / แผน / วิเคราะห์ / board)**,
**Flash 3.8 (Antigravity IDE — T2/HITL + verify)**, และ **Cline (Cline plugin — T0/T1 implement)**
โดยมี **มนุษย์เป็น Gate Keeper + Witness + relay**

> ⛔ ไม่มี GitHub / PR / Issue · ⛔ ไม่มี Kanban (cline-kanban ปลดระวาง)
> ฉบับเต็ม (loop STEP 0–5 · state machine · git · error handling): **`docs/agent/local_handoff.md`**

---

## 1. การแบ่งหน้าที่ (Role Boundaries: Plan vs Act)

| หน้าที่ | Argon (Antigravity) | Flash 3.8 (Antigravity IDE) | Cline (Cline plugin) | Human |
|---|---|---|---|---|
| **Role** | Complex Task Owner — Directive Owner, Planner, Evaluator, Board owner | Live Runner + Verifier (stepwise) + RCA | Implementer (code + unit test) | Gate Keeper (อนุมัติ) + Witness (ยืนยันเหตุการณ์จริง) + relay |
| **Model** | Argon/Pro (local) | Flash 3.8 (multimodal) | **Plan = DeepSeek Pro · Act = DeepSeek Flash** | — |
| **Tier** | Plan + STEP 5 | 🔴 T2/HITL | 🟢 T0 / 🟡 T1 | gate #1/#2 + witness |
| **การเข้าถึง** | folder เดียวกัน (เขียนแผน + อ่านผล) | folder + live browser + รูปภาพ | folder + terminal + tests | จอจริง + app broker |
| **Workspace** | `directive/` · `docs/handoff/` · `docs/board/` | branch `task/<slug>` + `data/screenshots/` | branch `task/<slug>` | `main` (merge) |
| **Output** | `directive/*.md`, แผนใน `docs/handoff/TASK-*.md`, `docs/board/loop_board.md`, `## Argon Analysis` | `## Verification & Stepwise Approval`, `### Live Evidence`, `rca/`, `learned_workflows/` | code (`app/**`, `tests/**`), `## Cline Report` | flip `Status` · merge `main` |

**Worktree:** ใช้ **single checkout + branch `task/<slug>`** (ไม่ใช้ `git worktree` แยก) — ทั้ง 3 app ชี้ folder เดียวกัน สลับ branch ตามงาน

---

## 2. Loop Board แทน Kanban (5 คอลัมน์) — `docs/board/loop_board.md`

```
[1. Backlog] ──> [2. Ready/Planning] ──> [3. In Progress] ──> [4. Review/Approval] ──> [5. Done]
                  (Argon · gate #1)      (Cline T0/T1 · Flash T2)   (Flash verify + human)   (human merge + Argon)
```

**เจ้าของบอร์ด = Argon** (ไฟล์ md ธรรมดา — ไม่มี daemon/CLI) · Cline/Flash อัปเดตแค่ `Status` ใน handoff แล้ว Argon sync ลง board
- **WIP Limit:** ไม่เกิน **2 การ์ด** ใน `[In Progress]` พร้อมกัน
- 1 board = 1 loop · ปิด loop → archive เป็น `docs/board/archive/LOOP-<N>.md` แล้ว reset

1. **`[Backlog]` (Argon)** — บันทึกความต้องการใหม่ + child cards ที่แตกจาก §Open questions / §Argon Analysis
2. **`[Ready / Planning]` (Argon) — STEP 0** — อัปเดต directive จาก learning loop ที่แล้ว → ร่าง `docs/handoff/TASK-<slug>.md` (+ Context map, Scope, Atomic Decomposition) → self-review → `Status: READY` → **รอ human gate #1**
3. **`[In Progress]` (Cline / Flash)** — human flip `Status: IN_PROGRESS` → 🟢🟡 Cline plugin (Plan=Pro · Act=Flash) · 🔴 T2 Flash 3.8 + live · อ่าน/แก้เฉพาะไฟล์ใน Context map · เพดาน context ≤ 60K (เกิน → `compact` → `resume`)
4. **`[Review / Approval]` (Flash + human)** — Flash เขียน `## Verification & Stepwise Approval`: Stage A audit diff vs Invariants · Stage B `verify_changes.py` · Stage C live/HITL ผ่าน `ask_question` · Stage D verdict + human merge — ภาพ UI อ่านผ่าน vision/OCR → landmark (**ห้าม base64 เข้าโมเดล**)
5. **`[Done]` (human + Argon) — STEP 4–5** — human **squash** `task/<slug>` → `main` (gate #2) → `Status: DONE` → **Argon** เขียน `## Argon Analysis` (4 งาน) → learning ป้อน directive loop ถัดไป

---

## 3. กฎการตั้งชื่อและการแยกการ์ด (Naming & Child Cards)

### 3.1 Naming
- `TASK-<domain>-<slug>` — ตัวอย่าง: `TASK-line-otp-relay-kde`, `TASK-kss-cancel-amend-uptick`
- branch: `task/<slug>`

### 3.2 กฎการแยกการ์ดใหม่ (Child Card Spawning)
- เจอ Bug แฝง / ปัญหานอก Scope / ข้อเสนอเพิ่ม → **ห้ามแก้เอง** (กัน Context Bloat + Scope Creep)
- บันทึกใน `## Cline Report -> Open questions`
- Argon แตกเป็นการ์ดใหม่ `TASK-<slug>_1-<desc>` → วางใน `[Backlog]`

---

## 4. Git & Commit Lifecycle

### 4.1 Branch
- **ไม่ใช้ `git worktree`** — single checkout, สลับ branch ตามงาน
- **ไม่มี git remote** — repo local-only (ห้าม push) · backup ทำเองนอก loop
- `main` = canonical, **human-owned เท่านั้น** · `task/<slug>` = branch งาน

### 4.2 Conventional Commit
```
TASK-<xxx>: <type>(<scope>): <summary>
```
*Type:* `feat`, `fix`, `test`, `refactor`, `docs`

### 4.3 Squash & Merge เข้า Main (human = gate #2)
```bash
git checkout main
git merge --squash task/<slug>
git commit -m "TASK-<xxx>: <full-feature-summary> (live-verified)"
git branch -D task/<slug>
```

---

## 5. มาตรการประหยัด Token (Token-Lean Rules)

1. **ห้ามรัน Search กว้างๆ** — ค้นหาเฉพาะ identifier เฉพาะเจาะจง (≤ 3 queries/ครั้ง · ดู `docs/agent/token_workflow.md`)
2. **ห้ามอ่านไฟล์เกิน 400 บรรทัดรวดเดียว** — ระบุช่วงบรรทัดเสมอ (อาศัย `CODEMAP.md`)
3. **ห้ามส่ง base64 รูปเข้าโมเดล** — Flash 3.8 อ่านภาพผ่าน vision tool → ข้อความ แล้วเทียบ UI landmark; หรือใช้ DOM text
4. **ตัดทอน Output** — `pytest -q --tb=line` + pipe `| tail -40`
5. **Prompt Caching** — System Prompt คงที่ ห้ามมี dynamic timestamp ใน `AGENTS.md`
6. **Hook Token Guard** — เปิด `.cline/hooks/PreToolUse` + `.agents/hooks.json` ตลอด

---

## 6. Loop (Argon ↔ Antigravity IDE ↔ Cline + Human)

Loop ใช้ **folder เดียวกันเป็น medium** — ทั้ง 3 app เขียน/อ่านไฟล์ใน repo โดยตรง · มนุษย์ = relay ปลุก agent ณ จุด handoff (ดู `docs/agent/local_handoff.md` §3)

```
STEP 0  Argon อัปเดต directive + ร่างแผน TASK-<slug>.md + Context map + board   [Argon · ไม่มีคน]  DRAFT→READY
STEP 1  Human อ่านแผน → flip Status (gate #1)                                    🔴 Human gate #1
STEP 2  Cline plugin implement + unit test (T0/T1) · Flash live (T2)             [Cline/Flash]    → REVIEW
STEP 3  Flash verify (stepwise + vision) → verdict + Live Evidence               [Flash 3.8 · witness]
STEP 4  Human squash task/<slug> → main (gate #2)                                🔴 Human gate #2 → DONE
STEP 5  Argon วิเคราะห์ (แผน + ผล) → ## Argon Analysis → directive delta         [Argon · ไม่มีคน] → STEP 0
```

**Human gates — 2 บทบาท (ไม่เป็นคอขวด):**

| บทบาท | Gate |
|---|---|
| **Gate Keeper (อนุมัติ)** | STEP 1 อนุมัติแผน (flip `Status` = gate #1) · STEP 4 squash merge `task/<slug>` → `main` (gate #2) |
| **Witness (ยืนยันเหตุการณ์จริง)** | STEP 3: live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE |

**Risk-Tier:** 🟢 T0 อัตโนมัติ (Cline) · 🟡 T1 diff audit + report (Cline) · 🔴 T2 บังคับ human (order / OTP / account / SBL / live login / live browser / merge `main`)

**Argon เขียนแผนเอง + เห็นผล → 4 งานวิเคราะห์:** (1) Direction alignment · (2) Directive consistency ·
(3) Code vulnerability scan · (4) Next loop improvement → เขียนใน `## Argon Analysis` ของไฟล์ handoff

> ฉบับเต็ม (status state machine · branch/merge convention · cost policy · T2 error handling · Anti-Mock guardrail): **`docs/agent/local_handoff.md`**
