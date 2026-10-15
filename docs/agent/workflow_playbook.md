# InvestmentHomelab — Agent Workflow & Kanban Playbook (SOP)

คู่มือและข้อกำหนดมาตรฐาน (Standard Operating Procedure) สำหรับการประสานงานระหว่าง **Argon @ Gemini web (Directive Owner / Loop Strategist)**, **Antigravity IDE (Architect / Planner / Evaluator)**, **Cline Agent (Executor / Builder)**, และ **Cline Kanban**

---

## 1. การแบ่งหน้าที่ (Role Boundaries: Plan vs Act)

| หน้าที่ | Argon @ Gemini web | Antigravity IDE | Cline Agent + Kanban |
|---|---|---|---|
| **Role** | Directive Owner, Loop Strategist | Architect, Planner, Evaluator, HITL Co-pilot | Worker, Implementer, Unit Tester |
| **Model** | Argon/Pro (web, GitHub integration) · monthly | Gemini 3.8 Flash / Claude 3.5 Sonnet · monthly | DeepSeek-Flash (Token-Lean) · prepaid |
| **การเข้าถึง** | GitHub repo เท่านั้น (เห็นแค่ แผน + ผล) | Main repo + live browser + รูปภาพ | Worktree + Context map เท่านั้น |
| **ขอบเขตงาน** | อัปเดต directive (รับ learning) · วิเคราะห์ direction / consistency / vuln · วางแผน loop ถัดไป | วางแผนระดับระบบ, RCA, เขียน Context map, ทำ Stepwise Approval, ตรวจรูปภาพ UI/Hardware | ทำตาม Atomic steps ใน Context map, เขียนโค้ด, รัน unit test เจาะจง |
| **Workspace** | GitHub (branch `plan/<slug>`) | Main repository root (`InvestmentHomelab`) | Dedicated Git Worktree (`~/.cline/worktrees/<task-slug>`) |
| **Output** | `directive/*.md`, `## Argon Analysis` | `docs/handoff/TASK-xxx.md`, Review Verdict, Git Merge | Code commits, `## Cline Report` ในไฟล์ handoff |

---

## 2. โครงสร้าง Kanban Board (5 คอลัมน์)

```
[1. Backlog] ──> [2. Ready / Planning] ──> [3. In Progress] ──> [4. Review / Approval] ──> [5. Done]
                       (AGY)                  (Cline)                  (AGY + User)
```

1. **`[Backlog]`**:
   - บันทึกความต้องการใหม่ (Backlog items) และการ์ดลูก (Spawned child cards) ที่แตกประเด็นออกมา
2. **`[Ready / Planning]` (Argon + Antigravity) — PHASE 0–3**:
   - PHASE 0: Argon อัปเดต `directive/*.md` จาก learning ของ loop ที่แล้ว (ดู §Argon Analysis ของการ์ดก่อน)
   - PHASE 1–2: Antigravity (Flash) ร่าง `docs/handoff/TASK-xxx.md` แล้ววนกับ Argon จนโอเค (status: `DRAFT`)
   - PHASE 3: ผู้ใช้อนุมัติแผน → freeze scope (status: `READY`) — เปลี่ยน scope ต้องผ่าน review ใหม่
   - ไฟล์ต้องระบุ **Scope**, **Context map** (ไฟล์, symbol, บรรทัด), และ **Atomic Decomposition**
   - รายละเอียดเต็ม: `docs/agent/github_handoff.md`
3. **`[In Progress]` (Cline)**:
   - **WIP Limit: ไม่เกิน 2 การ์ดพร้อมกัน**
   - Cline ทำงานแยกใน Git Worktree เฉพาะการ์ด
   - อ่านและแก้เฉพาะไฟล์ใน Context Map
   - เพดาน Context: **≤ 60K tokens** (ถ้าเกินให้สั่ง `/compact` แล้วสร้างการ์ดใหม่ด้วย `/resume`)
4. **`[Review / Approval]` (Antigravity + ผู้ใช้)**:
   - ดำเนินการตาม **Stepwise-Approval Protocol**:
     - Stage A: Audit diff เทียบกับ Invariants (Anti-Mock, Invariant 9 Zero-OTP, Uptick rule)
     - Stage B: Live Headed UI / Hardware check (บันทึกรูป screenshot ส่งให้ผู้ใช้ดู)
     - Stage C: ยืนยันผลลัพธ์ผ่าน `ask_question`
5. **`[Done]` — PHASE 4b + 5**:
   - Squash merge เข้าสู่ branch `main` (หลังผู้ใช้อนุมัติ merge = Human gate #2)
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
  - Antigravity จะนำรายการใน Open questions มาแตกเป็นการ์ดใหม่ เช่น `TASK-<slug>_1-<desc>` นำไปวางใน `[Backlog]` เพื่อวางแผนต่อไป

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

### 4.3 Squash & Merge เข้า Main (Antigravity Reviewer)
เมื่อผ่านการ Stepwise Approval:
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
3. **ห้ามส่งรูป/Screenshot เข้า Cline Agent**: ให้ตรวจ DOM text แทน หรือใช้ Antigravity ตรวจสอบ
4. **ตัดทอน Output**: รันเทสต์ด้วย `-q --tb=line` และ pipe log ด้วย `| tail -40`
5. **Prompt Caching**: รักษา System Prompt ให้คงที่ ห้ามมี Dynamic timestamps ใน `AGENTS.md`
6. **Hook Token Guard**: ให้เปิดใช้งาน `.cline/hooks/PreToolUse` และ `.agents/hooks.json` ตลอดเวลา

---

## 6. GitHub-Mediated Loop (Argon ↔ Antigravity ↔ Cline)

Loop ใช้ **GitHub เป็น medium กลาง** — Argon (Gemini web) เข้าถึง repo ผ่าน GitHub integration โดยตรง (ไม่ automate browser)

```
PHASE 0  Argon อัปเดต directive (รับ learning จาก loop ที่แล้ว)   [Argon · ไม่มีคน]
PHASE 1  Antigravity (Flash) ร่างแผน TASK-xxx.md (DRAFT)            [Flash · ไม่มีคน]
PHASE 2  วนแผน Flash ↔ Argon จนโอเค                                 [Flash+Argon · ไม่มีคน]
PHASE 3  ผู้ใช้อนุมัติแผน → READY (freeze scope)      🔴 Human gate #1
PHASE 4  Cline implement + test + live test            🔴 Human gates ที่ T2
PHASE 4b ผู้ใช้อนุมัติ merge เข้า main (squash)          🔴 Human gate #2
PHASE 5  Argon วิเคราะห์ (เห็นแค่ แผน + ผล) → 4 งาน     [Argon · ไม่มีคน] → กลับ PHASE 0
```

**Human gates — มีแค่ 2 บทบาท (ไม่เป็นคอขวด):**

| บทบาท | Gate |
|---|---|
| **Gate Keeper (อนุมัติ)** | PHASE 3 อนุมัติแผน · PHASE 4b อนุมัติ merge main |
| **Witness (ยืนยันเหตุการณ์จริง)** | live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE |

**Risk-Tier:** 🟢 T0 อัตโนมัติ · 🟡 T1 diff audit + report · 🔴 T2 บังคับมีคน (order / OTP / account / SBL / live login / merge)

**Argon เห็นแค่ "แผน + ผล" → 4 งานวิเคราะห์:** (1) Direction alignment · (2) Directive consistency ·
(3) Code vulnerability scan · (4) Next loop improvement → เขียนใน `## Argon Analysis` ของไฟล์ handoff

> ฉบับเต็ม (status state machine, branch convention, cost policy, Anti-Mock guardrail): **`docs/agent/github_handoff.md`**
