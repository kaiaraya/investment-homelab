# Loop Board — LIVE SNAPSHOT

> ⚠️ **SNAPSHOT ONLY — regenerated 2026-10-30 16:16.** The source of truth is the Hermes Kanban board:
> `hermes kanban --board investment-homelab list`. This file is a readable mirror; if the two
> disagree, the Kanban board wins. Regenerate with `python scripts/board_snapshot.py` — never
> hand-edit the live sections.
> **Platform:** Hermes-only. Jules, Cline and the Antigravity IDE loop are **retired**
> (`docs/handoff/TASK-hermes-only-migration.md`). SOP: `docs/agent/kanban_operating_model.md`.
> Card content lives in `docs/handoff/TASK-<slug>.md`.

- **Generated:** 2026-10-30 16:16
- **Counts:** running 0 · ready 0 · todo 0 · scheduled 0 · blocked 0 · triage 4 · review 0 · done 27 · archived 79
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
| `t_69fed7ac` | **blocked** (T2 witness) | `default` | 🔴 T2 · ไม่มีคำสั่งยกเลิกออเดอร์ — เพิ่ม /cancel &lt;order_no&gt; (KSS + LIB) |
| `t_fc086d6a` | **blocked** (T2 witness, depends `t_3046a05c`) | `default` | 🔴 T2 · SBL Realtime · /return live ยัง fail-closed |
| `t_02c86227` | **blocked** (T2 witness) | `default` | 🔴 T2 · Streaming · /port kss ไม่เห็น Short position |
| `t_effe2506` | **blocked** (T2 witness) | `default` | 🔴 T2 · Liberator · /sell + /nego lib ยังไม่เคย witness |
| `t_7224ce87` | **ready** 🟢 T0 | `homelab-build` | รีเฟรช /help + sweep read-only /cash /port lib /size |
| `t_f7e4c35a` | **ready** 🟢 T0 | `homelab-build` | vision_analyze อ่านภาพไม่ได้ (patch inlineData หาย) |
| `t_3046a05c` | **done** | `default` | 🟡 T1 · SBL Realtime · กระทบยอด lot (broker ledger = truth) |
| `t_0bd598ba` | **triage** | `homelab-build` | LINE image ingestion → data/screenshots/inbox + attach to referenced card |

## ✅ ปิดล่าสุด 10 ใบ

| id | completed | title |
|---|---|---|
| `t_3046a05c` | 2026-11-02 15:20 | 🟡 T1 · SBL · reconcile lots กับ broker (created 4 / closed 4) |
| `t_1e4a05eb` | 2026-11-02 14:40 | 🔴 T2 · Witness live SBL borrow & short cycle via LINE CLI |
| `t_85a65a8a` | 2026-10-30 15:15 | 🟢 T0 · LINE CLI · Add handler round-trip tests for portfolio action buttons (car |
| `t_c08412d2` | 2026-10-30 14:58 | 🟢 T0 · LINE CLI · พัฒนา Interactive Portfolio Card รวม 2 โบรกเกอร์ พร้อมปุ่มส่งค |
| `t_eff62798` | 2026-10-30 10:00 | 🟢 T0 · LINE CLI · เพิ่มคำสั่ง /size <sym> คำนวณจำนวนหุ้นงบ 50k/75k/100k จากราคาต |
| `t_53b40213` | 2026-10-29 16:48 | 🟢 T0 · LINE CLI · Default omitted trade price to passive 'lure' price (never cro |
| `t_6c73d316` | 2026-10-29 16:05 | 🟡 T1 · LINE CLI · Purge TradeMan & QuickTrade fallbacks → 100% CDP :9333 alignme |
| `t_4b6ed556` | 2026-10-29 15:33 | 🟢 T0 · Fix — Wire KSS LINE amend/nego to Streaming CDP change_order_native |
| `t_6d68fc2f` | 2026-10-29 12:57 | 🟢 T0 · SIDE-QUEST: OrderStatus enum ขาด UNCONFIRMED → /api/v1/orders 500 |
| `t_f22dbda2` | 2026-10-29 11:57 | 🏗️ Architecture: Order State Synchronization & DB Design (Broker vs Local DB) |
| `t_b6749a20` | 2026-10-29 10:52 | Witness live value BUY order flow via LINE to broker |

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
