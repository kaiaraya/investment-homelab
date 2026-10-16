# InvestmentHomelab — Agent Workflow & Loop Board Playbook (SOP)

คู่มือ SOP สำหรับ **Development Loop 4-Agent Hybrid** ระหว่าง
- **Argon (Antigravity · Complex Task Owner — directive / แผน / วิเคราะห์ / board)**,
- **Flash 3.8 (Antigravity IDE — STEP 0a Pre-Coding DOM Probe + STEP 3 T2/HITL Witness + RCA)**,
- **Jules (Google Jules Cloud VM — STEP 2a T0/T1 Primary Implementer · 100 sessions/day)**, และ
- **Cline (Cline plugin — STEP 2b Pre-Argon Local Triage + 🔧 Side-Quest / Open Questions Handler)**
โดยมี **มนุษย์เป็น Gate Keeper + Witness + relay**

> ⛔ ไม่ใช้ GitHub PR/Issue UI · ⛔ ไม่มี Kanban (`cline-kanban` ปลดระวาง)
> ใช้ `git remote origin` (`kaiaraya/investment-homelab`) เฉพาะเป็นท่อส่ง Branch ให้ **Jules** ผ่าน `scripts/jules_bridge.py`
> ฉบับเต็ม (loop STEP 0–5 · state machine · git · error handling): **`docs/agent/local_handoff.md`**

---

## 1. การแบ่งหน้าที่ (Role Boundaries: 4-Agent Hybrid Loop)

| หน้าที่ | Argon (Antigravity) | Flash 3.8 (Antigravity IDE) | Jules (Cloud VM) | Cline (Local Plugin) | Human |
|---|---|---|---|---|---|
| **Role** | Complex Task Owner — Directive, Planner, Evaluator, Board owner | **(1) STEP 0a Read-Only DOM Probe**<br>**(2) STEP 3 Live Runner + Witness + RCA** | Primary T0/T1 Implementer (Code + Unit Test บน Cloud VM) | **(1) STEP 2b Pre-Argon Local Triage**<br>**(2) 🔧 Side-Quest / Open Questions** | Gate Keeper (อนุมัติ) + Witness (ยืนยันหน้าจอจริง) |
| **Model** | Argon/Pro (local) | Flash 3.8 (multimodal) | **T0 = Gemini 3.6 Flash**<br>**T1 = Gemini 3.1 Pro** | Plan = DeepSeek Pro<br>Act = DeepSeek Flash | — |
| **Tier** | Plan + STEP 5 | 🔍 STEP 0a Probe + 🔴 T2/HITL | 🟢 T0 / 🟡 T1 (Main Loop) | 🔎 STEP 2b Triage + 🔧 Side-Quests | gate #1/#2 + witness |
| **การเข้าถึง** | folder เดียวกัน (เขียนแผน + อ่านผล) | folder + live browser + รูปภาพ | GitHub repo clone ใน Cloud VM (ไม่มี `.env`/session จริง) | folder + local terminal + local tests | จอจริง + app broker |
| **Workspace** | `directive/` · `docs/handoff/` · `docs/board/` | `main` (Probe) / `task/<slug>` (T2) + `data/screenshots/` | Cloud branch → ดึงลง `task/<slug>` | `task/<slug>` (Triage) · `chore/<slug>` (Side-Quest) | `main` (merge) |
| **Output** | `directive/*.md`, แผนใน `TASK-*.md`, `loop_board.md`, `## Argon Analysis` | `## DOM / API Contract`, `## Verification & Stepwise Approval`, `rca/`, `learned_workflows/` | code (`app/**`, `tests/**`), `## Jules Report` | `## Cline Triage Report`, Side-Quest fixes | ยืนยัน Probe · flip `Status` · merge `main` |

---

## 2. Loop Board แทน Kanban (5 คอลัมน์หลัก + เลนที่ 6 Side-Quests) — `docs/board/loop_board.md`

```
[1. Backlog] ──> [2. Ready/Planning (+STEP 0a Probe)] ──> [3. In Progress (Jules 2a -> Cline Triage 2b)] ──> [4. Review/Approval (Flash 3)] ──> [5. Done]
                                                                                                                                                 ▲
[🔧 6. Side-Quests / Open Questions (Cline Local · branch chore/<slug> · Non-Blocking)] ─────────────────────────────────────────────────────────┘
```

1. **`[Backlog]` (Argon)** — บันทึกความต้องการใหม่ของ Loop หลัก
2. **`[Ready / Planning]` (Argon + Flash STEP 0a)** —
   - หากการ์ดแตะหน้าเว็บโบรกเกอร์หรือ XHR API ต้องตั้ง `Pre-Coding Probe: PROBE_NEEDED` ให้ **Flash 3.8 + Human** ทำ Read-Only Probe อ่าน Selector/JSON จริงมาใส่ `## DOM / API Contract` (`PROBE_DONE`) ก่อนเสมอ
   - ร่าง `docs/handoff/TASK-<slug>.md` → `Status: READY` → **รอ human gate #1**
3. **`[In Progress & Local Triage]` (Jules STEP 2a → Cline STEP 2b · หรือ Flash T2)** —
   - **STEP 2a (Jules Cloud)**: รัน `.venv/bin/python scripts/jules_bridge.py push-plan <TASK>` และ `prompt <TASK>` ส่งให้ Jules (`3.6 Flash` สำหรับ T0 / `3.1 Pro` สำหรับ T1) เขียนโค้ด + Unit Test บน Cloud VM
   - **STEP 2b (Cline Local Triage)**: ดึงโค้ดกลับเข้าเครื่องด้วย `.venv/bin/python scripts/jules_bridge.py pull-branch <remote_branch> --slug <slug>` ให้ **Cline** ตรวจ Diff เทียบ Invariants, รัน `scripts/verify_changes.py` ซ้ำในเครื่อง, คัดแยก `Open questions` และเขียน `## Cline Triage Report` ก่อนส่งให้ Flash/Argon
4. **`[Review / Approval]` (Flash + human)** — สำหรับงานที่มีส่วน T2/Live Witness Flash 3.8 เขียน `## Verification & Stepwise Approval` (Stage A–D) ร่วมกับ Human Witness
5. **`[Done]` (human + Argon) — STEP 4–5** — human **squash** `task/<slug>` → `main` (gate #2) → `Status: DONE` → **Argon** เขียน `## Argon Analysis`
6. **`[🔧 Side-Quests / Open Questions]` (Cline Local)** — งาน Low-Priority / Tech Debt ที่แตกจาก `Open questions` ไม่บล็อก Loop หลัก ให้ Cline ทำในเครื่องบน branch `chore/<slug>` (WIP ≤ 1) แล้วสรุปส่ง Argon

---

## 3. กฎการตั้งชื่อและการแยกการ์ด (Naming, Child Cards & Side-Quests)

- **Main Loop Card**: `TASK-<domain>-<slug>` · branch: `task/<slug>`
- **Side-Quest (Low-Priority Open Question)**: `SQ-<n>` ใน `loop_board.md` · branch: `chore/<slug>`
- เจอ Bug แฝง / ปัญหานอก Scope ระหว่างทำงาน → **ห้ามแก้เองใน branch หลัก** ให้บันทึกใน `Open questions` เพื่อให้ Cline Triage / Argon แยกเป็น Child Card (ถ้ากระทบเป้าหมายหลัก) หรือ Side-Quest (ถ้าเป็นงานเก็บตก/Low-Priority)

---

## 4. Git & Jules Sync Lifecycle

### 4.1 Branch & Remote Transport
- ใช้ `git remote origin` (`kaiaraya/investment-homelab` Private Repo) **เฉพาะเป็นท่อรับ-ส่งโค้ดกับ Jules** (ไม่เปิด PR/Issue บนเว็บ GitHub)
- ก่อน `git push` ทุกครั้งต้องผ่าน `scripts/jules_bridge.py check-safety` (ห้ามมี `.env`, `*session*.json`, `*.db`, หรือ `data/screenshots/*.png` ใน Git index เด็ดขาด)
- `main` = canonical, **human-owned เท่านั้น** · `task/<slug>` = branch งานหลัก · `chore/<slug>` = branch งาน Side-Quest ของ Cline

### 4.2 คำสั่งใช้งาน `jules_bridge.py`
```bash
# 1. ตรวจความปลอดภัยและส่งแผนขึ้น origin ให้ Jules เห็น
.venv/bin/python scripts/jules_bridge.py push-plan docs/handoff/TASK-<slug>.md

# 2. สร้าง Prompt มาตรฐาน (พร้อมระบุโมเดล 3.6 Flash / 3.1 Pro) เพื่อก๊อปวางใน Jules
.venv/bin/python scripts/jules_bridge.py prompt docs/handoff/TASK-<slug>.md

# 3. เมื่อ Jules ทำเสร็จ ดึง branch ลงมาเป็น task/<slug> ให้ Cline ทำ Local Triage
.venv/bin/python scripts/jules_bridge.py pull-branch <jules-remote-branch> --slug <slug>
```

### 4.3 Squash & Merge เข้า Main (human = gate #2)
```bash
git checkout main
git merge --squash task/<slug>
git commit -m "TASK-<xxx>: <full-feature-summary> (verified)"
git branch -D task/<slug>
```

---

## 5. มาตรการประหยัด Token & Cost (Token-Lean Rules)

1. **Offload งาน T0/T1 ขึ้น Jules (100 sessions/วัน)**: ประหยัดงบ DeepSeek Prepaid ใน Cline โดยให้ Cline ทำเฉพาะ **Local Triage** (อ่านเฉพาะ `git diff main...task/<slug>`) และงาน **Side-Quests**
2. **บังคับ `STEP 0a Pre-Coding Probe` เมื่อแตะ DOM/API**: ห้ามปล่อยให้ Jules เดา Selector เอง ต้องมี `## DOM / API Contract` จาก Flash 3.8 + Human ก่อนเสมอ
3. **ห้ามอ่านไฟล์เกิน 400 บรรทัดรวดเดียว** และ **ห้ามส่ง base64 รูปเข้าโมเดล** (`token_guard` เปิดทำงานตลอด)
