# Phase & Milestone Review — Investment Homelab

- **Date:** 2026-10-04
- **Prepared by:** Cline (assisted)
- **Status:** DRAFT — pending owner confirmation on open decisions

---

## 1. Executive Summary

The system has outgrown its original **Phase 1/2/3** naming and now operates as a
**6-Pillars Modular Gateway + Agentic Layer (Pillar 7)**. The *code* is already aligned
with Nick Saraev's DOE / PT-MRO framework. The *documentation & knowledge-base folder
layout*, however, has drifted: stale phase names, a mis-named master directive, and
contradictory RCA file paths. This document reconstructs the timeline, audits current
status, and proposes a **docs-only restructure** (no code changes).

---

## 2. Reconstructed Milestone Timeline

| Milestone | Original scope | Current status |
|---|---|---|
| **Phase 1** | **Foundation & Connectivity** — KDE Connect, LINE OOB, multi-broker OTP login, account switch + portfolio read, session persistence, per-broker RCA | ✅ Implemented (see §2.1) |
| **Phase 2** | **Trade Execution Engine** — place/cancel/modify orders, odd-lot guard, multi-account capability guards, HITL gate | ✅ Implemented (see §2.2) |
| **Phase 3** | **Trading Strategy** — Action Exit / Price Negotiation / Action Entry, driven by the **DeepSeek** AI interpreter | ✅ Implemented (see §2.3) |
| **6 Pillars** | Session / Monitor / Trade / SBL / Portfolio / Strategy | 🟢 33 of 37 features Done; 4 Pending Market Open |
| **Pillar 7 (Agentic)** | DOE/PT-MRO: sub-agents, dual-store memory, orchestrator | ✅ Implemented, not yet in roadmap matrix |

### 2.1 Phase 1 — Foundation & Connectivity (owner-defined)

Owner's definition of Phase 1, cross-checked against live code:

| # | Phase 1 requirement | Code evidence | Status |
|---|---|---|---|
| 1 | Connect to KDE Connect (mobile bridge) correctly | `app/console.py` (`/session/kdeconnect/ping`), D-Bus `smartphonedisconnected` check, `session_connect_all` KDE refresh | ✅ |
| 2 | Use LINE as out-of-band communication | `app/services/line_service.py` (`push_message`, `push_progress_update`, webhook + postback HITL) | ✅ |
| 3 | Connect to Krungsri / Click2Win / Liberator with OTP (where required) | `session_login_broker` (CLICK2WIN/TRADEMAN/LIBERATOR/SETTRADE_OPENAPI), `app/brokers/*/driver.py`, `app/ai/otp_agent.py` | ✅ |
| 4 | Switch account & read each portfolio correctly | `portfolio_switch_account`, `portfolio_get_holdings`, `app/browser/broker_factory.py` | ✅ |
| 5 | Maintain session over time (avoid frequent re-login) | `app/browser/session_sentinel.py` (auto-reconnect, cookie restore, Zero-OTP) | ✅ |
| 6 | Root-cause analysis of each broker login mistake → learn workflow | `.agents/rules/broker_pdca_rca.md` (per-broker RCA files) + `rca/<broker>/` | ✅ (⚠️ path contradiction — §4.7) |

#### 2.1.1 Related Files (repo-relative paths)

| # | Requirement | Files |
|---|---|---|
| 1 | KDE Connect → mobile | `app/services/kdeconnect_service.py` · `app/services/kdeconnect_cli.py` · `app/api/v1/endpoints/session.py` (`POST /kdeconnect/ping`, L154) · `app/console.py` |
| 2 | LINE out-of-band | `app/services/line_service.py` · `app/api/v1/endpoints/webhook_line.py` · `app/core/security.py` (`verify_line_signature`) |
| 3 | Broker OTP login | `app/mcp/pillars/pillar1_session.py` · `app/browser/broker_factory.py` · `app/browser/auth_driver.py` · `app/ai/otp_agent.py` · `app/brokers/krungsri/plugin.py` + `app/browser/trademan_driver.py` · `app/brokers/click2win/plugin.py` + `app/browser/click2win_driver.py` + `app/browser/click2win_auth_driver.py` · `app/brokers/liberator/plugin.py` + `app/brokers/liberator/driver.py` · `app/brokers/settrade_openapi/plugin.py` |
| 4 | Switch account + read portfolio | `app/mcp/pillars/pillar5_portfolio.py` · `app/browser/broker_factory.py` · `app/services/portfolio_overview_service.py` · **Krungsri** `app/brokers/krungsri/plugin.py` (`get_portfolio`, `switch_account_type`) + `app/browser/trademan_driver.py` (`switch_account`) · **Click2Win** `app/brokers/click2win/plugin.py` (`get_portfolio`, `switch_account_type`) + `app/browser/click2win_driver.py` (`switch_account_type`) · **Liberator** `app/brokers/liberator/plugin.py` (`get_portfolio`) + `app/brokers/liberator/driver.py` · **Settrade Open API** `app/brokers/settrade_openapi/plugin.py` (`get_portfolio`) |
| 5 | Maintain session | `app/browser/session_sentinel.py` · `app/core/config.py` (`SESSION_STATE_PATH`) · `app/browser/popup_manager.py` · `app/browser/tab_manager.py` |
| 6 | Per-broker RCA | `.agents/rules/broker_pdca_rca.md` · `rca/krungsri/rca_krungsri_trademan.md` · `rca/click2win/rca_settrade_click2win.md` · `rca/liberator/rca_liberator.md` |

#### 2.1.2 Cross-Cutting Files (used by 2+ requirements)

| File | Requirements served |
|---|---|
| `app/services/kdeconnect_service.py` | **#1** (bridge) **+ #3** — `poll_active_notifications()` returns `OTPPayload` → KDE Connect is *also* an inbound OTP channel |
| `app/services/line_service.py` | **#2** (OOB) **+ #3** — `push_message()` asks for OTP, webhook receives it back |
| `app/browser/broker_factory.py` | **#3** (driver selection) **+ #4** (account switch) |
| `app/mcp/pillars/pillar1_session.py` | **#1** (`session_connect_all`) **+ #3** (`session_login_broker`) |
| `app/browser/session_sentinel.py` | **#5** (session) **+ #2** (`line_service.push_message`) **+ #3** (OTP prompt on reconnect) |

#### 2.1.3 Relationship Insight — the Connectivity Triangle

OTP is **dual-channel**: it can arrive via **KDE Connect** (`kdeconnect_service.poll_active_notifications`) *or* **LINE** (`line_service` webhook), both funneling into `app/ai/otp_agent.py` for parsing before reaching the broker driver. Requirements #1, #2, #3 therefore form one tightly-coupled unit:

```
KDE Connect ──┐
              ├──► app/ai/otp_agent.py ──► broker driver (login)
LINE webhook ─┘
```

### 2.2 Phase 2 — Trade Execution Engine (owner-defined)

Owner's definition of Phase 2, cross-checked against live code:

| # | Phase 2 requirement | Code evidence | Status |
|---|---|---|---|
| 1 | Place orders (Buy/Sell, Long/Short) | `app/mcp/pillars/pillar3_trade.py` → `trade_place_order()` (L48) | ✅ |
| 2 | Cancel orders | `app/mcp/pillars/pillar3_trade.py` → `trade_cancel_order()` (L205) | ✅ |
| 3 | Modify order price | `app/mcp/pillars/pillar3_trade.py` → `trade_modify_price()` (L229) | ✅ |
| 4 | Odd-lot / board-lot guard | `app/services/validator.py` → `validate_board_lot()` (L54), `validate_tick_size()` (L68), `validate_order_value()` (L87), `validate_short_uptick()` (L158) | ✅ |
| 5 | Multi-account capability guards | `app/schemas/account.py` → `AccountCapability` + `account_guardrail.validate_capability()`; enforced at `pillar3_trade.py:81` | ✅ |
| 6 | HITL gate (live + sandbox) | `app/core/config.py` → `ENABLE_HITL_LIVE_GATE` (L91), `ENABLE_HITL_SANDBOX_GATE` (L92); `app/api/v1/endpoints/orders.py:111-112` | ✅ |

#### 2.2.1 Related Files — Trade Execution (per broker, mirrors §2.1.1)

| Broker | Place | Cancel | Modify |
|---|---|---|---|
| Krungsri | `app/brokers/krungsri/plugin.py` `place_order()` (L91) + `app/browser/trademan_driver.py` `execute_order()` (L489) | `app/brokers/krungsri/plugin.py` `cancel_order()` (L108) | `app/browser/trademan_driver.py` `modify_order_price()` (L795) |
| Click2Win | `app/brokers/click2win/plugin.py` `place_order()` (L124) + `app/browser/click2win_driver.py` `execute_order()` (L328) | `app/brokers/click2win/plugin.py` `cancel_order()` (L148) + `app/browser/click2win_driver.py` `cancel_order()` (L761) | `app/browser/click2win_driver.py` `modify_order_price()` (L814) |
| Liberator | `app/brokers/liberator/plugin.py` `place_order()` (L121) + `app/brokers/liberator/driver.py` `execute_order()` (L568) | `app/brokers/liberator/plugin.py` `cancel_order()` (L177) + `app/brokers/liberator/driver.py` `cancel_order()` (L727) | *(no native modify — cancel + replace)* |
| Settrade Open API | `app/brokers/settrade_openapi/plugin.py` `place_order()` (L81) | `app/brokers/settrade_openapi/plugin.py` `cancel_order()` (L91) | via REST amend |

#### 2.2.2 Cross-Cutting / Shared Trade Files

| File | Role |
|---|---|
| `app/services/validator.py` | `PreTradeValidator`: board-lot, tick size, value ceiling, short-uptick, idempotency |
| `app/services/trade_dispatcher.py` | 3-tier guardrails (PIN challenge, LIVE value limit `LIVE_ORDER_VALUE_LIMIT_THB`, visual badges); `dispatch_order`, `dispatch_price_modification` |
| `app/services/trade_center_service.py` | batch approval card, `execute_confirmed_order`, `_ensure_sbl_borrowed` |
| `app/schemas/account.py` | `AccountType`, `AccountCapability`, `account_guardrail`, `account_context` |
| `app/api/v1/endpoints/orders.py` | HITL gate enforcement (L111–112) |

### 2.2.3 Order-Type Capability Matrix (per broker)

Owner-defined Phase 2 order taxonomy — three families, cross-referenced to the canonical
enums and enforced per broker. One broker need not support all families.

#### Order vocabulary (canonical enums)

| Family | Sides | Position | Source |
|---|---|---|---|
| 1. Normal (Equity) | `BUY`, `SELL` | — | `app/schemas/order.py` `OrderSide` (L7–12) |
| 2. Future (TFEX) | `LONG`, `SHORT` | `OPEN`, `CLOSE`, `AUTO` | `order.py` `OrderSide` + `OrderPosition` (L15–18) |
| 3. SBL — trade leg | `SHORT`, `COVER` | — | `order.py` `OrderSide` |
| 3. SBL — lending leg | Borrow, Return | — | `app/mcp/pillars/pillar4_sbl.py` `sbl_borrow_stock` / `sbl_return_stock` |

#### Per-broker support

| Broker | 1. Buy/Sell | 2. TFEX Long/Short (Open/Close/Auto) | 3. SBL Short/Cover | 3. SBL Borrow/Return |
|---|---|---|---|---|
| Click2Win | ✅ `EQUITY` | ✅ `DERIVATIVES` | ❌ | ❌ |
| Krungsri | ✅ `CASH` + `MARGIN` | ❌ | ✅ `MARGIN` | ✅ `MARGIN` |
| Settrade Open API | ✅ `EQUITY` | ✅ `DERIVATIVES` | ❌ | ❌ |
| Liberator | ✅ `CASH` | ❌ | ❌ | ❌ |

#### Gate references (how each family is enforced)

| Family | Broker-level flag | Account-level capability | Enforced at |
|---|---|---|---|
| 1. Normal | `BrokerCapability.EQUITY_TRADE` | `AccountCapability.EQUITY_TRADE` | `pillar3_trade.py:78,81` |
| 2. Future | `BrokerCapability.DERIVATIVES_TRADE` | `AccountCapability.TFEX_TRADE` | `pillar3_trade.py:77–78,81` |
| 3. SBL | `BrokerCapability.SBL_SHORT` | `SBL_BORROW` / `SBL_RETURN` | `pillar4_sbl.py:72,122` |

#### Asset segregation grammar (TFEX vs Equity)

`app/services/validator.py::validate_asset_action` (L173):
- **TFEX symbol** → side ∈ `{LONG, SHORT}`, position ∈ `{OPEN, CLOSE, AUTO}`.
- **Equity symbol** → side ∈ `{BUY, SELL, OPEN_SHORT, COVER, SHORT}`; `LONG` is rejected.

### 2.3 Phase 3 — Trading Strategy (owner-defined)

Owner's definition of Phase 3, cross-checked against live code:

| # | Phase 3 requirement | Code evidence | Status |
|---|---|---|---|
| 1 | **Action Exit** — exit inside a **P&L-sign-based time window**: profitable → Sell/Cover (Equity) or Close (TFEX) in **10:00–10:30**; non-profitable → place in **10:30–12:00** | `app/services/action_exit_service.py:161-174`; `app/services/action_exit_dispatcher.py` | ✅ |
| 2 | **Price Negotiation** — reprice unmatched orders to best **Bid 1 / Offer 1** at **11:00** and **15:30** (price **change** only); SHORT orders obey the **Uptick** rule | `app/services/price_negotiation_service.py:96-109`; `app/core/config.py:88` | ✅ |
| 3 | **Action Entry** — order entry; **manual today** (mobile / web), **automatable later** (flag-gated, no rewrite) | `webhook_signal.py:14-55`; `app/console.py` | ✅ |
| AI | **AI interpreter** — parse the owner's Thai brief into structured orders, feeding Phase 2 | `app/ai/signal_agent.py`, `app/ai/otp_agent.py` → **DeepSeek** | ✅ |

Owner's framing: **all three items are time-based** — the strategy is a set of *scheduled, deterministic* actions. The AI interpreter only **converts free-text intent** into Phase 2 order objects; it does not decide the schedule.

#### 2.3.1 Related Files — Trading Strategy (per broker, mirrors §2.1.1)

| Requirement | Krungsri TradeMan | Settrade Click2Win | Liberator | Settrade Open API |
|---|---|---|---|---|
| Action Exit | `trademan_driver.py` (Sell/Cover/Close) | `click2win_driver.py` (Sell/Close) | ⏳ driver pending | ⏳ REST pending |
| Price Negotiation | `trademan_driver.py:795` `modify_order_price` | `click2win_driver.py` (modify) | ⏳ | ⏳ |
| Action Entry | `webhook_signal.py` → broker driver | same dispatcher | ⏳ | ⏳ |
| AI interpreter | broker-agnostic (`app/ai/*`) | broker-agnostic | broker-agnostic | broker-agnostic |

#### 2.3.2 Cross-Cutting / Shared Strategy Files

| File | Role |
|---|---|
| `app/services/action_exit_service.py` | Builds the time-windowed exit plan from P&L sign (profit vs loss) + jitter |
| `app/services/action_exit_dispatcher.py` | 09:45 pre-flight, then dispatches queued exits inside each window |
| `app/services/price_negotiation_service.py` | Computes the negotiation target price and issues a price **change** |
| `app/mcp/pillars/pillar6_strategy.py` | MCP surface `strategy_action_exit_from_text` (L142) & `strategy_negotiate_unmatched_orders` (L33) |
| `app/ai/signal_agent.py`, `app/ai/otp_agent.py` | DeepSeek-backed AI interpreter (parses trading briefs / OTP SMS) |
| `app/core/config.py` | Negotiation rounds + policy, exit windows, `DEEPSEEK_*` / `GEMINI_API_KEY` |

#### 2.3.3 Relationship Insight — the Time-Window Spine

Phase 3 hangs off a single **daily time spine** owned by the market session:

```
09:45           Action-Exit pre-flight (build plan)
10:00–10:30     Profitable exits  (Sell / Cover / Close)
10:30–12:00     Losing exits      (Sell / Cover / Close)
11:00           Price Negotiation round 1 (Bid 1 / Offer 1)
15:30           Price Negotiation round 2 (Bid 1 / Offer 1)
16:30           EOD order cleanup
```

The AI interpreter runs **before** this spine (turning the owner's brief into orders); the spine then executes deterministically. This is why Phase 3 is *time-based*: once the orders exist (Phase 2), Phase 3 only **decides when** to act.

#### 2.3.4 AI Interpreter — Provider Note (Gemini → DeepSeek)

Phase 3's AI interpreter (Signal + OTP agents) is backed by **DeepSeek** via PydanticAI's OpenAI-compatible provider (`OpenAIProvider` + `OpenAIChatModel`, base URL `https://api.deepseek.com`, model `deepseek-chat`). Config keys: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`. The Gemini path remains available (config `GEMINI_API_KEY`) and is still used by the Vision popup manager, the direct-REST fallback in `app/services/parser.py`, the sub-agents, and the self-annealing engine.

---

## 3. Current Status Audit

| Pillar | Module | Features | Status |
|---|---|---|---|
| 1. Session Sentinel | `pillar1_session.py` | P1.1–P1.4 | 🟢 Done ✅ |
| 2. Account & Portfolio | `pillar2_portfolio.py` | Account switch, Balances, Holdings, Open Orders, Sync | 🟢 Done ✅ |
| 3. Trade Execution | `pillar3_trade.py` | P3.1–P3.6 ✅ · **P3.7–P3.8 ⏳ Pending Market Open** | 🟢/🟡 |
| 4. SBL Intelligence | `pillar4_sbl.py` | P4.1–P4.5 | 🟢 Done ✅ |
| ~~5. Portfolio & Risk~~ | ยุบรวมเข้า Pillar 2 (`pillar2_portfolio.py`) 2026-10-06 | — | 🔁 Merged |
| 6. Tactical Strategy | `pillar6_strategy.py` | P6.1–P6.3 ✅ · **P6.4–P6.5 ⏳ Pending Market Open** | 🟢/🟡 |
| 7. Agentic (DOE/PT-MRO) | `pillar7_agentic.py` | orchestrator, 5 sub-agents, memory, kill-switch | ✅ (not yet in matrix) |
| Self-Annealing | `self_annealing_engine.py` | SA.1–SA.4 + SYS.1 | 🟢 Done ✅ |

**Pending Market Open (not yet verified live):** P3.7 JIT SBL Auto-Borrow, P3.8 SBL Bulk
Return (16:30), P6.4 TradeMan Passive Price Negotiation, P6.5 Action Entry Multi-Window
Dispatcher.

**Deprecated / decoupled:** `DRY_RUN_MODE` (removed), hardcoded market regimes & cron
(decoupled to external layer), blocking human-approval dialogs (→ autonomous + LINE report).

---

## 4. Drift & Contradictions Found (over time)

1. **`directive/phase3_detail.md` is mis-named** — it is now the *Master Directive
   (6-Pillars)*, but still carries the "phase3" name.
2. **Legacy phase file names** remain (`test_phase1_live.py`, `run_phase2_login.py`,
   `test_phase3_*.py`) although the architecture moved to Pillars.
3. **`directive/idea.md` self-marks "historical/archived"** but was never actually archived.
4. **`DailyScenarioTest.md`** says its timetable is "decommissioned" (external orchestration)
   yet remains the active scenario spec.
5. **`automation_roadmap_status_embedded.js` is a stale export** (old title "Semi-Automated
   Trading" vs current "Hybrid High-Frequency Monitor…").
6. **No single phase index** ties Phase 1/2/3 → 6 Pillars → Agentic in one place.
7. **RCA path contradiction** — `broker_pdca_rca.md` + `watch-and-learn/SKILL.md` point to
   `learned_workflows/rca_<broker>.md`, but files actually live in `rca/<broker>/rca_*.md`.
8. **`directive/` (singular) vs `directives/` (plural)** — two different concepts with
   near-identical names.

#### 4.1 Full Conflict Matrix (doc vs latest code)

| Severity | File | What the doc says | Latest reality (code) |
|---|---|---|---|
| 🔴 | `directive/idea.md` | LINE is the OTP relay ("พิมพ์ส่ง OTP กลับมาทาง LINE") | LINE removed from OTP → KDE Connect (auto) + `/console` (manual); `auth.py` keeps `LINE_CHAT` as legacy only |
| 🔴 | `directives/sops/sop_session_security.md` | "Tier 2 (LINE Mobile Fallback)" for OTP | Contradicts `kdeconnect.md` "ตัด LINE ออกจากระบบ OTP" |
| 🔴 | `ManualTest.md` + `MannualTest.md` | OTP via LINE; "Phase 3 Scheduler"; "`DRY_RUN_MODE=true` (default)" | LINE-OTP removed; DRY_RUN removed; scheduler decoupled |
| ✅ FIXED 2026-10-08 | `directive/kdeconnect.md` | ~~§6.2/§7 device id `556f3369…`~~ → แก้เป็น `9507a3fd…` แล้ว (**KDE-RCA-009**) | `9507a3fd…` = Mi 10T (live: paired+reachable; config `KDECONNECT_DEVICE_ID`); `556f3369…` = NUC self-id |
| 🔴 | `directive/idea.md` | DB `tradelab.db`, 4 tables | `investment_homelab.db`, 8 tables (`app/db/models.py`) |
| 🔴 | `directive/idea.md` | Krungsri TradeMan only, old tabs | 4 brokers via `app/brokers/*/plugin.py` |
| 🔴 | `directive/idea.md` | "Phase 1–5" roadmap | Owner-defined Phase 1/2/3 (§2.1–§2.3) |
| 🟡 | `directive/phase3_detail.md` | "ไม่มี Cron ภายใน" | `action_exit_dispatcher.py` hard-codes 09:45 / 11:00 / 15:30; `phase3_scheduler.py` exists |
| 🟡 | `directive/phase3_detail.md` | Pillar 6 = negotiation + EOD only | Owner Phase 3 adds Action Exit (10:00–10:30 / 10:30–12:00) |
| 🟡 | `directive/phase3_detail.md` | negotiation "Change Price **หรือยกเลิกแล้วส่งใหม่**" | Owner: "change price only"; `dispatch_price_modification` |
| 🟡 | `directive/phase3_detail.md` | 6 pillars, no Pillar 7 | Pillar 7 (Agentic) in `pillar7_agentic.py` |
| 🟡 | `automation_roadmap_status.md` | no Agentic row, no DeepSeek, `file://` → `directive/phase3_detail.md` | needs Pillar 7 + DeepSeek; links break if `directive/` moved |
| 🟡 | `DailyScenarioTest.md` | "Phase 3 Scheduler" (L156/L286); decommissioned-but-active | Scheduler decoupled |

**Consistent (no action):** `kdeconnect.md` §1–§5, `root_cause_and_escalation.md` (Invariant 8),
`sop_market_signals`/`order_execution`/`sbl_lifecycle`/`portfolio_risk`, and this `milestone_review.md`.

#### 4.2 Reconciliation Plan (docs-only, ordered)

1. Archive `directive/idea.md` (add ⛔ SUPERSEDED banner / move to `_archive/`).
2. ✅ DONE (2026-10-08) — `kdeconnect.md` device id `556f3369…` → `9507a3fd…` (§6.2/§7) + เพิ่ม source-of-truth comment ชี้ `app/core/config.py KDECONNECT_DEVICE_ID` (**KDE-RCA-009**).
3. Fix `sop_session_security.md` OTP tier (remove LINE; use KDE Connect → `/console` manual entry).
4. Fix `ManualTest.md`/`MannualTest.md` (remove LINE-OTP, `DRY_RUN_MODE=true`, "Phase 3 Scheduler").
5. Add Pillar 7 + DeepSeek to `phase3_detail.md` and `automation_roadmap_status.md`.
6. Resolve "no internal cron" claim in `phase3_detail.md`.
7. RCA path fix (`broker_pdca_rca.md` + `watch-and-learn/SKILL.md` → `rca/<broker>/rca_*.md`).

---

## 5. Proposed Canonical Milestone Model — ⚠️ OPEN DECISION

- **Option A:** Retire Phase 1/2/3 naming; adopt "6 Pillars + Agentic (Pillar 7)".
- **Option B:** Keep Phase 1/2/3 as the spine; map Pillars under them.
- **Option C:** New phasing (owner to describe).

*(Decision pending — see Open Questions.)*

---

## 6. Proposed Restructure Plan (docs-only, no code changes)

**Phase A — Fix RCA path contradictions** (`.agents/rules/broker_pdca_rca.md`,
`.agents/skills/watch-and-learn/SKILL.md` → point to `rca/<broker>/rca_*.md`).

**Phase B — Merge `directive/` → `directives/architecture/`** (move `idea.md`,
`phase3_detail.md`, `kdeconnect.md`; update `file://` links in `automation_roadmap_status.md`,
`DailyScenarioTest.md`, and `idea.md`).

**Phase C — Tidy `docs/`** (move 4 scattered guides → `docs/guides/`).

**Not moved (would require code changes):** `DailyScenarioTest.md`, `dailyorder.md`,
`ManualTest.md` (read from root by `app/api/v1/endpoints/phase3.py`); and the root
HTML/JS viewers.

**Validate:** `grep` for stale links; run `.venv/bin/python -m pytest tests/test_agent_sops.py
tests/test_mcp_and_workflow_engine.py -q`.

---

## 7. Open Questions

1. Canonical milestone model (Option A / B / C)?
2. Should Pillar 7 (Agentic) be added to `automation_roadmap_status.md`?
3. Priority of the 4 "Pending Market Open" items?
4. Properly archive `idea.md` + `DailyScenarioTest.md` as "historical"?
5. Dated vs living filename for this review?

---

## 8. Next Steps

1. Owner answers Open Questions (grill).
2. Lock the restructure scope.
3. Execute in Act mode; report full `Files changed` list.
