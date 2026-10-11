# Liberator WebTrade — Login Loop-Engineering Checklist

- **Generated At**: 2026-10-06
- **Platform**: Liberator Securities WebTrade (`https://webtrade.liberator.co.th`) — KDE Connect OTP interception
- **Source of truth**: `app/brokers/liberator/driver.py` → `LiberatorDriver.login()` (+ `verify_saved_session`, `save_session_state`)
- **Protocol**: Loop Engineering (`/.agents/rules/loop_engineering.md`) — DECOMPOSE → EXECUTE → VERIFY → REFLECT → REPEAT
- **Related**: `app/brokers/liberator/session_health.py`, `learned_workflows/liberator/liberator_portfolio.md`, `rca/liberator/rca_liberator.md`
- **Daily entrypoint (2026-10-08)**: `scripts/daily_readiness.py` — headed auto re-login for Liberator (gated by KDE Connect `is_device_reachable()`; see `.agents/skills/daily-readiness/SKILL.md`). NOTE: differs from `scripts/start_homelab.py` Stage 3 which deliberately does no headed login.

> **Rule**: Execute **one gate per loop**. Do NOT run the whole `login()` as a single batch.
> Hardware / OTP gates are only "verified" with **human confirm** on the phone (`stepwise-approval` §5), not merely a passed assertion (Anti-Mock Guardrail).

## Loop Reminder

```
DECOMPOSE → EXECUTE (1 gate) → VERIFY (evidence) → REFLECT (on FAIL) → REPEAT (next gate)
```

## Atomic Gates (decomposed from `login()`)

| # | Atomic Step (selector) | Expected Outcome | Verify (evidence / human) | Status |
| :--- | :--- | :--- | :--- | :--- |
| 0 | Reuse — `verify_saved_session()` (JWT `exp` via `session_health`) | valid JWT → skip login | `saved_expired=False`, `remaining > 0` | ⬜ |
| 1 | Fresh login — `launch_browser(resume_state=False)` + `goto(login_url)` | login page loaded | URL = `.../login` | ⬜ |
| 2 | `TYPE` username — `input[placeholder*='Username']` (fallbacks: `Email`, `input[type='text']`, `#username`) | username entered | field visible + filled | ⬜ |
| 3 | `TYPE` password — `input[placeholder*='Password']`, `input[type='password']`, `#password` | password entered | field filled (mask password) | ⬜ |
| 4 | `CLICK` submit — `button:has-text('ยืนยัน')` (fallbacks: `button[type='submit']`, `เข้าสู่ระบบ`, `Login`) | form advances to OTP / dashboard | URL changes | ⬜ |
| 5 | Detect OTP — `input[placeholder*='OTP' i]` / `input[inputmode='numeric']` + ref regex `\(ref\.\s*code:\s*([A-Za-z0-9]+)\)` | OTP page rendered + **Ref code** scraped | ref code string + screenshot | ⬜ |
| 6 | Poll OTP (KDE Connect, loop ≤180s) | OTP captured from phone notification / manual entry | KDE ping; **human confirms SMS received** | ⬜ |
| 7 | Submit OTP — fill `otp_input` + click `button:has-text('ยืนยัน')` (4s safety hold) | OTP accepted | URL leaves OTP page | ⬜ |
| 8 | Verify dashboard + persist — URL contains `webtrade.liberator.co.th` and NOT `login`/`otp` → `save_session_state()` | portfolio rendered; session file written | final URL + file timestamp / cookie count | ⬜ |

### Notes / Edge Cases
- **OTP source priority**: (1) KDE Connect notification matched to expected Ref, (2) manual OTP typed into the on-screen field (detected via `input_value()` ≥ 6 digits).
- **Safety hold**: 4s pause after capture before clicking Confirm (`await asyncio.sleep(4.0)`) — the OTP is highlighted on the live Chrome window for the operator.
- **Session persistence**: `save_session_state()` → `data/liberator_session.json` (see `session_path`); do not purge on transient errors.
- Ref-code extraction uses regex `\(ref\.\s*code:\s*([A-Za-z0-9]+)\)` — if the OTP SMS format changes, this gate is the first to break.

## REFLECT (on any FAIL)

1. **4-tier self-annealing** (`root_cause_and_escalation.md` Invariant 3): dismiss obstructive popups → try fallback selectors → wait 1–2s for re-render → escalate.
2. **Log RCA** into `rca/liberator/rca_liberator.md` in PDCA format (Incident ID, Symptom, RCA, Edge Cases, Proven Solution).
3. **Reconcile** any changed selector/step order into `learned_workflows/liberator/liberator_portfolio.md` immediately (Zero-Contradiction §3).
4. If unresolved after ~3 attempts → **escalate** via KDE Connect (`🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: ...`).

## Cross-references
- `.agents/rules/loop_engineering.md` — canonical loop + decomposition rules
- `.agents/rules/broker_pdca_rca.md` — PDCA logging + Zero-Contradiction
- `.agents/rules/root_cause_and_escalation.md` — 4-tier self-annealing + KDE escalation
- `.agents/skills/stepwise-approval/SKILL.md` — human-confirm verification for hardware/OTP gates
