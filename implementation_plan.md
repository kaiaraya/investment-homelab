# Implementation Plan — Pillar 2 = Account & Portfolio; Remove Monitor & Alert

> Status: **PLAN — APPROVED** (2026-10-06). Handoff: `docs/handoff/TASK-pillar2-portfolio-refactor.md`.
> User-approved: (1) **DELETE Monitor & Alert entirely**; (2) rename tools → `switch_account` /
> `portfolio_holdings` / `current_open_orders`.
>
> NOTE: The sections below (Pillar-1 acceptance = DONE/PASS, LIB-RCA-007 = IN PROGRESS) are preserved untouched.

## Overview
Restructure the pillar layout so **Pillar 2 = Account & Portfolio** (switch account / read holdings / read open
orders, for Krungsri + Liberator) and **remove the Monitor & Alert feature** (module + 16 MCP tools + monitoring
API + console UI + all dependents). Liberator is single-account (CASH `<liberator-acct>`). Read-only scope: no order
placement / tick-size / price-volume validation logic is changed.

## Types
No new models. Reuse `AccountType.CASH` for Liberator single-account. Liberator open-orders normalized to
`{broker_order_no, symbol, side, volume, matched_volume, balance, price, status, time}`.

## Files
- RENAME `app/mcp/pillars/pillar5_portfolio.py` → `app/mcp/pillars/pillar2_portfolio.py`
- DELETE `app/mcp/pillars/pillar2_monitor_alert.py`
- DELETE `app/api/v1/endpoints/monitoring.py`
- MODIFY `app/schemas/account.py` — `normalize_account_type` LIBERATOR→CASH (+ error-string tool names)
- MODIFY `app/brokers/liberator/plugin.py` — add `get_open_orders()` + `switch_account_type()`
- MODIFY `app/mcp/pillars/__init__.py`, `app/mcp/__init__.py`, `app/mcp/server.py`
- MODIFY `app/mcp/pillars/overview.py`
- MODIFY `app/mcp/pillars/pillar6_strategy.py` — remove `monitor_engine` quote dep
- MODIFY `app/api/v1/endpoints/phase3.py` — remove monitor endpoints; `app/api/v1/api.py` — drop monitoring router
- MODIFY `app/console.py` — remove monitoring UI; `app/main.py` — drop polling/monitor wiring if tied
- MODIFY docs: `automation_roadmap_status.md`, `docs/mcp_6pillars_architecture.md`,
  `docs/MCP_6PILLARS_INTEGRATION_GUIDE.md`, `docs/remote_mcp_setup.md`, `docs/milestone_review.md`
- NEW `tests/test_pillar2_portfolio_liberator.py`, `tests/test_account_capability_liberator.py`
- DELETE `tests/test_monitoring_alert_engine.py`, `tests/test_phase3_alert_center.py`

## Functions
- MODIFY `AccountCapabilityGuardrail.normalize_account_type` (+ error-message tool names)
- NEW `LiberatorBrokerPlugin.get_open_orders()`, `LiberatorBrokerPlugin.switch_account_type()`
- RENAME `portfolio_switch_account`→`switch_account`, `portfolio_get_holdings`→`portfolio_holdings`,
  `portfolio_get_open_orders`→`current_open_orders` (+ LIBERATOR routing)
- KEEP `portfolio_list_accounts`, `portfolio_get_balances`, `portfolio_sync_db`
- REMOVE `portfolio_audit_risk_and_tpsl`, all 16 monitor/alert/watchlist tools, `register_monitor_alert_pillar`

## Classes / Dependencies
MODIFY `LiberatorBrokerPlugin`. No new classes/packages. Remove `monitor_engine` as a dependency of
`pillar6_strategy` and `portfolio`.

## Testing
- NEW: normalize LIBERATOR; `switch_account` CASH-ok/MARGIN-reject; holdings + open_orders (mock LIBERATOR);
  `portfolio_list_accounts`/`portfolio_get_balances` include LIBERATOR.
- REMOVE monitor/alert tests.
- Regression `.venv/bin/python -m pytest tests/ -q`; `python -c "import app.main"`; live headed verification + human confirm.

## Implementation Order (stepwise-gated)
- **Gate A** (additive): A1 `account.py` LIBERATOR→CASH + test → A2 Liberator plugin methods + tests →
  A3 rename module pillar5→pillar2 + imports → A4 rename 3 tools + LIBERATOR routing + tests.
- **Gate B** (destructive): B1 neutralize dependents (pillar6 / portfolio-audit / phase3 / api / console) →
  B2 delete `pillar2_monitor_alert.py` + `monitoring.py` + unregister → B3 remove monitor/alert tests →
  B4 `import app.main` + full pytest green.
- **Gate C**: docs/roadmap (Zero-Contradiction).
- **Gate D**: live headed verification + human confirm.

## Key risk (approved)
"Remove" = **fully DELETE** Monitor & Alert (a working feature). Confirmed by user 2026-10-06.

---

# Implementation Plan — Pillar 1 Acceptance: `start_homelab.sh` Clean End-to-End (Stages 1–4 Green)

> Status: **DONE — PASS** (2026-10-06). `start_homelab.sh` Stages 1–4 all green; artifacts verified.
> New anomaly logged as KDE-RCA-007 (stale MCP process without D-Bus session bus). Handoff: `docs/handoff/TASK-pillar1-acceptance.md`.
>
> NOTE: The plan below this section (LIB-RCA-007 Preflight Broker Session Health) remains a SEPARATE
> IN-PROGRESS task and is preserved untouched.

## Overview
Run `./start_homelab.sh` (→ `scripts/start_homelab.py`) and confirm **all 4 startup stages resolve green** —
KDE bridge online, Krungsri **Zero-OTP** session verified, Liberator **cached** session verified,
FastAPI + `/console` up — as the Pillar-1 (Session Sentinel) acceptance gate. This is a
**verification/operations run**, not a code change: no code is modified unless a stage fails (then we
follow the 4-step self-annealing + per-broker RCA loop per `broker_pdca_rca.md` / `root_cause_and_escalation.md`).

### Current state (verified this session)
| Component | Status |
|---|---|
| KDE bridge (Mi 10T) | ✅ Reachable — Tailscale `100.119.166.62:1716` |
| Krungsri session | ✅ Valid Zero-OTP — `data/session_state.json` (27,879 B / 60 cookies) |
| Liberator session | ✅ Cached JWT valid ~2h (via `session_health.py`) |
| Click2Win | Sandbox, no session (auto web-login, no OTP) |
| FastAPI :8000 | 🔴 DOWN (Stage 4 will start it) |
| Stale MCP server (PID 4056) | ⚠️ needs restart with `DISPLAY=:0` (out of scope — flag only) |

## Types
None (no code changes planned).

## Files
**No planned modifications.** Contingency only (if a stage fails): `scripts/start_homelab.py` (stage logic),
`app/browser/auth_driver.py` / `app/brokers/liberator/driver.py` (selectors/session),
`app/services/kdeconnect_service.py` (bridge). Any such change requires its own handoff task + unit test + RCA entry.

## Functions
No new/modified functions. Exercises existing: `stage1_check_kdeconnect()` (180s poll),
`stage2_verify_krungsri_session()` (Zero-OTP fast-path or headed OTP login),
`stage3_verify_liberator_session()` (cached JWT check, anti-2FA),
`stage4_launch_server_and_console()` (uvicorn + `/console`), `resolve_startup_plan()`.

## Classes / Dependencies
None.

## Pre-requisites (human + environment)
1. **Phone**: awake, KDE Connect app open, Tailscale connected (Stage 1 mandatory gate).
2. **Port 8000 free** (preflight showed DOWN — confirmed).
3. Recommended: run `scripts/preflight_check.py` first (Invariant 7).

## Execution — Stepwise Gated (one step per loop, human-confirm between)
| # | Step | Expected outcome | Verify (evidence) |
|---|------|------------------|-------------------|
| 1 | Pre-flight `python scripts/preflight_check.py` | KDE reachable + Krungsri session present + Liberator active + no orphan Chrome | preflight output (read-only) |
| 2 | Run `./start_homelab.sh` (headed, `DISPLAY=:0`), tee to `/tmp/start_homelab_run.log` | Stages 1→4 proceed | log |
| 3 | Observe **Stage 1** | `🎉 Xiaomi Mi 10T CONNECTED SUCCESSFULLY` + ping | log + phone vibrates (human) |
| 4 | Observe **Stage 2** | `✅ Krungsri TradeMan Active Session Verified! (Zero-OTP Pass <2s)` — **no OTP** | log |
| 5 | Observe **Stage 3** | `✅ Liberator WebTrade Active Session Verified! (Zero-OTP Pass <2s)` | log |
| 6 | Observe **Stage 4** | `🟢 ALL SYSTEMS GO!` + uvicorn on :8000 + `/console` opened | log + browser (human) |
| 7 | Verify artifacts | `curl -s http://localhost:8000/health` → 200; `session_get_health` reports Krungsri + Liberator authenticated + KDE reachable | curl / MCP output |
| 8 | REFLECT | all green → **Pillar-1 PASS**; any fail → self-anneal + RCA + escalate after ~3 attempts | log / RCA file |

## Testing
- Pre-flight: `python scripts/preflight_check.py`.
- Post-run: `curl -s http://localhost:8000/health` + `session_get_health`.
- No pytest for a clean run (no code changed). If code changes on failure: targeted broker tests + `.venv/bin/python -m pytest tests/ -q`.

## Next pillar (after acceptance)
> ⚠️ **SUPERSEDED (2026-10-06)** — Pillar 2 (Monitor & Alert) ถูก **ลบทั้งระบบแล้ว**
> (`monitor_register_position` / `monitor_get_realtime_quote` / `monitor_add_*` / `alert_add_rule`
> ไม่มีอยู่ในโค้ดแล้ว — ไฟล์ `app/mcp/pillars/pillar2_monitor_alert.py`, `app/mcp/pillars/monitoring.py`,
> `app/services/alert_center_service.py` ถูกลบ) ตาม `docs/handoff/TASK-pillar2-portfolio-refactor.md`.
> Pillar 2 ปัจจุบัน = **Account & Portfolio** — **ห้ามใช้รายการด้านล่างนี้เป็นแผนงานอีก**

Pillar 1 done → ~~next is **Pillar 2 (Monitor & Alert)** live verification~~ (removed),
ที่เหลือคือ **4 "Pending Market Open"** items
(`P3.7`/`P3.8` SBL auto-borrow/return, `P6.4` passive negotiation, `P6.5` action-entry dispatcher)
which require live market hours. Decided after acceptance.

## Implementation Order
1. Pre-flight → 2. run `start_homelab.sh` → 3. observe Stages 1–4 → 4. verify `/health` + `session_get_health`
→ 5. REFLECT (PASS record / FAIL self-anneal) → 6. plan next pillar.

---


# Implementation Plan — Preflight Broker Session Health (LIB-RCA-007)

> Status: **IN PROGRESS** — Gate 1 (shared helper + driver delegation); plan approved, executing stepwise.

## Overview
Fix the `scripts/preflight_check.py` false-positive that reports "✅ session exists" for broker
sessions from `os.path.exists()` alone, contradicting each broker's real validity check (LIB-RCA-007).
Split the single lumped "Broker Sessions" step into **three independent per-broker steps** (Broker
Knowledge Isolation), and make Liberator reuse the same JWT-expiry check as its driver (single source
of truth).

- **Krungsri** (live, `data/session_state.json`) — own step; file presence + size + age (Stage-2 hard gate unchanged).
- **Click2Win** (simulation, `data/click2win_session.json`) — own step; report file presence + age + cookie count only, **no false "✅ active"** (sandbox, no JWT, auto web-login fallback).
- **Liberator** (live, `data/liberator_session.json`) — own step; real JWT `exp` via shared helper → 3-state report (✅ Active / ⚠️ EXPIRED / ℹ️ No session).

## Types
No new Pydantic models. Two plain `dict[str, Any]` status shapes (documented for tests):
- `session_health()` → `{"exists": bool, "exp": int|None, "expired": bool, "remaining_seconds": int|None}`
- `click2win_session_status()` → `{"exists": bool, "age_seconds": float|None, "cookie_count": int}`

## Files
- **NEW** `app/brokers/liberator/session_health.py` — pure (stdlib only), browser-free JWT session health.
- **MODIFY** `app/brokers/liberator/driver.py` — delegate the two private helpers to the new module.
- **MODIFY** `scripts/preflight_check.py` — add `sys.path` guard + `app` imports; split broker step into 3 per-broker steps; renumber Market→6, Hygiene→7; honest 3-state reports.
- **NEW** `tests/test_preflight_check.py` — unit tests for the helper + preflight status/render.
- **MODIFY** `rca/liberator/rca_liberator.md` — mark LIB-RCA-007 🟢 RESOLVED (final gate).

## Functions
- **NEW** `read_session_token_expiry(session_path: str) -> Optional[int]` (`session_health.py`) — decode `api-token`/`ws-token` JWT `exp`; fallback to any cookie `expires>0`; `None` if undeterminable.
- **NEW** `session_expired(session_path: str, safety_margin_seconds: int = 60) -> bool` — `True` if `exp <= now + margin`; `False` if undeterminable (preserves LIB-RCA-006 online-DOM path).
- **NEW** `session_health(session_path: str, safety_margin_seconds: int = 60) -> Dict[str, Any]`.
- **MODIFY** `LiberatorDriver._session_token_expiry()` → `return read_session_token_expiry(self.session_path)`.
- **MODIFY** `LiberatorDriver._saved_session_expired()` → `return session_expired(self.session_path, safety_margin_seconds)`.
- **NEW** `scripts/preflight_check.py::_path(key, default)` — resolve broker paths from `settings` with hardcoded fallback.
- **NEW** `liberator_session_status(path)` / `click2win_session_status(path)` — pure, testable status dicts.
- **SPLIT** `check_broker_sessions()` → `check_krungsri_session()`, `check_click2win_session()`, `check_liberator_session()`; each prints its own numbered banner; `main()` calls all three.

## Classes
None.

## Dependencies
None added (stdlib + existing `app.core.config`, `app.brokers.liberator.session_health`).

## Testing
- `.venv/bin/python -m pytest tests/test_liberator_session.py tests/test_preflight_check.py -q` (new + regression).
- New tests: JWT decode (valid / cookie-fallback / missing / corrupt), `session_expired` (past / margin / future / None), `session_health` 3 states, `click2win_session_status` (no file / with file), and capsys render of `check_liberator_session()` for EXPIRED vs ACTIVE vs No-session.
- Full suite: `.venv/bin/python -m pytest tests/ -q` (regression).
- Live: `python scripts/preflight_check.py` (read-only; no `--clean` needed).

## Implementation Order (stepwise-gated — user confirms each gate)
1. **Gate 1** — add `session_health.py` + driver delegation; run `pytest tests/test_liberator_session.py -q` (still green). ✅ DONE (see Live Verification Evidence).
2. **Gate 2** — preflight: `sys.path` guard, `_path()`, status helpers, split into 3 broker steps, renumber.
3. **Gate 3** — write `tests/test_preflight_check.py`; run new tests + full suite.
4. **Gate 4** — live run: confirm Liberator shows ✅ Active (fresh session written 2026-10-05) and Click2Win shows its own 🎮 simulation step; then point Liberator at `data/liberator_session.stale.bak.json` to demonstrate the ⚠️ EXPIRED branch.
5. **Gate 5** — docs: mark LIB-RCA-007 🟢 RESOLVED in `rca/liberator/rca_liberator.md`; update `implementation_plan.md` Open Question 7.

---

# Archived — Implementation Plan — Mobile-Offline Degrade-and-Continue + Liberator Headed Verification

> Status: **COMPLETE (2026-10-05)** — code + tests green; Liberator WebTrade headed login verified PASS (4 human-confirmed gates, live).

## Goal
1. Wire `scripts/start_homelab.py` `main()` to **degrade-and-continue** (skip BOTH broker logins) when the
   KDE-Connect mobile OTP bridge is OFFLINE, instead of hard-aborting with `sys.exit(1)`.
2. Verify the **Liberator WebTrade headed login** step-by-step (4 gates, human-confirmed).

## Root Cause / Rationale (Invariant 7.3)
KDE Connect is the ONLY channel the system uses to read the 2FA SMS OTP for BOTH Krungsri and Liberator.
If the bridge is down, a fresh broker login is impossible — so aborting the whole startup is worse than
coming up degraded: the operator loses the Cockpit and the ability to remediate. The fix distinguishes an
*intentional* `--skip-*` (optimistic, not degraded) from a *bridge-offline* skip (a real failure → DEGRADED).

## Design — single decision point
`resolve_startup_plan(kde_ok, skip_login, skip_liberator) -> dict[str, bool]` (module level, `start_homelab.py`):

| kde_ok | skip_login | skip_liberator | kde_ready | run_krungsri | run_liberator | degrade_krungsri | degrade_liberator |
| :--: | :--: | :--: | :--: | :--: | :--: | :--: | :--: |
| False | – | – | False | False | False | True | True |
| True | False | False | True | True | True | False | False |
| True | True | True | True | False | False | False | False |
| None | True | False | True | False | True | False | False |
| True | True | False | True | False | True | False | False |

- Stage 2 keeps its `sys.exit(1)` **ONLY** for the "bridge UP but Krungsri login failed" case; the
  mobile-offline path never reaches it (`run_krungsri=False`).
- Liberator startup stays **cached-session-check only** (anti-2FA); the headed login is a separate
  verification harness, not a startup step.

## Files
- `scripts/start_homelab.py` — new `resolve_startup_plan()`; `main()` Stages 1–3 rewired; docstring note.
- `start_homelab.sh` — L8/L15 comments: offline → degrade + skip broker logins.
- `tests/test_start_homelab_resolve_plan.py` — **new** decision-table tests (6 cases).

## Testing
- `.venv/bin/python -m py_compile scripts/start_homelab.py`
- `.venv/bin/python -m pytest tests/test_start_homelab_resolve_plan.py tests/test_start_homelab_transport.py tests/test_start_homelab_stages.py -q`
  → **15 passed** (6 new + 6 transport + 3 stages).

## Verification (Step 6 — DONE 2026-10-05)
- **Staleness proven live:** headed Chrome loaded saved cookies → GET protected `/Portfolio` →
  bounced to `/login` (`step_a_redirected_to_login=true`), matching the expired (~30 h) saved JWT.
- Vehicle: ephemeral checkpoint-gated harness `/tmp/liberator_stepwise_login.py` (creds in-process only,
  never printed; stop-and-confirm after every gate) — visible Chrome on `DISPLAY=:0`, KDE OTP auto-capture.
- **All gates PASSED.** Full evidence table: *Live Verification Evidence — Liberator Headed Login* (below).

## Open Questions
- `liberator_driver.login()` hardcoded fallback creds (L205–206) — out of scope, flagged only.

---

# Archived — Implementation Plan — 4-Stage Approval-Gated Startup Hardening (`start_homelab.py`)

> Status: **IMPLEMENTED** (Stages 2–5). Stage 0 deferred (see Open Questions).

## Overview
Normalize `scripts/start_homelab.py` (invoked by `./start_homelab.sh`) into a clean **4-stage,
approval-gated** readiness sequence, and reconcile every stale "3-stage" label across code, shell,
runbook, and app comments. Stage 1 (KDE Connect mandatory OTP-readiness gate + LINE troubleshooting +
dual-transport probe) was completed and verified earlier and is **not** re-touched here; the
completed MacroDroid removal is also **not** re-touched.

Final stage map:
1. **Stage 1** — KDE Connect Hardware Bridge Probe (mandatory SMS-OTP gate; LINE escalation on DOWN).
2. **Stage 2** — Krungsri TradeMan Session Gate (hard gate; **NEW** LINE escalation on login failure).
3. **Stage 3** — Liberator WebTrade Session Gate (renamed from Stage 2B; de-nested; optional).
4. **Stage 4** — Launch FastAPI Gateway & /console Cockpit (renamed from Stage 3).

## Types
None. `STARTUP_STATUS` keys (`kde`/`krungsri`/`liberator`) unchanged.

## Files
- `scripts/start_homelab.py` — escalation helper, 3 failure-path calls, renames, de-nest, label fixes, docstring.
- `tests/test_start_homelab_stages.py` — **new** regression tests (names + escalation).
- `start_homelab.sh` — 3-stage → 4-stage banner/comments.
- `app/main.py` — `/console` launch comment (~L77).
- `learned_workflows/krungsri/krungsri_market_open_operational_runbook.md` — L89 `3-stage` → `4-stage`.

## Functions
- **NEW `push_krungsri_login_alert(phase: str, detail: str) -> None`** (module level, above Stage 2):
  escalates Krungsri login failure to LINE via `line_service.send_system_notification(..., severity="CRITICAL")`,
  wrapped in try/except (never raises). Module-level for direct unit-testing (Invariant 6).
- **MODIFIED `stage2_verify_krungsri_session`**: calls `await push_krungsri_login_alert(...)` on 3 failure
  paths — missing credentials, `login_res.success == False`, and `except Exception`.
- **RENAMED `stage2b_verify_liberator_session` → `stage3_verify_liberator_session`**: banner `[STAGE 2B/4]` → `[STAGE 3/4]`.
- **RENAMED `stage3_launch_server_and_console` → `stage4_launch_server_and_console`**: banner `[STAGE 3/3]` → `[STAGE 4/4]`.
- **MODIFIED `main()`**: de-nested Liberator out of `if not args.skip_login:` into its own Stage 3;
  renumbered step comments. `--skip-login` now skips **only** Krungsri; `--skip-liberator` governs Liberator.
- **MODIFIED `stage1_check_kdeconnect` banner**: `[STAGE 1/3]` → `[STAGE 1/4]`.

## Classes / Dependencies
None.

## Testing
- `tests/test_start_homelab_stages.py`: (1) new names exist, (2) old names removed, (3) escalation helper
  dispatches LINE with `severity="CRITICAL"` and never raises on transport failure.
- `.venv/bin/python -m py_compile scripts/start_homelab.py`
- `.venv/bin/python -m pytest tests/test_start_homelab_transport.py tests/test_start_homelab_stages.py -q`
- Stale-token grep: `stage2b_verify_liberator_session`, `stage3_launch_server_and_console`, `STAGE 2B`,
  `STAGE 1/3`, `STAGE 2/3`, `STAGE 3/3`, `3-stage`/`3-Stage`.

## Implementation Order
1 Stage 2 escalation → 2 Stage 3 rename → 3 de-nest → 4 Stage 4 rename → 5 label normalization →
6 tests → 7 docs (shell/app/runbook) → 8 validate.

## Open Questions (recorded, not acted on)
1. **Stage 0 `--simulate-kde-down` — DEFERRED** (user decision). `--skip-kde` remains the offline/CI escape
   hatch; the real physical test already proved the DOWN→LINE path.
2. `app/console.py` readiness subtitle still shows only the Tailscale IP (cosmetic UI, separate scope).
3. `docs/MCP_6PILLARS_INTEGRATION_GUIDE.md` lists stale home Wi-Fi IP `192.168.1.187` (live lease `.54`);
   harmless — no hardcoded LAN IP in code.
4. `STARTUP_STATUS["kde"]` is never set `False` by Stage 1 (Stage 1 hard-exits instead) — pre-existing,
   out of scope.

---

## Live Verification Evidence (2026-10-05) — headed / real-interaction

Per `.agents/skills/stepwise-approval/SKILL.md` §5, hardware/browser steps count as "verified" only
with a real observable result **plus** human confirmation. Captured this session:

| Step | Test performed | Evidence captured | Human confirm |
| :-- | :-- | :-- | :--: |
| Out-of-band alert | `line_service.send_system_notification(...)` | `POST https://api.line.me/v2/bot/message/broadcast "HTTP/1.1 200 OK"` (+ a setup-instruction push) | ✅ user saw the LINE message |
| Stage 1 (KDE bridge) | `kdeconnect-cli -d 9507a3fd… --ping-msg "…"` | `isReachable: false → true`; `statusIconName=smartphoneconnected`; `ping_rc=0` | ✅ user saw the ping |
| Stage 2 (Krungsri login) | `stage2_verify_krungsri_session(force_fresh=False)` — **headed** on `DISPLAY=:0` | `Ref: GMCY` → KDE auto-captured `598255` → `#dropDownAccountPort` visible → final URL `https://trademan.in.th/Portfolio`; `STAGE2_RESULT=True elapsed=30.4s`; `data/session_state.json` = 27,882 B (60 cookies / 3 origins) | ✅ user saw Chrome login → Portfolio |

Pre-flight (`scripts/preflight_check.py`) at test time: FastAPI :8000 **DOWN**; KDE bridge socket
connected on Tailscale `100.119.166.62:1716`; **no** saved Krungsri session (→ fresh headed login);
Liberator session present; Monday live hours; no orphan Chrome processes.

## Open Questions (cont.)
5. **`playwright-homelab` MCP server has no `DISPLAY`** → every headed MCP browser tool (`browser_open`,
   `browser_screenshot`, `trademan_check_session`) fails with *"Missing X server or $DISPLAY"*, while
   direct driver calls succeed because `start_homelab.py` sets `DISPLAY=:0` itself. Fix (out of scope):
   export `DISPLAY=:0` in the MCP server launch env, then restart it. Logged as `PWENV-RCA-001` in
   `rca/shared/rca_playwright_headed_env.md`.
6. **Duplicate "NUC-Intel / Nuc-Intel" shown on the phone** — cosmetic only; `kdeconnectd` + GSConnect
   both announce the NUC. No functional impact (unpaired ghost `92bf…` is excluded by `-a` and by the
   code blacklist). Logged as `KDE-RCA-004` in `rca/shared/rca_kdeconnect_bridge.md`.

---

## Live Verification Evidence (2026-10-05) — Liberator WebTrade Headed Login (stepwise)

Vehicle: ephemeral checkpoint-gated harness `/tmp/liberator_stepwise_login.py` (creds in-process only,
never printed; stop-and-confirm after every gate). Headed Chrome on `DISPLAY=:0`; screenshots in `data/screenshots/`.

| Gate | Test performed | Evidence captured | Human confirm |
| :-- | :-- | :-- | :--: |
| 0 — Bridge | `kdeconnect-cli -d 9507a3fd… --ping-msg "Investment Homelab Bridge Active"` | `ping_rc=0`; TCP `:1716` ESTAB; D-Bus `statusIconName=smartphoneconnected` | ✅ ping seen on Mi 10T |
| 1 — Staleness / login | headed load saved cookies → GET protected `/Portfolio` | landed `https://webtrade.liberator.co.th/login` (`redirected_to_login=true`); `liberator_stepA_stale_probe.png` | ✅ saw login page (not dashboard) |
| 2 — Credentials → 2FA | auto-fill `.env` creds → submit | URL `.../otp?telNo=061XXX6363`, Ref `JOXV`; `liberator_gate3_2fa_prompt.png`; KDE probe `MASKED=84****` | ✅ saw "Confirm OTP" page |
| 3 — OTP auto-submit | KDE auto-capture (ref `JOXV`) → fill → submit | `KDE captured OTP 84****`; post-OTP URL `.../Market` (dashboard); `liberator_gate4_after_otp.png` | ✅ saw logged-in dashboard |
| 4 — Portfolio + persist | GET `/Portfolio` → `save_session_state()` | final URL `.../Portfolio`; `liberator_gate5_portfolio.png`; fresh `data/liberator_session.json` | ✅ saw Portfolio holdings |

**Post-run validation of the NEW session (`LIB-RCA-006` guard, real driver code path):**
`saved_expired = False`; `token_exp = 1791288007` (~24 h → ≈2026-10-06T12:01Z UTC); file `ts 2026-10-05T12:01:28Z`;
11 cookies. Stale file preserved non-destructively (Invariant 8) → `data/liberator_session.stale.bak.json`
(11 cookies, `ts 2026-10-03T06:12:42Z`).

Portfolio rendered post-login: BCH 4,000 · BCP 900 · IVL 700 · JAS 50,000 · RCL 400 · THAI 2,000;
account `<liberator-acct>`; `Credit Limit 500,000.00` · `Line Available 96,291.18` · `Cash Balance 115,276.53`.

## Open Questions (cont. 2)
7. `LIB-RCA-007` still OPEN (out of scope): `scripts/preflight_check.py` L120-122 reports
   `✅ Saved session exists` from `os.path.exists()` only — it does **not** reuse
   `liberator_driver.saved_session_expired()`, so it can contradict the driver (which correctly said
   EXPIRED this run). Same pattern in the Click2Win branch (L113-115).
8. `liberator_driver.login()` hardcoded fallback creds (L205–206: `"<redacted>"` / `"<redacted>"`) —
   security smell, out of scope; the live run used `.env` creds (`LIBERATOR_USERNAME` / `LIBERATOR_PASSWORD`).
   **RESOLVED 2026-10-11** (git init secret scan): fallbacks removed; `login()` now fails closed with
   `error_code="MISSING_CREDENTIALS"` before the OTP gate when `.env` creds are empty.
