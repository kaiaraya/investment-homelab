# Loop Board — LIVE SNAPSHOT

> ⚠️ **SNAPSHOT ONLY — regenerated 2026-10-28 19:29.** The source of truth is the Hermes Kanban board:
> `hermes kanban --board investment-homelab list`. This file is a readable mirror; if the two
> disagree, the Kanban board wins. Regenerate with `python scripts/board_snapshot.py` — never
> hand-edit the live sections.
> **Platform:** Hermes-only. Jules, Cline and the Antigravity IDE loop are **retired**
> (`docs/handoff/TASK-hermes-only-migration.md`). SOP: `docs/agent/kanban_operating_model.md`.
> Card content lives in `docs/handoff/TASK-<slug>.md`.

- **Generated:** 2026-10-28 19:29
- **Counts:** running 1 · ready 0 · todo 3 · scheduled 0 · blocked 2 · triage 1 · review 0 · done 12 · archived 79
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
| `t_ccaf8647` | **running** | `homelab-build` | 🟡 T1 · LINE CLI · retire /login /logout /quicktrade /halt → RustDesk |
| `t_53b32b72` | **todo** | `homelab-build` | 🟡 T1 · LINE CLI · add /sync portfolio|orders|borrow|balance |
| `t_ee9bd654` | **todo** | `homelab-build` | 🟡 T1 · LINE CLI · add /nego all (ต่อราคาทั้ง 2 โบรกเกอร์) |
| `t_4458dea1` | **todo** | `homelab-build` | 🟢 T0 · LINE CLI · update /help text + board snapshot |
| `t_b6749a20` | **blocked** | `default` | Witness live value BUY order flow via LINE to broker |
| `t_99cc85d7` | **blocked** | `default` | [ตลาดเปิด] 🔴 T2 · N6: HITL witness ต่อราคาผ่าน Rich Menu ในตลาด |
| `t_1e4a05eb` | **triage** | `default` | 🔔 เปิดตลาด · 🔴 T2 · 2.8 Witness — SBL borrow → short → return (kss MARGIN 3024959 · ยุบ 2.5 แล้ว) |

## ✅ ปิดล่าสุด 10 ใบ

| id | completed | title |
|---|---|---|
| `t_5b35b939` | 2026-10-28 18:02 | 🟢 T0 · SNAP.2: wire cron 09:15 Mon-Fri → run pre_market_snapshot.py (no-agent) + |
| `t_f6ade9d5` | 2026-10-28 17:58 | 🟢 T0 · SNAP.1: scripts/pre_market_snapshot.py — อ่าน KSS+LIB (balance+portfolio+ |
| `t_e4cc1add` | 2026-10-28 10:59 | 🔍 0a · SNAP.0a: Verify broker read-only REST endpoints (KSS+LIB) via CDP daemon  |
| `t_4e823047` | 2026-10-28 09:01 | 3.2 Port Regime & Wave Thrust Engine |
| `t_d326ce5f` | 2026-10-28 08:29 | 3.1 Port Compass Engine & Setup Scoring |
| `t_49794e8b` | 2026-10-28 08:00 | 3.0a STEP 0a Probe: Model 19 Code Map & Golden Snapshot |
| `t_ee3c1ac6` | 2026-10-27 08:45 | ⏰ ปิดตลาด (fix+DRY) · 🟠 HITL · 2.11 XD hard-block on /borrow + /short |
| `t_b558906e` | 2026-10-26 20:32 | [ตลาดปิด] 🟡 T1 · N4: ส่ง target_price ลง negotiate_order_price (KSS) |
| `t_e7a85d71` | 2026-10-26 20:31 | [ตลาดปิด] 🟢 T0 · N5: เปลี่ยน rich menu ช่อง 4 เป็น ⚡ ต่อราคา (action=nego_menu) |
| `t_0c99d89c` | 2026-10-23 12:59 | ⏰ ปิดตลาด · 🟡 T1 · 2.6 Value sizing edge cases (tick/board-lot/budget/G6) |

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
