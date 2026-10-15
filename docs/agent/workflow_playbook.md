# InvestmentHomelab — Agent Workflow & Kanban Playbook (SOP)

คู่มือและข้อกำหนดมาตรฐาน (Standard Operating Procedure) สำหรับการประสานงานระหว่าง **Argon @ Gemini web (Complex Task Owner — directive / แผน / วิเคราะห์ / Kanban)** กับ **Cline Agent (Implementer + Verifier)** โดยมี **มนุษย์เป็น Gate Keeper + Witness** (ไม่มี Gemini Flash ใน loop แล้ว)

---

## 1. การแบ่งหน้าที่ (Role Boundaries: Plan vs Act)

| หน้าที่ | Argon @ Gemini web | Cline Agent | Human |
|---|---|---|---|
| **Role** | Complex Task Owner — Directive Owner, Planner, Evaluator, Kanban owner | Implementer + Verifier (Unit Tester, RCA fixer) | Gate Keeper (อนุมัติ) + Witness (ยืนยันเหตุการณ์จริง) |
| **Model** | Argon/Pro (web, GitHub connector) · monthly | DeepSeek Flash → Pro (implement) · **Pro** (verify) | — |
| **การเข้าถึง** | GitHub repo (เขียนแผน + อ่านผล) เท่านั้น | Worktree + live browser + รูปภาพ (ผ่าน vision tool) | จอจริง + app broker + GitHub |
| **ขอบเขตงาน** | อัปเดต directive (รับ learning) · วางแผน + self-review · เขียน Context map · วิเคราะห์ direction / consistency / vuln · จัดการ Kanban | ทำตาม Atomic steps ใน Context map · เขียนโค้ด · รัน unit test เจาะจง · verify (stepwise + vision) | merge PR แผน (gate #1) · ยืนยัน T2/live · merge PR ผล (gate #2) |
| **Workspace** | GitHub (branch `plan/<slug>`) | Dedicated Git Worktree (`~/.cline/worktrees/<task-slug>`) | — |
| **Output** | `directive/*.md`, `docs/handoff/TASK-xxx.md` (แผน), `## Argon Analysis`, GitHub Issue | Code commits, `## Cline Report`, `## Cline Verification` | การอนุมัติ (merge) |

---

## 2. โครงสร้าง Kanban Board (5 คอลัมน์)

```
[1. Backlog] ──> [2. Ready / Planning] ──> [3. In Progress] ──> [4. Review / Approval] ──> [5. Done]
                     (Argon)                  (Cline)              (Cline verify + User)      (Argon + User)
```

**เจ้าของบอร์ด = Argon** (ผ่าน GitHub — commit/PR/Issue) · Cline ทำงานเฉพาะคอลัมน์ 3–4

1. **`[Backlog]` (Argon)**:
   - บันทึกความต้องการใหม่ (Backlog items) และการ์ดลูก (Spawned child cards) ที่แตกประเด็นจาก §Argon Analysis / Open questions
2. **`[Ready / Planning]` (Argon) — PHASE 0–3**:
   - PHASE 0: Argon อัปเดต `directive/*.md` จาก learning ของ loop ที่แล้ว (ดู §Argon Analysis ของการ์ดก่อน)
   - PHASE 1–2: Argon ร่าง `docs/handoff/TASK-xxx.md` + self-review เองจนโอเค (status: `DRAFT`)
   - PHASE 3: Argon เปิด PR แผน + GitHub Issue → ผู้ใช้ merge PR → freeze scope (status: `READY`)
   - ไฟล์ต้องระบุ **Scope**, **Context map** (ไฟล์, symbol, บรรทัด), และ **Atomic Decomposition**
   - รายละเอียดเต็ม: `docs/agent/github_handoff.md` (§4 Handoff mechanism)
3. **`[In Progress]` (Cline)**:
   - **WIP Limit: ไม่เกิน 2 การ์ดพร้อมกัน**
   - Cline ทำงานแยกใน Git Worktree เฉพาะการ์ด
   - อ่านและแก้เฉพาะไฟล์ใน Context Map
   - เพดาน Context: **≤ 60K tokens** (ถ้าเกินให้สั่ง `/compact` แล้วสร้างการ์ดใหม่ด้วย `/resume`)
4. **`[Review / Approval]` (Cline verify + ผู้ใช้ witness)**:
   - Cline ดำเนินการตาม **Stepwise-Approval Protocol**:
     - Stage A: Audit diff เทียบกับ Invariants (Anti-Mock, Invariant 9 Zero-OTP, Uptick rule)
     - Stage B: Live Headed UI / Hardware check
     - Stage C: ยืนยันผลลัพธ์ผ่าน `ask_question`
   - ภาพ UI/hardware → Cline อ่านผ่าน vision tool (Gemini vision → ข้อความ) เทียบ UI landmark
5. **`[Done]` — PHASE 4c + 5 (Argon + ผู้ใช้)**:
   - ผู้ใช้ Squash merge PR ผล เข้าสู่ branch `main` (Human gate #2)
   - ลบ Worktree ชั่วคราว และอัปเดตสถานะใน handoff เป็น `DONE`
   - PHASE 5: Argon วิเคราะห์ (แผน + ผล) → เขียน `## Argon Analysis` → learning ป้อนกลับ `[Backlog]` / directive ของ loop ถัดไป

---

## 3. กฎการตั้งชื่อและการแยกการ์ด (Card Naming & Branching)

### 3.1 Naming Convention
ชื่อไฟล์และชื่อการ์ดต้องตรงกันในรูปแบบ:
```
TASK-<pillar/area>-<phase/seq>-<short-slug>
```
*ตัวอย่าง:*
- `TASK-cli-p2a-cash-honest-mapping`
- `TASK-krungsri-cancel-amend-uptick`
- `TASK-line-otp-relay-kde`

### 3.2 กฎการแยกการ์ดใหม่ (Child Card Spawning)
- เมื่อ Cline กำลังทำงาานแล้วพบ Bug แฝง, ปัญหาโครงสร้างนอก Scope, หรือข้อเสนอแนะเพิ่มเติม:
  - **ห้ามแก้เองเด็ดขาด** (ป้องกัน Context Bloat & Scope Creep)
  - บันทึกรายละเอียดลงใน `## Cline Report -> Open questions`
  - Argon จะนำรายการใน Open questions มาแตกเป็นการ์ดใหม่ เช่น `TASK-<slug>_1-<desc>` นำไปวางใน `[Backlog]` เพื่อวางแผนต่อไป

---

## 4. กลยุทธ์ Git Worktree และ Commit Lifecycle

### 4.1 Git Worktree Isolation
Cline ทำงานใน Worktree อิสระต่อ 1 การ์ดเสมอ:
```bash
git worktree add ~/.cline/worktrees/<task-slug> -b task/<task-slug>
```

### 4.2 Conventional Commit ใน Worktree (Cline Worker)
ทุกครั้งที่จบ Atomic step ให้ commit โค้ดลง branch ประจำการ์ด:
```
TASK-<xxx>: <type>(<scope>): <summary>
```
*ประเภท (Type):* `feat`, `fix`, `test`, `refactor`, `docs`

### 4.3 Squash & Merge เข้า Main (ผู้ใช้ = Human gate #2)
หลัง Cline verify ผ่าน (Stepwise Approval) → ผู้ใช้ Squash merge PR ผลเข้าสู่ `main` (GitHub UI หรือคำสั่งด้านล่าง):
```bash
git checkout main
git merge --squash task/<task-slug>
git commit -m "TASK-<xxx>: <full-feature-summary>"
git worktree remove ~/.cline/worktrees/<task-slug>
```

---

## 5. มาตรการประหยัด Token (Token-Lean Rules)

1. **ห้ามรัน Search กว้างๆ**: ค้นหาเฉพาะชื่อฟังก์ชัน/คลาสเฉพาะเจาะจง (≤ 3 คำต่อครั้ง)
2. **ห้ามอ่านไฟล์เกิน 400 บรรทัดรวดเดียว**: ต้องระบุช่วงบรรทัดเสมอ (อาศัย `CODEMAP.md`)
3. **ห้ามส่ง base64 รูปเข้าโมเดลตรงๆ**: Cline อ่านภาพผ่าน **vision tool** (Gemini vision → ข้อความ) แล้วเทียบ UI landmark; หรือตรวจ DOM text แทน
4. **ตัดทอน Output**: รันเทสต์ด้วย `-q --tb=line` และ pipe log ด้วย `| tail -40`
5. **Prompt Caching**: รักษา System Prompt ให้คงที่ ห้ามมี Dynamic timestamps ใน `AGENTS.md`
6. **Hook Token Guard**: ให้เปิดใช้งาน `.cline/hooks/PreToolUse` และ `.agents/hooks.json` ตลอดเวลา

---

## 6. GitHub-Mediated Loop (Argon ↔ Cline + Human)

Loop ใช้ **GitHub เป็น medium กลาง** — Argon (Gemini web) เข้าถึง repo ผ่าน GitHub connector โดยตรง (ไม่ automate browser) · มนุษย์ = ผู้ปลุก agent ณ จุด handoff (ดู `docs/agent/github_handoff.md` §4)

```
PHASE 0  Argon อัปเดต directive (รับ learning จาก loop ที่แล้ว)   [Argon · ไม่มีคน]
PHASE 1  Argon ร่างแผน TASK-xxx.md + Context map (DRAFT)            [Argon · ไม่มีคน]
PHASE 2  Argon self-review แผน (direction / consistency)            [Argon · ไม่มีคน]
PHASE 3  คน merge PR แผน → READY (freeze scope)       🔴 Human gate #1
PHASE 4  Cline implement + test + live test            🔴 Human gates ที่ T2
PHASE 4b Cline verify (stepwise + vision tool) → verdict [Cline · DeepSeek Pro]
PHASE 4c คน merge PR ผล → main (squash)                 🔴 Human gate #2
PHASE 5  Argon วิเคราะห์ (เขียนแผนเอง + เห็นผล) → 4 งาน  [Argon · ไม่มีคน] → กลับ PHASE 0
```

**Human gates — มีแค่ 2 บทบาท (ไม่เป็นคอขวด):**

| บทบาท | Gate |
|---|---|
| **Gate Keeper (อนุมัติ)** | PHASE 3 อนุมัติ+merge PR แผน · PHASE 4c อนุมัติ+merge PR ผลเข้า main |
| **Witness (ยืนยันเหตุการณ์จริง)** | live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE |

**Risk-Tier:** 🟢 T0 อัตโนมัติ · 🟡 T1 diff audit + report · 🔴 T2 บังคับมีคน (order / OTP / account / SBL / live login / merge)

**Argon เขียนแผนเอง + เห็นผล → 4 งานวิเคราะห์:** (1) Direction alignment · (2) Directive consistency ·
(3) Code vulnerability scan · (4) Next loop improvement → เขียนใน `## Argon Analysis` ของไฟล์ handoff

> ฉบับเต็ม (status state machine, branch convention, cost policy, Anti-Mock guardrail): **`docs/agent/github_handoff.md`**
