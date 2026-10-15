# GitHub-Mediated Multi-Agent Handoff (Argon ↔ Antigravity ↔ Cline)

> SOP สำหรับ loop การทำงานข้าม 3 agent โดยใช้ **GitHub เป็น medium กลาง** (Argon = Gemini web
> เข้าถึง repo ผ่าน GitHub integration โดยตรง — ไม่ใช้ CDP / browser automation)
> อ้างอิง: `docs/agent/workflow_playbook.md` (Kanban), `docs/agent/token_workflow.md` (token),
> `.agents/skills/stepwise-approval/SKILL.md` (HITL), `docs/agent/handoff_protocol.md` (file format)

---

## 1. Actors & model assignment (cost-aware)

| Actor | Model | Billing | Role |
|---|---|---|---|
| **Argon** @ Gemini web (GitHub integration) | Argon/Pro (web-only) | monthly (fixed) | **Directive Owner + Loop Strategist** |
| **Antigravity IDE** | Gemini Flash | monthly (fixed) | Planner + HITL co-pilot + image review |
| **Cline Agent** | DeepSeek Flash → Pro | prepaid (per token) | Implementer + targeted unit test |
| **Cline Kanban** | DeepSeek Flash → Pro | prepaid (per token) | Card orchestration + relationship linking |

- **Rule**: thinking/planning/review → monthly models (Argon + Flash), วนกี่รอบก็ marginal ≈ 0 ·
  doing/implement → prepaid (DeepSeek) เฉพาะ Phase 4
- **Image rule**: มีแต่ Gemini (web/Flash) ที่เห็นภาพได้ — DeepSeek ไม่เคยรับ base64 (ดู `token_guard`)

## 2. GitHub เป็น shared medium

- Argon อ่าน/เขียนไฟล์ใน repo ได้เองผ่าน GitHub integration → **ไม่ต้อง automate browser** (กัน selector เปราะ)
- Argon **เห็นแค่ "แผน" กับ "ผล"** (ดู §4) — ไม่รันโค้ด ไม่เห็น live browser (Anti-Mock Guardrail §7)
- Branch convention:
  - `main` — protected · merge ได้เฉพาะโค้ดที่ test + live-verified แล้ว
  - `task/<slug>` — branch ของ Cline (worktree `~/.cline/worktrees/<task-slug>`)
  - `plan/<slug>` — branch ที่ Argon เขียน directive/แผน draft
- Prereq (ยังไม่ทำ): private repo + `git remote add origin` + audit git history ว่าไม่มี `.env`/session หลุด
  (`.gitignore` ครอบ `.env`, `data/`, `*.db`, `*session_state*.json` แล้ว)

## 3. The loop (Phase 0 → 5)

```
PHASE 0  Argon อัปเดต directive (รับ learning จาก loop ที่แล้ว)      [Argon · ไม่มีคน]
PHASE 1  Antigravity (Flash) ร่างแผน TASK-xxx.md (status: DRAFT)      [Flash · ไม่มีคน]
PHASE 2  Loop แผน Flash ↔ Argon จนโอเค                                [Flash+Argon · ไม่มีคน]
PHASE 3  คนอนุมัติแผน → status: READY (freeze scope)   🔴 Human gate #1
PHASE 4  Cline implement + test + live test           🔴 Human gates ที่ T2
PHASE 4b คนอนุมัติ merge เข้า main (squash)             🔴 Human gate #2
PHASE 5  Argon วิเคราะห์ (แผน + ผล เท่านั้น) → 4 งาน   [Argon · ไม่มีคน]
         │  learning ไหลกลับเข้า PHASE 0 ของ loop ถัดไป
         └──────────────────────────────────────────────►
```

Lead time: planning (0–3) วิ่งอัตโนมัติบนโมเดลรายเดือน · คนถูกเรียกแค่ gate ที่เสี่ยง (3, 4b + T2)

## 4. Argon เห็นแค่ "แผน + ผล" → 4 งานวิเคราะห์

**Input (2 artifact ต่อ loop เท่านั้น):**

| Artifact | อยู่ในไฟล์ | อ่านส่วนไหน |
|---|---|---|
| **แผน** | `docs/handoff/TASK-xxx.md` | `## Context`, `## Scope`, `## Steps/Task Decomposition`, `## Acceptance` |
| **ผล** | ไฟล์เดียวกัน | `## Cline Report` (files changed, summary, tests, open questions) + `## Antigravity Review` (verdict, live-test) |

**Output = `## Argon Analysis` (เขียนในไฟล์ handoff เดียวกัน):**

| # | งาน Argon | ตอบคำถาม | ปลายทาง |
|---|---|---|---|
| 1 | **Direction alignment** | งานที่ทำใน loop นี้ ตรงกับ Direction (`directive/idea.md` + roadmap) ไหม? อย่างไร? | `direction_alignment:` verdict + เหตุผล |
| 2 | **Directive consistency** | แผน/ผล ขัดกับ `directive/*.md` ไหม? | ≥1 `TASK` card ใหม่ → `[Backlog]` |
| 3 | **Code vuln scan** | ไฟล์ที่เปลี่ยนใน `## Cline Report` มีช่องโหว่ไหม (เทียบ RCA pattern) | ≥1 `TASK` card + RCA entry |
| 4 | **Next loop improvement** | loop นี้เจอปัญหาอะไร → loop หน้าต้องทำอะไร | ป้อนเป็น `## Context` ของการ์ดถัดไป |

## 5. Human อยู่ตรงไหน (มีแค่ 2 บทบาท — ไม่เป็นคอขวด)

| บทบาท | Gate | ทำไมต้องมีคน |
|---|---|---|
| **Gate Keeper (อนุมัติ)** | Phase 3 อนุมัติแผน · Phase 4b อนุมัติ merge main | กัน scope creep + กันโค้ดไม่ผ่าน live test หลุดเข้า main |
| **Witness (ยืนยันเหตุการณ์จริง)** | live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE | Anti-Mock: ต้องเห็นจริง ไม่เชื่อ assertion/โมเดล (stepwise-approval §5) |

**Human ต้อง *ไม่* อยู่ (ไม่งั้นเป็นคอขวด):** Phase 0–2 (Argon/Flash วนแผน) · T0/T1 โค้ด+unit test ·
Phase 5 (Argon วิเคราะห์เอง)

**Risk-Tier (ใช้ตัดสินว่า gate ไหนเรียกคน):**
- 🟢 **T0** — code/docs/unit test/headless scrape → อัตโนมัติ
- 🟡 **T1** — logic ไม่แตะ order/OTP/tick → diff audit + report
- 🔴 **T2** — order / OTP / account switch / SBL / live login / **merge main** → บังคับมีคน

## 6. Status state machine (field `Status` ในไฟล์ handoff)

```
DRAFT ──(Argon ผ่าน)──► READY ──(Cline เริ่ม)──► IN_PROGRESS ──► REVIEW ──(คน+Argon ผ่าน)──► DONE
  ▲                                                                 │
  └────────────── CHANGES_REQUESTED ◄───────────────────────────────┘
```
- `DRAFT` = Flash ร่าง / วนแผนกับ Argon (Phase 1–2)
- `READY` = คนอนุมัติแล้ว + freeze scope (Phase 3) — เปลี่ยน scope ต้องผ่าน review ใหม่
- `IN_PROGRESS` = Cline ทำใน worktree (Phase 4) · `REVIEW` = รอ Stage A–D
- `DONE` = merge main + ลบ worktree + Argon วิเคราะห์เสร็จ

## 7. Anti-Mock Guardrail (บังคับ)

Argon เห็นแค่ แผน+ผล → ข้อ 2–3 ที่ Argon "สงสัย" เป็น **สมมติฐาน ไม่ใช่หลักฐาน**
→ ต้องยืนยันด้วย test จริง (broker + LINE, headed) + human confirm ก่อน merge เสมอ
→ ห้าม merge main เพราะ "Argon บอกว่าปลอดภัย"

## 8. Token / cost policy

1. Phase 0–3 + 5 ใช้แต่โมเดลรายเดือน (Argon + Flash) → iterate ฟรี
2. DeepSeek ถูกใช้เฉพาะ Phase 4 (prepaid) — Pro เฉพาะ Flash พัง unit เดิม 2 ครั้ง + การ์ดใหม่
3. ภาพ → Gemini เท่านั้น · คง prompt-cache (ห้าม dynamic timestamp ใน rules)
4. วัดผล: `.venv/bin/python scripts/token_report.py --since <date>`

## 9. Cross-references

- `docs/agent/workflow_playbook.md` — Kanban 5 คอลัมน์ + worktree + merge lifecycle
- `docs/agent/token_workflow.md` — token budget + Kanban card policy (deepseek-flash default)
- `docs/agent/handoff_protocol.md` — รูปแบบไฟล์ handoff + Cline Report
- `.agents/skills/stepwise-approval/SKILL.md` — HITL stages A–D + human confirm
- `.agents/rules/loop_engineering.md` — DECOMPOSE→EXECUTE→VERIFY→REFLECT→REPEAT

## 10. Setup (one-time prerequisite)

ทำครั้งเดียวต่อเครื่อง — หลังจากนี้ `git push/pull` ทำงาน **non-interactive** (automatable ทุก context ไม่ผูกกับ VS Code)

```bash
# 1. สร้าง SSH key (ไม่ใส่ passphrase เพื่อให้ automation/background job ใช้ได้)
ssh-keygen -t ed25519 -C "kaiaraya@investment-homelab" -f ~/.ssh/id_ed25519 -N ""

# 2. copy public key → GitHub → Settings → SSH and GPG keys → New SSH key
cat ~/.ssh/id_ed25519.pub

# 3. ผูก remote เป็น SSH (ห้ามใช้ HTTPS — HTTPS พึ่ง GIT_ASKPASS ของ VS Code ซึ่งไม่มีใน background)
git remote set-url origin git@github.com:kaiaraya/investment-homelab.git

# 4. ตรวจว่าใช้ได้แบบไม่ต้อง prompt
ssh -T git@github.com                      # → "Hi kaiaraya! You've successfully authenticated"
GIT_TERMINAL_PROMPT=0 git fetch origin     # ต้องผ่านโดยไม่ค้าง
```

- ตรวจก่อน push ครั้งแรก: `git log --all --pretty=format: --name-only | sort -u | grep -iE '(^|/)\.env$|session_state|\.db$|^data/|screenshot'` → ต้องว่าง
- ห้าม commit `.env` / `*session_state*.json` / `*.db` / `data/` (`.gitignore` ครอบแล้ว)
- ตั้ง branch protection ที่ `main` ฝั่ง GitHub (Settings → Branches) เพื่อบังคับให้ merge ผ่าน PR เท่านั้น

