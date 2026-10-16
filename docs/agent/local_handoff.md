# Local Handoff — Argon ↔ Antigravity IDE (Flash 3.8) ↔ Cline (DeepSeek)

> SOP ของ Development Loop แบบ 3-agent โดยใช้ **folder เดียวกัน (filesystem) เป็น medium กลาง**
> — **ไม่มี GitHub · ไม่มี PR · ไม่มี Kanban** (cline-kanban ปลดระวางแล้ว)
> **มนุษย์ = Gate Keeper + Witness + relay** (ปลุก agent แต่ละตัว ณ จุด handoff)
> อ้างอิง: `docs/agent/workflow_playbook.md` (บทบาท + board) · `docs/agent/token_workflow.md` (token/model) ·
> `docs/agent/handoff_protocol.md` (รูปแบบไฟล์) · `.agents/skills/stepwise-approval/SKILL.md` (HITL)

---

## 1. Actors & model assignment

| Actor | Surface | Model | Tier | บทบาท | เขียน |
|---|---|---|---|---|---|
| **Argon** | Antigravity (local) | Argon/Pro | Plan + STEP 5 | Complex Task Owner — directive · แผน · Context map · วิเคราะห์ · เจ้าของ board | `directive/*.md`, แผนใน `docs/handoff/TASK-*.md`, `docs/board/loop_board.md`, `## Argon Analysis` |
| **Flash** | Antigravity IDE | **Flash 3.8** (multimodal ถูก) | 🔴 T2/HITL + verify | Live runner + co-pilot (stepwise) + RCA | `## Verification & Stepwise Approval`, `data/screenshots/`, `rca/<broker>/`, `learned_workflows/<broker>/` |
| **Cline** | Cline plugin | **Plan=DeepSeek Pro · Act=DeepSeek Flash** | 🟢🟡 T0/T1 | Implementer (code + unit test) | code (`app/**`, `tests/**`) + `## Cline Report` |
| **Human** | — | — | gate + witness | อนุมัติแผน (gate #1) · ยืนยัน live · merge `main` (gate #2) | flip `Status` · merge `task/<slug>` → `main` |

- **3 context แยกกัน เรียกกันเองไม่ได้** (Argon = **Antigravity** · Flash 3.8 = **Antigravity IDE** — คนละ app/context แม้ชื่อตระกูลเดียวกัน · Cline = **Cline plugin**) → มนุษย์เป็น **relay**: ปลุก app และชี้ไปที่ md ไฟล์
- **Medium = folder เดียว**: `docs/handoff/TASK-<slug>.md` (ตัวกลางเดียวของ 1 งาน) + `docs/board/loop_board.md` (ภาพรวม loop)
- **ห้าม base64/รูป เข้าโมเดล** — Flash 3.8 อ่านภาพผ่าน vision/DOM text แล้วเทียบ UI landmark (§ `token_workflow.md`)

## 2. Folder เป็น shared medium (ไม่มี GitHub)

- ทั้ง 3 app ชี้ **folder เดียวกัน** — Argon เขียนแผนลง `docs/handoff/` + `directive/` โดยตรง
- **handoff signal = `Status` field ใน md** (ไม่ใช่ PR) + **git commit เป็น checkpoint**
- Argon **เขียนแผนเอง (STEP 0) + อ่านผล (STEP 5)** — ไม่รันโค้ด ไม่เห็น live browser (Anti-Mock §10)
- **ไม่มี git remote** — repo เป็น **local-only** (ปลด `origin` 2026-10-16 · backup ทำเองนอก loop) · git commit = checkpoint ในเครื่อง
- Branch (local เท่านั้น): `main` = canonical (human-owned) · `task/<slug>` = งานที่กำลังทำ

## 3. The loop (STEP 0 → 5)

```
STEP 0  Argon อัปเดต directive + เขียนแผน (handoff md + board)      [Argon · ไม่มีคน]   Status DRAFT→READY
STEP 1  Human อ่านแผนใน Antigravity → อนุมัติ (gate #1, ไม่มี PR)     🔴 Human            Status READY→IN_PROGRESS
STEP 2  T0/T1 → Cline plugin (Plan=Pro · Act=Flash) implement+unit    [Cline]             ## Cline Report → REVIEW
STEP 3  T2/HITL → Flash 3.8 (Antigravity IDE) live verify + witness   [Flash · human]     ## Verification
STEP 4  Human squash `task/<slug>` → `main` (gate #2)                 🔴 Human            Status DONE
STEP 5  Argon วิเคราะห์ (แผน+ผล) → `## Argon Analysis` → directive delta → กลับ STEP 0
```

**Human gates — 2 บทบาท (ไม่เป็นคอขวด):**

| บทบาท | Gate |
|---|---|
| **Gate Keeper (อนุมัติ)** | STEP 1 อนุมัติแผน (flip `Status` = gate #1) · STEP 4 squash merge `task/<slug>` → `main` (gate #2) |
| **Witness (ยืนยันเหตุการณ์จริง)** | STEP 3: live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE |

**Human ต้อง *ไม่* อยู่ (ไม่งั้นเป็นคอขวด):** STEP 0 (Argon เขียนแผนเอง) · STEP 2 T0/T1 · STEP 5 (Argon วิเคราะห์เอง)

## 4. Handoff mechanism (md = medium)

1. **Argon → Human/Cline/Flash**: เขียนแผนครบใน `docs/handoff/TASK-<slug>.md` (§Context map · §Steps · §Acceptance) + เพิ่มการ์ดใน `docs/board/loop_board.md` → `Status: READY`
2. **Human**: อ่านแผน → flip `Status: IN_PROGRESS` (gate #1) → ปลุก Cline/Flash ชี้ไปที่ไฟล์
3. **Cline → Flash**: เติม `## Cline Report` (files changed · tests · open questions) → `Status: REVIEW`
4. **Flash → Human/Argon**: เติม `## Verification & Stepwise Approval` + `### Live Evidence` → verdict
5. **Human**: PASS → squash `task/<slug>` → `main` (gate #2) → `Status: DONE`
6. **Argon**: อ่านแผน + ผล → เติม `## Argon Analysis` → learning → directive delta ของ loop ถัดไป

> ไฟล์เดียวต่อยอดกันทั้ง 3 app (ไม่ copy ไฟล์) — อ่าน §Status ก่อนเสมอเพื่อรู้ว่าต้องทำอะไรต่อ

## 5. Risk-Tier (ใครทำ)

- 🟢 **T0** — code / docs / unit test / headless scrape (ไม่แตะ order/OTP/account) → **Cline plugin**
- 🟡 **T1** — logic ที่ไม่แตะ order / OTP / tick size → **Cline plugin** (Pro plan, Flash act) + diff audit
- 🔴 **T2** — order · OTP · account switch · SBL · live login · live browser · merge `main` → **Flash 3.8 (Antigravity IDE)** + human witness

Fast screen (ตอบ "yes" ข้อใด ⇒ T2 ⇒ **ห้าม** ให้ Cline plugin ทำ): ยิง order จริง · ยิง SMS OTP/2FA · switch account/SBL · ขับ headed browser/อ่านจอจริง · merge `main`

## 6. Verify ladder + token budget

- 🟢🟡 **T0/T1**: `.venv/bin/python scripts/verify_changes.py <changed files>` (targeted test) · `--full` ครั้งเดียวตอนปิดงาน · docs-only = report-only
- 🔴 **T2/HITL**: หลักฐานจริง + **human confirm** (Anti-Mock) — screenshot ลง `data/screenshots/` แล้วอ้าง **path** · อ่าน UI ผ่าน DOM text / `browser_evaluate` / short OCR → `ask_question`
- **เริ่มจาก Context map เสมอ** (ไฟล์ + ช่วงบรรทัด) — ห้าม search/อ่านทั้งไฟล์ใหม่ · 1 atomic step ต่อ turn
- `token_guard` บังคับ: read ≤400 บรรทัด · search ≤3 queries · ห้าม image/binary เข้าโมเดล · budget ~20 tool calls/unit
- Context > 60K → skill `compact` snapshot → `/resume`

## 7. Status state machine (field `Status` ในไฟล์ handoff)

```
DRAFT ──(Argon เขียนแผนเสร็จ)──► READY ──(human gate #1)──► IN_PROGRESS ──► REVIEW ──(Flash verify + human merge)──► DONE
  ▲                                                                          │
  └────────────── CHANGES_REQUESTED ◄─────────────────────────────────────────┘
```
- `DRAFT` = Argon ร่าง (§Context/§Scope/§Steps/§Acceptance) + self-review
- `READY` = แผนพร้อม · รอ human อนุมัติ (freeze scope) — เปลี่ยน scope ต้อง review ใหม่
- `IN_PROGRESS` = Cline/Flash กำลังทำ · `REVIEW` = รอ Flash verify (Stage A–D)
- `DONE` = human merge `main` (gate #2) + Argon วิเคราะห์เสร็จ (STEP 5)

## 8. Git tree + commit timing

```
main          ← canonical, human-owned เท่านั้น (squash จาก task/<slug>)
task/<slug>   ← branch ชั่วคราวของงาน (Cline + Flash commit ระหว่างทำ)
```

| # | ใคร | เมื่อไหร่ | commit อะไร | branch | ข้อความ |
|---|-----|----------|-------------|--------|---------|
| 1 | Argon | แผนผ่าน self-review | `directive/` + `docs/handoff/TASK-*.md` + `docs/board/` | `main` | `docs(TASK-xxx): plan + context map + decomposition` |
| 2 | Cline | แต่ละ atomic unit PASS | `app/**`, `tests/**` | `task/<slug>` | `TASK-xxx: <type>(<scope>): <summary>` |
| 3 | Flash | T2/HITL witness PASS | หลักฐาน + `## Verification` | `task/<slug>` | `TASK-xxx: test(live): witness PASS` |
| 4 | Human | gate #2 | **squash** `task/<slug>` → `main` | `main` | `TASK-xxx: <summary> (live-verified)` |
| 5 | Argon | STEP 5 เสร็จ | `## Argon Analysis` + directive delta | `main` | `docs: Argon analysis loop <N>` |

## 9. On T2/HITL error (สังเกตได้ตอน live)

1. **STOP ทันที** (stepwise-approval §4) — ห้ามทำ step ถัดไป
2. **3-point RCA** (session/context · live DOM · data schema) → self-anneal ≤ 3 ครั้ง
3. เก็บ anomaly snapshot (`data/screenshots/` + DOM text) → บันทึก **RCA ใหม่** ใน `rca/<broker>/` + อัปเดต `learned_workflows/<broker>/` (zero-contradiction)
4. **ห้าม commit ไป `main` เด็ดขาด** — โค้ดค้างบน `task/<slug>` · Verdict = `CHANGES_REQUESTED` + ลิงก์ RCA
5. รากเป็น **code bug** → Cline แก้บน `task/<slug>` เดิม → Flash re-verify → วนจน PASS → human merge
6. รากเป็น **แผน/directive ผิด** → Argon re-plan (STEP 0) + spawn child card ลง board
7. เกิน 3 attempts / แตะ order-OTP-account จริง → HITL escalate: `🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`

> Git safety: `main` สะอาดเสมอ เพราะ human merge เท่านั้น · `task/<slug>` reset/rebase ได้อิสระ

## 10. Anti-Mock Guardrail (บังคับ)

Argon เขียนแผนเอง + เห็นผล → ข้อ 2–3 ที่ Argon "สงสัย" เป็น **สมมติฐาน ไม่ใช่หลักฐาน**
→ ต้องยืนยันด้วย test จริง (broker + LINE, headed) + human confirm ก่อน merge เสมอ · **ห้าม merge main เพราะ "Argon บอกว่าปลอดภัย"**
· ห้ามยืนยันด้วย unit test อย่างเดียวสำหรับงาน T2 · ห้ามรายงาน ✅ ทั้งที่ DOM ไม่เปลี่ยน

## 11. Cross-references

- `docs/agent/workflow_playbook.md` — บทบาท 3 actor + board (แทน Kanban) + worktree/merge lifecycle
- `docs/agent/token_workflow.md` — token budget + model routing (Pro plan / Flash act / Flash 3.8 HITL)
- `docs/agent/handoff_protocol.md` — รูปแบบไฟล์ handoff + Cline Report + Verification
- `.agents/skills/stepwise-approval/SKILL.md` — HITL stages A–D + human confirm (Flash 3.8)
- `.agents/skills/task-router/SKILL.md` — routing T0/T1 → Cline plugin · T2 → Flash
- `.agents/rules/loop_engineering.md` — DECOMPOSE→EXECUTE→VERIFY→REFLECT→REPEAT
