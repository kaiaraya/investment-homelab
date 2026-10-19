# Loop Board — Loop 1

> **แทน Kanban** (ปลดระวาง cline-kanban แล้ว) · เจ้าของบอร์ด: **Argon** (Antigravity)
> **4-Agent Hybrid Loop**: **Argon** (Plan/Eval) · **Flash 3.8** (STEP 0a DOM Probe + STEP 3 T2 Witness) · **Jules** (STEP 2a Cloud T0/T1) · **Cline** (STEP 2b Local Triage + Side-Quests)
> รายละเอียดงานต่อใบ → `docs/handoff/TASK-<slug>.md` (ตัวกลางเดียวของ loop)

- **Loop:** 1
- **Opened:** 2026-10-15
- **Closed:** —
- **Directive:** `directive/master_directive_v2.md` · **Scorecard:** `directive/loop_acceptance_and_tasks.md`

## วิธีใช้
- **Argon** = เจ้าของบอร์ด: ย้ายการ์ดระหว่างคอลัมน์ + เพิ่ม/ลบการ์ด + กำหนดโมเดล Jules (`3.6 Flash` / `3.1 Pro`) และสถานะ `PROBE_NEEDED`
- **Flash 3.8 + Human** = รัน **STEP 0a (Pre-Coding Read-Only Probe)** เติม `## DOM / API Contract` ก่อนส่งให้ Jules และรัน **STEP 3 (T2 Live Witness)**
- **Jules (Cloud VM)** = เขียนโค้ด + Unit Test งานหลัก `🟢T0` (`Gemini 3.6 Flash`) / `🟡T1` (`Gemini 3.1 Pro`) ผ่าน `scripts/jules_bridge.py`
- **Cline (Local)** = **(1) STEP 2b Local Triage**: ดึง branch จาก Jules มาตรวจ Diff + รัน `verify_changes.py` กรองก่อนส่ง Argon · **(2) เลนที่ 6 (`🔧 Side-Quests`)**: เคลียร์งาน Low-Priority จาก `Open questions` โดยไม่บล็อก Loop หลัก
- **Human** = gate: อ่านแผน + ยืนยัน Probe → flip `Status` (gate #1) · squash `task/<slug>` → `main` (gate #2)

---

## 🔴 1. Backlog (Argon — Main Loop Candidates)
| # | Task | Tier / Model | Probe | Owner | Status | Handoff |
|---|------|--------------|-------|-------|--------|---------|
| — | — | — | — | — | — | — |

## 🟡 2. Ready / Planning (Argon + STEP 0a Flash Probe — รอ gate #1)
| # | Task | Tier / Model | Probe | Owner | Status | Handoff |
|---|------|--------------|-------|-------|--------|---------|
| 4 | `loop1-4-live-round-b-witness-verification` | 🔴T2 (`Flash 3.8`) | NONE | Flash | IN_PROGRESS — ขั้น 3–4 **BLOCKED**: broker rejects QuickTrade amend (`side H`); รอ decision | `docs/handoff/TASK-loop1-4-live-round-b-witness-verification.md` |

## 🔵 3. In Progress & Local Triage (STEP 2a Jules Cloud → STEP 2b Cline Triage · Flash T2)
| # | Task | Tier / Model | Probe | Owner | Status | Handoff |
|---|------|--------------|-------|-------|--------|---------|
| — | — | — | — | — | — | — |

## 🟢 4. Review / Approval (Flash verify + human witness)
| # | Task | Tier / Model | Probe | Owner | Status | Handoff |
|---|------|--------------|-------|-------|--------|---------|
| — | — | — | — | — | — | — |

## ⚪ 5. Done (human merge แล้ว)
| # | Task | Tier / Model | Probe | Owner | Status | Handoff |
|---|------|--------------|-------|-------|--------|---------|
| 1 | `loop1-1-pillar2-orders-and-margin-lock` (`7bc4bf2`, `14e31de`) | 🟡T1 | DONE | Cline | DONE (unit · live witness in #4) | `docs/handoff/TASK-loop1-1-pillar2-orders-and-margin-lock.md` |
| 2 | `loop1-2-unify-kss-nego-to-quicktrade-inplace` (`d7bde41`, `cd2a24e`) | 🟡T1 | DONE | Cline | DONE (unit · live witness in #4) | `docs/handoff/TASK-loop1-2-unify-kss-nego-to-quicktrade-inplace.md` |
| 3 | `loop1-3-liberator-quote-and-nego-hardening` (`9ed1f5a`) | 🟡T1 | DONE | Cline | DONE (unit+quote API · live witness in #4) | `docs/handoff/TASK-loop1-3-liberator-quote-and-nego-hardening.md` |

---

## 🔧 6. Side-Quests / Open Questions (Cline Local — Non-Blocking, WIP ≤ 1, branch `chore/<slug>`)
> งานเก็บตก Low-Priority จาก `Open questions` ที่ไม่บล็อกวัตถุประสงค์หลักของ Loop ปัจจุบัน (Cline ทำในเครื่อง + กรองส่ง Argon)

| # | Side-Quest | Source Card | Tier | Owner | Status | Branch / Notes |
|---|------------|-------------|------|-------|--------|----------------|
| SQ-1 | `nego-policy-unify-and-dryrun-badge` (รวม `_plan_nego` ของ LIB เข้า `plan_negotiation` + ป้ายหัวการ์ด `DRY-RUN` เมื่อ `DRY_RUN_MODE=True`) | `TASK-loop1-2` Open Q#2, Q#5 | 🟡T1 | Jules (`3.1 Pro`) | DONE (`32dbdf4` via Jules + Cline Triage) | `docs/handoff/TASK-sq1-nego-policy-and-dryrun-badge.md` |
| SQ-2 | `liberator-halt-zero-price-guard` (แปลง `bp`/`op` = `"0"` ช่วง Halt/Pre-open ใน `_to_float` ของ `driver.py` เป็น `None` แทน `0.0`) | `TASK-loop1-3` Open Q#4 | 🟢T0 | Jules (`3.6 Flash`) | READY | `docs/handoff/TASK-sq2-liberator-halt-zero-price-guard.md` |
| SQ-3 | `click2win-runbook-clean-f11` (ล้างข้อความ `(Self-Annealed: ...)` ซ้ำ 75× ที่ค้างใน `learned_workflows/click2win/click2win_order_submit.md`) | `C2W-RCA-006` (`28b3468`) | 🟢T0 | Jules (`3.6 Flash`) | READY | `docs/handoff/TASK-sq3-click2win-runbook-clean-f11.md` |
| SQ-4 | `quicktrade-quote-button-selector` (ปุ่ม Get Quotes ไม่มี id แล้ว → `_fetch_quote` timeout; เปลี่ยนเป็น scoped `input.refreshQuoteBtn` ใต้ td ของ `#eqQuoteSymbol`) | `TASK-loop1-4` pre-flight 2026-10-19 | 🟢T0 | Jules (`3.6 Flash`) | DONE (merged `b58560a`) — unit + live quote PASS | `docs/handoff/TASK-sq4-quicktrade-quote-button-selector.md` |
| SQ-5 | `quicktrade-last-price-from-dom` (`last=None` เพราะหน้าเว็บไม่มี label "Last"; อ่านจาก `span.last` แทน) | SQ-4 live probe 2026-10-19 | 🟢T0 | local fix | DONE (merged `b58560a`) — unit PASS · live last-price ค้างยืนยันตอน witness | `docs/handoff/TASK-sq5-quicktrade-last-price-from-dom.md` |
| SQ-6 | `nego-kss-side-and-quote-path` (side `H`/`C` ไม่รู้จัก + pre-plan ด้วย quote ที่ไม่มี bid/offer) | witness 2026-10-19 | 🟢T0 | local fix | DONE (merged `1df4b01`) — unit 113 passed · live blocked โดย broker rejection | `docs/handoff/TASK-sq6-nego-kss-side-and-quote-path.md` |

---

## Legend

**Tier & Model Routing:**
- 🔍 **STEP 0a (Pre-Coding Probe)** — งานที่แตะ DOM/XHR โบรกเกอร์ ต้องให้ **Flash 3.8 + Human** อ่านค่าจริงใส่ `## DOM / API Contract` ก่อนส่งให้ Jules (`PROBE_NEEDED → PROBE_DONE`)
- 🟢 **T0** — code / docs / unit test / selector ที่มี Contract แล้ว → **Jules (`Gemini 3.6 Flash`)** → **Cline Triage**
- 🟡 **T1** — logic / guardrails / multi-file refactor ที่ไม่แตะ live order/OTP → **Jules (`Gemini 3.1 Pro`)** → **Cline Triage**
- 🔧 **Side-Quest (T0/T1 Low-Priority)** — ประเด็นจาก `Open questions` นอกเส้นทางหลัก → **Cline (`DeepSeek Pro/Flash`)** บน branch `chore/<slug>`
- 🔴 **T2** — order · OTP · account switch · SBL · live login · live browser · merge `main` → **Antigravity IDE (Flash 3.8)** + human witness

**Status (ใน handoff md):** `DRAFT → (PROBE_NEEDED) → READY → IN_PROGRESS → TRIAGE → REVIEW → DONE` (↩ `CHANGES_REQUESTED`)
