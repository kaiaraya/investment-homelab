# Loop Board — LIVE SNAPSHOT

> ⚠️ **SNAPSHOT ONLY — regenerated 2026-10-26 13:53.** The source of truth is the Hermes Kanban board:
> `hermes kanban --board investment-homelab list`. This file is a readable mirror; if the two
> disagree, the Kanban board wins. Regenerate with `python scripts/board_snapshot.py` — never
> hand-edit the live sections.
> **Platform:** Hermes-only. Jules, Cline and the Antigravity IDE loop are **retired**
> (`docs/handoff/TASK-hermes-only-migration.md`). SOP: `docs/agent/kanban_operating_model.md`.
> Card content lives in `docs/handoff/TASK-<slug>.md`.

- **Generated:** 2026-10-26 13:53
- **Counts:** running 1 · ready 0 · todo 0 · scheduled 1 · blocked 6 · triage 1 · review 0 · done 42 · archived 17
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
| `t_5f2d4b60` | **running** | `homelab-build` | 🟡 T1 · 2.11c /short + /borrow pre-trade ต้องบล็อก verdict CACHE_MISS/CACHE_STALE ด้วย (handlers.py ยังเช็คแค่ XD) |
| `t_1e4a05eb` | **scheduled** | `default` | 🔔 เปิดตลาด · 🔴 T2 · 2.8 Witness — SBL borrow → short → return (kss MARGIN 3024959 · ยุบ 2.5 แล้ว) |
| `t_b6749a20` | **blocked** | `default` | 🔔 เปิดตลาด · 🔴 T2 · 2.7 Witness — value BUY 50k → confirm → executor (lib CASH) |
| `t_25ba3820` | **blocked** | `default` | ⏰ ปิดตลาด · 🔴 T2 · 2.9 Witness — Rich Menu + Quick Trade postback |
| `t_15869000` | **blocked** | `default` | ⏰ ปิดตลาด · 🟠 HITL · 2.10 confirm/cancel TTL (human taps) |
| `t_ee3c1ac6` | **blocked** | `default` | ⏰ ปิดตลาด (fix+DRY) · 🟠 HITL · 2.11 XD hard-block on /borrow + /short |
| `t_75795660` | **blocked** | `homelab-build` | 🔴 T2 · [Streaming] · P.4-kss Order submit ผ่าน JS + Anti-Mock |
| `t_e2c587f7` | **blocked** | `homelab-build` | 🔴 T2 · [Liberator] · P.4-lib Order submit ผ่าน JS (buy/sell/change/cancel) + Anti-Mock |
| `t_e3f4fc6f` | **triage** | `default` | 🔧 T0 · Fix test fixture: Liberator account 7-digit (7055938) vs 8-digit (70559382) |

## ✅ ปิดล่าสุด 10 ใบ

| id | completed | title |
|---|---|---|
| `t_a31b5c2b` | 2026-10-26 13:51 | 🟡 T1 · 2.11b SBL check_symbol_risk fail-closed เมื่อ cache ว่าง/เก่า |
| `t_c2b11416` | 2026-10-26 13:46 | 🟢 T0 · 2.2b Draft TTL อ่านจาก settings.CARD_TTL_SECONDS (แทน hardcode 180) |
| `t_17d8aeea` | 2026-10-26 13:15 | 🟢 T0 · 0.1-0.2 Version the JS-first layer + commit P.1-P.5 by topic |
| `t_96f02cf9` | 2026-10-26 12:26 | 🔴 T2 · [SBL Realtime] · P.5 SBL borrow/return ผ่าน JS |
| `t_a1d5c9c4` | 2026-10-26 11:54 | 🔍 0a · [Liberator+Streaming] · P.4a HAR capture — Liberator order + Streaming Ch |
| `t_2c403ecd` | 2026-10-26 11:47 | 🔔 เปิดตลาด · 🔍 0a · 2.0a Probe — quote source สำหรับ value sizing (TradeMan REST |
| `t_ce767c92` | 2026-10-26 11:06 | 🟢 T0 · [Liberator+Streaming] · P.4c Support Stepper (+/-) Price Adjustment & Tic |
| `t_14f992b6` | 2026-10-26 10:51 | 🟢 T0 · [SBL Realtime] · P.5a SBL read JS (PP / inventory / XD-XR) |
| `t_888884c1` | 2026-10-26 10:36 | 🟡 T1 · [Streaming+Liberator] · P.2 Convert read-only scrape → JS-first + Playwri |
| `t_e007f8bb` | 2026-10-26 10:34 | 🟢 T0 · [Streaming+Liberator] · P.4b Value sizing ผ่าน getQuote JS (_broker_quote |

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
