# GitHub-Mediated Two-Agent Handoff (Argon ↔ Cline)

> SOP สำหรับ loop การทำงานระหว่าง **Argon (Gemini web)** กับ **Cline (local)** โดยใช้ **GitHub เป็น medium กลาง**
> (Argon เข้าถึง repo ผ่าน GitHub connector โดยตรง — ไม่ใช้ CDP / browser automation) · **มนุษย์ = Gate Keeper + Witness**
> เป็นผู้ปลุก agent ณ จุด handoff (ไม่ใช่ actor ใน loop) · **ไม่มี Gemini Flash ใน loop แล้ว**
> อ้างอิง: `docs/agent/workflow_playbook.md` (Kanban), `docs/agent/token_workflow.md` (token),
> `.agents/skills/stepwise-approval/SKILL.md` (HITL), `docs/agent/handoff_protocol.md` (file format)

---

## 1. Actors & model assignment (cost-aware)

| Actor | Model | Billing | Role |
|---|---|---|---|
| **Argon** @ Gemini web (GitHub connector) | Argon/Pro (web-only) | monthly (fixed) | **Complex Task Owner** — directive · วางแผน · Context map · วิเคราะห์ · จัดการ Kanban (token เยอะได้) |
| **Cline Agent** | DeepSeek Flash → Pro (implement) · **Pro** (verify) | prepaid (per token) | Implementer **+ Verifier** (stepwise-approval + vision tool) |
| **Human** | — | — | Gate Keeper + Witness (ไม่ใช่ agent — ปลุก agent ณ จุด handoff) |

- **Rule**: คิด/วางแผน/วิเคราะห์ → **Argon (monthly)** วนกี่รอบก็ marginal ≈ 0 ·
  implement → DeepSeek (prepaid) เฉพาะ Phase 4 · verify → **DeepSeek Pro** (prepaid)
- **Image rule**: DeepSeek ไม่รับ base64 → Cline อ่านภาพผ่าน **vision tool** (Gemini multimodal ผ่าน
  `app.ai.providers.get_gemini_model()` → คืน **ข้อความ**) แล้วเทียบ UI landmark เอง · `token_guard` ยังกัน base64 ตรงเข้าตัวโมเดล
  - ⚠️ **สถานะ: concept** — repo ยังไม่มีสคริปต์ vision tool → follow-up `TASK` card (ไม่บล็อก loop; ระหว่างนี้ใช้ DOM text ถ้าไม่มีภาพ)
- **ไม่มี Flash ใน loop แล้ว** — งาน verification เดิมที่ใช้ Gemini Flash ย้ายมาเป็น **Cline + DeepSeek Pro**

## 2. GitHub เป็น shared medium

- Argon อ่าน/เขียนไฟล์ใน repo ได้เองผ่าน GitHub integration → **ไม่ต้อง automate browser** (กัน selector เปราะ)
- Argon **เขียน "แผน" เอง (PHASE 1)** แล้ว **อ่าน "ผล" (PHASE 4–5)** — ไม่รันโค้ด ไม่เห็น live browser
  (Anti-Mock Guardrail §8 · 4 งานวิเคราะห์ดู §5)
- Branch convention:
  - `main` — protected · merge ได้เฉพาะโค้ดที่ test + live-verified แล้ว
  - `task/<slug>` — branch ของ Cline (worktree `~/.cline/worktrees/<task-slug>`)
  - `plan/<slug>` — branch ที่ Argon เขียน directive/แผน draft
- Prereq (ยังไม่ทำ): private repo + `git remote add origin` + audit git history ว่าไม่มี `.env`/session หลุด
  (`.gitignore` ครอบ `.env`, `data/`, `*.db`, `*session_state*.json` แล้ว)

## 3. The loop (Phase 0 → 5)

```
PHASE 0  Argon อัปเดต directive (รับ learning จาก loop ที่แล้ว)      [Argon · ไม่มีคน]
PHASE 1  Argon ร่างแผน TASK-xxx.md + Context map (DRAFT)              [Argon · ไม่มีคน]
PHASE 2  Argon self-review แผน (direction / consistency)              [Argon · ไม่มีคน]
PHASE 3  คน merge PR แผน → main → READY (freeze scope)    🔴 Human gate #1
PHASE 4  Cline implement + unit test + live test        🔴 Human gates ที่ T2
PHASE 4b Cline verify (stepwise + vision tool) → verdict  [Cline · DeepSeek Pro]
PHASE 4c คน merge PR ผล → main (squash)                   🔴 Human gate #2
PHASE 5  Argon วิเคราะห์ (แผน + ผล เท่านั้น) → 4 งาน   [Argon · ไม่มีคน]
         │  learning ไหลกลับเข้า PHASE 0 ของ loop ถัดไป
         └──────────────────────────────────────────────►
```

Lead time: planning (0–2) วิ่งอัตโนมัติบน Argon (monthly) · คนถูกเรียกแค่ gate ที่เสี่ยง (3, 4c + T2)

## 4. Handoff mechanism (Argon ↔ Cline)

Argon (web) **เรียก Cline ตรงๆ ไม่ได้** และ Cline **ปลุก Argon ไม่ได้** (Argon เป็น web chat ไม่ได้รันรอเหตุการณ์)
→ ตัวกลางคือ **GitHub repo (ส่งไฟล์) + มนุษย์ (ปลุก agent ณ จุด handoff)** · ทุกจุด handoff ตรงกับ human gate ที่มีอยู่แล้ว

| ทิศทาง | ใครเริ่ม | กลไก |
|---|---|---|
| Argon → Cline (แผน) | Argon | commit `plan/<slug>` + เปิด **PR → main** + สร้าง **GitHub Issue** "plan ready (PHASE 1)" 📮 → มนุษย์เห็น notif → **merge PR = gate #1** → แผนอยู่ `main` |
| Cline → เริ่มงาน | มนุษย์ | บอก Cline (local): "เริ่มการ์ด TASK-xxx" → Cline `git fetch` + สร้าง worktree จาก `main` + อ่านแผน |
| Cline → Argon (ผล) | Cline | commit `task/<slug>` + เขียน `## Cline Report` + เปิด **PR → main** 📮 → **merge PR = gate #2** → ผลอยู่ `main` |
| Argon → PHASE 5 | มนุษย์ | prompt Argon (web): "รัน PHASE 5 บน TASK-xxx" → Argon อ่านไฟล์ที่ merge แล้วผ่าน GitHub → เขียน `## Argon Analysis` + สร้าง **Issue** "analysis done" 📮 |

- **Notification**: Argon สร้าง GitHub Issue ทุกครั้งที่เขียนแผนเสร็จ (PHASE 1) และวิเคราะห์เสร็จ (PHASE 5)
  → Human ได้ notif ผ่าน GitHub app โดยไม่ต้องเปิดหน้าเช็คเอง · ฝั่ง Cline ใช้ PR เป็น notif ในตัว
- **PR = gate + handoff ในตัวเดียว** — การ merge คือทั้งการอนุมัติ (human gate) และการส่งไฟล์ให้ฝั่งตรงข้าม
- Local poller (แจ้งเตือน LINE เมื่อมี PR พร้อม merge / การ์ด `READY`) เป็น **optional** ไม่บังคับ

## 5. Argon เขียนแผน + อ่านผล → 4 งานวิเคราะห์

**Input (2 artifact ต่อ loop เท่านั้น):**

| Artifact | อยู่ในไฟล์ | อ่านส่วนไหน |
|---|---|---|
| **แผน** | `docs/handoff/TASK-xxx.md` | `## Context`, `## Scope`, `## Steps/Task Decomposition`, `## Acceptance` |
| **ผล** | ไฟล์เดียวกัน | `## Cline Report` (files changed, summary, tests, open questions) + `## Cline Verification` (verdict, live-test) |

**Output = `## Argon Analysis` (เขียนในไฟล์ handoff เดียวกัน):**

| # | งาน Argon | ตอบคำถาม | ปลายทาง |
|---|---|---|---|
| 1 | **Direction alignment** | งานที่ทำใน loop นี้ ตรงกับ Direction (`directive/idea.md` + roadmap) ไหม? อย่างไร? | `direction_alignment:` verdict + เหตุผล |
| 2 | **Directive consistency** | แผน/ผล ขัดกับ `directive/*.md` ไหม? | ≥1 `TASK` card ใหม่ → `[Backlog]` |
| 3 | **Code vuln scan** | ไฟล์ที่เปลี่ยนใน `## Cline Report` มีช่องโหว่ไหม (เทียบ RCA pattern) | ≥1 `TASK` card + RCA entry |
| 4 | **Next loop improvement** | loop นี้เจอปัญหาอะไร → loop หน้าต้องทำอะไร | ป้อนเป็น `## Context` ของการ์ดถัดไป |

## 6. Human อยู่ตรงไหน (มีแค่ 2 บทบาท — ไม่เป็นคอขวด)

| บทบาท | Gate | ทำไมต้องมีคน |
|---|---|---|
| **Gate Keeper (อนุมัติ)** | PHASE 3 merge PR แผน · PHASE 4c merge PR ผลเข้า main | กัน scope creep + กันโค้ดไม่ผ่าน live test หลุดเข้า main |
| **Witness (ยืนยันเหตุการณ์จริง)** | live login/OTP · order เงินจริง · account switch/SBL · live test broker+LINE | Anti-Mock: ต้องเห็นจริง ไม่เชื่อ assertion/โมเดล (stepwise-approval §5) |

**Human ต้อง *ไม่* อยู่ (ไม่งั้นเป็นคอขวด):** PHASE 0–2 (Argon วนแผน + self-review เอง) · T0/T1 โค้ด+unit test ·
PHASE 5 (Argon วิเคราะห์เอง)

**Risk-Tier (ใช้ตัดสินว่า gate ไหนเรียกคน):**
- 🟢 **T0** — code/docs/unit test/headless scrape → อัตโนมัติ
- 🟡 **T1** — logic ไม่แตะ order/OTP/tick → diff audit + report
- 🔴 **T2** — order / OTP / account switch / SBL / live login / **merge main** → บังคับมีคน

## 7. Status state machine (field `Status` ในไฟล์ handoff)

```
DRAFT ──(Argon self-review)──► READY ──(Cline เริ่ม)──► IN_PROGRESS ──► REVIEW ──(Cline verify + คน merge)──► DONE
  ▲                                                                    │
  └────────────── CHANGES_REQUESTED ◄───────────────────────────────────┘
```
- `DRAFT` = Argon ร่างแผน + self-review (PHASE 1–2)
- `READY` = มนุษย์ merge PR แผนแล้ว + freeze scope (PHASE 3) — เปลี่ยน scope ต้องผ่าน review ใหม่
- `IN_PROGRESS` = Cline ทำใน worktree (PHASE 4) · `REVIEW` = รอ Cline verify Stage A–D (PHASE 4b)
- `DONE` = merge main (PHASE 4c) + ลบ worktree + Argon วิเคราะห์เสร็จ (PHASE 5)

## 8. Anti-Mock Guardrail (บังคับ)

Argon เขียนแผนเอง + เห็นผล → ข้อ 2–3 ที่ Argon "สงสัย" เป็น **สมมติฐาน ไม่ใช่หลักฐาน**
→ ต้องยืนยันด้วย test จริง (broker + LINE, headed) + human confirm ก่อน merge เสมอ
→ ห้าม merge main เพราะ "Argon บอกว่าปลอดภัย"

## 9. Token / cost policy

1. PHASE 0–3 + 5 ใช้ **Argon (monthly)** → iterate ฟรี (คิด/วางแผน/วิเคราะห์ token เยอะได้)
2. DeepSeek (prepaid) ใช้เฉพาะ PHASE 4 — implement = DeepSeek Flash default → Pro เมื่อ escalation;
   **verify (PHASE 4b) = Pro เสมอ**
3. ภาพ → Cline อ่านผ่าน vision tool (Gemini vision → ข้อความ) · คง prompt-cache (ห้าม dynamic timestamp ใน rules)
4. วัดผล: `.venv/bin/python scripts/token_report.py --since <date>`

## 10. Cross-references

- `docs/agent/workflow_playbook.md` — Kanban 5 คอลัมน์ + worktree + merge lifecycle
- `docs/agent/token_workflow.md` — token budget + Kanban card policy (DeepSeek implement/verify)
- `docs/agent/handoff_protocol.md` — รูปแบบไฟล์ handoff + Cline Report
- `.agents/skills/stepwise-approval/SKILL.md` — HITL stages A–D + human confirm (Cline verify)
- `.agents/rules/loop_engineering.md` — DECOMPOSE→EXECUTE→VERIFY→REFLECT→REPEAT

## 11. Setup (one-time prerequisite)

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

