# Loop Board — LIVE SNAPSHOT

> ⚠️ **SNAPSHOT ONLY — regenerated 2026-10-27 16:56.** The source of truth is the Hermes Kanban board:
> `hermes kanban --board investment-homelab list`. This file is a readable mirror; if the two
> disagree, the Kanban board wins. Regenerate with `python scripts/board_snapshot.py` — never
> hand-edit the live sections.
> **Platform:** Hermes-only. Jules, Cline and the Antigravity IDE loop are **retired**
> (`docs/handoff/TASK-hermes-only-migration.md`). SOP: `docs/agent/kanban_operating_model.md`.
> Card content lives in `docs/handoff/TASK-<slug>.md`.

- **Generated:** 2026-10-27 16:56
- **Counts:** running 0 · ready 0 · todo 0 · scheduled 0 · blocked 2 · triage 1 · review 0 · done 65 · archived 18
- **Directive:** `directive/master_directive_v2.md` · **Scorecard:** `directive/loop_acceptance_and_tasks.md`
- **เปิด acceptance:** Loop 1 = native in-place `change_order` ทำงานได้ทั้ง Streaming + Liberator

## วิธีใช้
- **Kanban board** = ความจริง: status/assignee/evidence อยู่บนการ์ด และ gateway dispatch เอง
- **`default` (planner)** = เขียน/แก้การ์ด, `set-model`, verdict, squash `main`
- **`homelab-build`** = T0 (`gemini-3.8-flash`) / T1 (`gemini-3.1-pro`) เขียนโค้ด + unit test
- **`homelab-review`** (`gemini-3.1-pro`) = diff audit + `verify_changes.py` + §Review Report
- **`homelab-colab`** = งาน GPU/CPU ผ่าน `colab` CLI
- **Human** = gate #1 (อนุมัติแผน/probe) · gate #2 (squash `main`) · witness 🔴T2 ที่หน้าจอ

---

## 🟨 การ์ดที่ยังเปิดอยู่ (live)

| id | status | assignee | title |
|---|---|---|---|
| `t_1e4a05eb` | **blocked** | `default` | 🔔 เปิดตลาด · 🔴 T2 · 2.8 Witness — SBL borrow → short → return (kss MARGIN 3024959 · ยุบ 2.5 แล้ว) |
| `t_99cc85d7` | **blocked** | `default` | [ตลาดเปิด] 🔴 T2 · N6: HITL witness ต่อราคาผ่าน Rich Menu ในตลาด |
| `t_b6749a20` | **triage** | `default` | Witness live value BUY order flow via LINE to broker |

## ✅ ปิดล่าสุด 10 ใบ

| id | completed | title |
|---|---|---|
| `t_75795660` | 2026-10-27 16:32 | [ตลาดเปิด] 🔴 T2 · [Streaming] · P.4-kss Order submit ผ่าน JS + Anti-Mock |
| `t_305334e5` | 2026-10-27 16:08 | 🟡 T1 · [Streaming] · SQ-7 native change ผ่าน REST (PATCH /change) แทน cancel+rep |
| `t_15de71eb` | 2026-10-27 15:25 | 🟡 T1 · [Streaming] · SQ-8 JS place + cancel snippet + Anti-Mock (ปิดช่องว่างก่อน |
| `t_15869000` | 2026-10-27 13:24 | ⏰ ปิดตลาด · 🟠 HITL · 2.10 confirm/cancel TTL (human taps) |
| `t_14aeac1b` | 2026-10-27 11:57 | 🟡 T1 · [Liberator] · P.4-lib-exec wire LINE CLI /buy → JS snippet executor (แทน  |
| `t_e2c587f7` | 2026-10-27 11:38 | [ตลาดเปิด] 🔴 T2 · [Liberator] · P.4-lib Order submit ผ่าน JS (buy/sell/change/ca |
| `t_ee3c1ac6` | 2026-10-27 08:45 | ⏰ ปิดตลาด (fix+DRY) · 🟠 HITL · 2.11 XD hard-block on /borrow + /short |
| `t_2293ae5f` | 2026-10-26 20:40 | [ตลาดปิด] 🟢 T0 · /sbl sync ยัง launch Chromium clone — ต่อ sbl_read.js ผ่าน CDP  |
| `t_b558906e` | 2026-10-26 20:32 | [ตลาดปิด] 🟡 T1 · N4: ส่ง target_price ลง negotiate_order_price (KSS) |
| `t_e7a85d71` | 2026-10-26 20:31 | [ตลาดปิด] 🟢 T0 · N5: เปลี่ยน rich menu ช่อง 4 เป็น ⚡ ต่อราคา (action=nego_menu) |

---

## 📜 ประวัติ Loop 1 (frozen 2026-10-26 — อ่านอย่างเดียว)

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

**Tier & Model Routing (อัปเดต 2026-10-26):**
- 🔍 **STEP 0a (Probe)** — งานที่แตะ DOM/XHR โบรกเกอร์ ต้อง probe แบบ read-only + headed มีคนยืนยันหน้าจอ แล้วเติม `## DOM / API Contract` ก่อนปล่อยการ์ดจาก `blocked` (`PROBE_NEEDED → PROBE_DONE`)
- 🟢 **T0** — code / docs / unit test / selector ที่มี Contract แล้ว → lane `homelab-build` (`gemini-3.8-flash`) → lane `homelab-review`
- 🟡 **T1** — logic / guardrails / multi-file refactor ที่ไม่แตะ live order/OTP → lane `homelab-build` (`gemini-3.1-pro` via `set-model`) → lane `homelab-review`
- 🔧 **Side-Quest / idea ใหม่** — ประเด็นจาก `Open questions` นอกเส้นทางหลัก → การ์ด `--triage` (specifier เติม body) ไม่บล็อก loop หลัก
- ☁️ **Colab** — งาน GPU/CPU (model 19, Monte Carlo, EOD ingest) → lane `homelab-colab` (`colab` CLI, artifact ผ่าน Drive)
- 🔴 **T2** — order · OTP · account switch · SBL · live login · live browser · merge `main` → `default` + human witness (headed, `DRY_RUN_MODE=false` เฉพาะ run)

**Status (ใน handoff md):** `DRAFT → (PROBE_NEEDED) → READY → IN_PROGRESS → TRIAGE → REVIEW → DONE` (↩ `CHANGES_REQUESTED`)
