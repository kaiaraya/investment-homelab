# Hybrid Handoff — Argon ↔ Flash 3.8 (Probe/HITL) ↔ Jules (Cloud T0/T1) ↔ Cline (Triage/Side-Quests)

> SOP ของ Development Loop แบบ **4-Agent Hybrid** โดยใช้ **folder เดียวกันเป็นศูนย์กลาง** + **`scripts/jules_bridge.py`** เชื่อม Cloud VM ของ **Google Jules** (`100 sessions/day` บนแพ็กเกจ PRO)
> — **ไม่ใช้ GitHub PR/Issue UI · ไม่มี Kanban** (`cline-kanban` ปลดระวางแล้ว)
> **มนุษย์ = Gate Keeper + Witness + relay**

---

## 1. Actors & model assignment

| Actor | Surface | Model | Tier | บทบาท | เขียน |
|---|---|---|---|---|---|
| **Argon** | Antigravity (local) | Argon/Pro | Plan + STEP 5 | Complex Task Owner — directive · แผน · Context map · วิเคราะห์ · เจ้าของ board | `directive/*.md`, แผนใน `docs/handoff/TASK-*.md`, `docs/board/loop_board.md`, `## Argon Analysis` |
| **Flash** | Antigravity IDE | **Flash 3.8** (multimodal) | 🔍 STEP 0a Probe + 🔴 T2/HITL | **(1) Pre-Coding Read-Only DOM/API Probe** · **(2) Live runner + witness (STEP 3)** + RCA | `## DOM / API Contract`, `## Verification & Stepwise Approval`, `data/screenshots/`, `rca/`, `learned_workflows/` |
| **Jules** | Google Jules (Cloud VM) | **T0 = Gemini 3.6 Flash**<br>**T1 = Gemini 3.1 Pro** | 🟢🟡 T0/T1 (Main Loop) | Primary Implementer (code + unit test ใน Cloud VM แยกขาดจาก `.env`/session จริง) | code (`app/**`, `tests/**`) + `## Jules Report` |
| **Cline** | Cline plugin (local) | **Plan=DeepSeek Pro · Act=DeepSeek Flash** | 🔎 STEP 2b Triage + 🔧 Side-Quest | **(1) Pre-Argon Local Triage** (ตรวจ Diff/Invariants + รัน `verify_changes.py` ในเครื่อง) · **(2) เคลียร์งาน Low-Priority Open Questions** | `## Cline Triage Report` + Side-Quest fixes (`chore/<slug>`) |
| **Human** | — | — | gate + witness | ยืนยันหน้าจอ Probe (STEP 0a) · อนุมัติแผน (gate #1) · ยืนยัน live (STEP 3) · merge `main` (gate #2) | flip `Status` · merge `task/<slug>` → `main` |

---

## 2. The Loop (STEP 0 → 5 + Side-Quest Lane)

```
STEP 0   Argon อัปเดต directive + ร่างแผน TASK-<slug>.md (+ ระบุว่าต้องใช้ Probe หรือไม่)          [Argon]            DRAFT
STEP 0a  (ถ้าแตะ DOM/XHR) Flash 3.8 + Human รัน Read-Only Probe → ล็อก `## DOM / API Contract`    [Flash · Human]    PROBE_DONE → READY
STEP 1   Human อ่านแผน → flip Status (gate #1) + `jules_bridge.py push-plan` & `prompt`          🔴 Human gate #1   IN_PROGRESS
STEP 2a  Jules (Cloud VM) เขียนโค้ด + Unit Test (T0=3.6 Flash / T1=3.1 Pro) → `## Jules Report`  [Jules Cloud]      TRIAGE
STEP 2b  `jules_bridge.py pull-branch` → Cline กรองงานในเครื่อง + รัน `verify_changes.py` ซ้ำ      [Cline Local]      REVIEW
STEP 3   (ถ้ามี T2) Flash 3.8 + Human Witness รันทดสอบสด → `## Verification` + `### Live Evidence` [Flash · Human]    REVIEW (PASS)
STEP 4   Human squash `task/<slug>` → `main` (gate #2)                                           🔴 Human gate #2   DONE
STEP 5   Argon วิเคราะห์ (แผน+ผลผ่านการกรองของ Cline) → `## Argon Analysis` → แตกการ์ด/Side-Quest  [Argon]            → STEP 0
```

### ความแตกต่างระหว่าง `STEP 0a (Pre-Coding Probe)` vs `STEP 3 (T2 Live Witness)`
| มิติ | 🔍 STEP 0a: Pre-Coding Probe | 🔴 STEP 3: T2 Live Witness |
|---|---|---|
| **จังหวะเวลา** | **ก่อนเขียนโค้ด** (ก่อนส่งงานให้ Jules) | **หลังเขียนโค้ดและผ่าน Unit Test/Cline Triage แล้ว** |
| **การกระทำบนหน้าเว็บ** | **Read-Only 100%** (อ่าน DOM selector, ดัก XHR JSON schema) **ห้ามกด Submit/Change/OTP เด็ดขาด** | กดทดสอบ Flow จริง (เช่น `/login`, `/nego` staging หรือ live amend) |
| **หน้าที่ของคน (Human)** | ช่วยเปิดหน้าจอ/ยืนยันว่าอยู่ถูกบัญชีและถูกหน้า | เป็นพยาน (Witness) ยืนยันว่าผลลัพธ์ตรงกับหน้าจอโบรกเกอร์และมือถือ |
| **ผลลัพธ์ที่ได้** | หัวข้อ `## DOM / API Contract` ใน `TASK-<slug>.md` เพื่อให้ Jules เขียนโค้ดบน Cloud VM โดยไม่ต้องเดา | หัวข้อ `## Verification & Stepwise Approval` + `### Live Evidence` |

---

## 3. บทบาทคู่ของ Cline (Pre-Argon Filter & Side-Quest Handler)

1. **STEP 2b — ด่านกรองก่อนส่งมอบให้ Argon (`## Cline Triage Report`)**:
   - เมื่อดึง branch ของ Jules ลงมาเป็น `task/<slug>` ด้วย `scripts/jules_bridge.py pull-branch`
   - Cline อ่านเฉพาะ `git diff main...task/<slug>` และไฟล์ Handoff (ประหยัด Token สูงสุด)
   - รัน `.venv/bin/python scripts/verify_changes.py <changed files>` ในเครื่อง Homelab
   - ตรวจเช็คกฎเหล็ก (Anti-Mock, Broker Isolation, Zero-OTP, Scope boundary) หากมีจุดบกพร่องเล็กน้อย Cline แก้ต่อบน `task/<slug>` ได้ทันที แล้วสรุป `## Cline Triage Report` สั้นกระชับให้ Argon
2. **🔧 Side-Quest Lane — เคลียร์ประเด็น Low-Priority (`Open questions`)**:
   - ประเด็นที่พบใน `Open questions` ซึ่งไม่ได้บล็อกเป้าหมายหลักของ Loop ปัจจุบัน จะถูกวางไว้ในตาราง **`🔧 6. Side-Quests / Open Questions`** บน `docs/board/loop_board.md`
   - Cline หยิบไปทำในเครื่องบน branch `chore/<slug>` (WIP ≤ 1) เมื่อทำเสร็จและผ่าน `verify_changes.py` แล้วจึงส่งให้ Human squash เข้า `main` และให้ Argon รับทราบ

---

## 4. Safety & Anti-Mock Guardrails สำหรับ Jules + Cline

1. **Pre-Push Security Gate (`jules_bridge.py check-safety`)**: ห้ามมี `.env`, `data/*session*.json`, `*.db`, หรือ `data/screenshots/*` อยู่ใน Git index ก่อน push ไปยัง `origin` (`kaiaraya/investment-homelab`) เด็ดขาด
2. **Pre-Coding Probe Gate**: สคริปต์ `jules_bridge.py prompt` และ `push-plan` จะบล็อกทันทีหากไฟล์ Handoff ระบุ `Pre-Coding Probe: PROBE_NEEDED` แต่ยังไม่ได้ทำ Probe (`PROBE_DONE` + `## DOM / API Contract`)
3. **Physical T2 Block**: งาน `🔴 T2` ห้ามรันบน Jules เด็ดขาด (`jules_bridge.py` บล็อกอัตโนมัติ) ต้องรันผ่าน Flash 3.8 + Human Witness เท่านั้น
