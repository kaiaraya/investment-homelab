# Krungsri TradeMan — Login Loop-Engineering Checklist

- **Generated At**: 2026-10-06
- **Platform**: Krungsri TradeMan (login → SSO `https://trademan.in.th`)
- **Source of truth**: `app/browser/auth_driver.py` → `KrungsriAuthDriver.login()` (+ `_detect_otp_prompt`, `_wait_for_otp_multi_channel`, `_click_otp_submit`, `_verify_post_login`)
- **Protocol**: Loop Engineering (`/.agents/rules/loop_engineering.md`) — DECOMPOSE → EXECUTE → VERIFY → REFLECT → REPEAT
- **Related**: `learned_workflows/krungsri/trademan_session_reconnect.md`, `rca/krungsri/rca_krungsri_trademan.md`
- **Daily entrypoint (2026-10-08)**: `scripts/daily_readiness.py` — เตรียมพร้อมรายวัน + auto re-login (gated by KDE Connect `is_device_reachable()`; see `.agents/skills/daily-readiness/SKILL.md`)

> **Rule**: Execute **one gate per loop**. Do NOT run the whole `login()` as a single batch.
> Hardware / OTP gates are only "verified" with **human confirm** on the phone (`stepwise-approval` §5), not merely a passed assertion (Anti-Mock Guardrail).

## Loop Reminder

```
DECOMPOSE → EXECUTE (1 gate) → VERIFY (evidence) → REFLECT (on FAIL) → REPEAT (next gate)
```

## Atomic Gates (decomposed from `login()`)

| # | Atomic Step (selector) | Expected Outcome | Verify (evidence / human) | Status |
| :--- | :--- | :--- | :--- | :--- |
| 0 | Reuse — `validate_preflight_session()` / `verify_saved_session()` | `#dropDownAccountPort` visible on `trademan.in.th`, no re-login needed | no OTP sent; returns `resumed=True` | ⬜ |
| 1 | `NAVIGATE` → `settings.KRUNGSRI_LOGIN_URL` | login form rendered | page URL = login page + screenshot | ⬜ |
| 2 | `TYPE` `#login_username` + `#login_password` | both fields populated | assert field values (mask password in log) | ⬜ |
| 3 | `CLICK` `#login` | form submits, page advances | URL changes / no alert dialog | ⬜ |
| 4 | Check alert dialog (`_handle_dialog`) | no "invalid password" alert | dialog handled; if alert → REFLECT (credentials) | ⬜ |
| 5 | Detect OTP (`_detect_otp_prompt`) | OTP input visible + **Ref code** scraped | ref code string logged + screenshot | ⬜ |
| 6 | Wait OTP (`_wait_for_otp_multi_channel`, `OTP_TIMEOUT_SECONDS`=180s) | OTP captured (KDE Connect / manual / EventBus) | KDE ping sent; **human confirms SMS received** | ⬜ |
| 7 | Fill OTP + submit (`_click_otp_submit`) | OTP accepted, page advances | URL leaves OTP page | ⬜ |
| 8 | Verify SSO → TradeMan (`_verify_post_login`) | lands `trademan.in.th`, `#dropDownAccountPort` visible | final URL + **human confirm** | ⬜ |
| 9 | Persist cookies (`context.storage_state`) | `data/session_state.json` written | file exists + size / cookie count | ⬜ |

### Notes / Edge Cases
- **Cooldown guard**: a duplicate `login()` within 60s while `status ∈ {NAVIGATING, AWAITING_OTP}` is skipped (prevents SMS OTP spam).
- **`force_fresh=True`** purges `session_state.json` + clears cookies before Gate 1 — only use intentionally.
- **Zero-OTP integrity**: never delete `session_state.json` on a transient DOM exception/timeout (Invariant 8) — preserve the OTP pass.
- OTP timeout is `settings.OTP_TIMEOUT_SECONDS` (default 180s); on timeout a diagnostic snapshot is captured (`otp_timeout`).
- **SMS arrival-time capture (`KDE-RCA-005`, 2026-10-06)**: Gate 6 calls
  `poll_active_notifications(expected_ref=self.current_ref, since_ms=int(wait_start_time.timestamp()*1000))`.
  The journal scan is anchored to the moment the OTP was requested, and a **definitive Ref-Code match always
  bypasses the age guard** (GSConnect stores the *phone's* SMS creation time, not the arrival time).
  The generic age guard is `settings.OTP_STALENESS_GRACE_SECONDS` (default 600s).
- **Do NOT widen `OTP_TIMEOUT_SECONDS` to fix a late SMS.** The SMS itself expires in ~5 min while an
  Android-Doze / link-flap relay can take ~7m39s → the OTP is dead before it arrives. Fix **relay latency**
  (Active Pull / Doze whitelist), not the window.
- **Dual-link reachability (U4)**: `is_device_reachable()` is True when **either** daemon confirms a live link —
  `kdeconnectd` (`isReachable`) **or** GSConnect (`org.gnome.Shell.Extensions.GSConnect.Device.Connected`).
  GSConnect exposes **no** notifications interface, so OTP payloads are read from the **user journal + GSConnect
  cache**, never from GSConnect D-Bus.
- **Evidence gate**: re-verify with `scripts/replay_kde_rca005.py` (real-data replay, read-only — no login/OTP/order)
  before declaring an OTP-bridge fix complete (Anti-Mock Guardrail).
- **Live-confirmed (2026-10-06 16:58)**: a real `login --force-fresh` captured a **fresh** SMS OTP
  (`Ref ZHXZ` / `682729`) via KDE Connect in **~3s**, landed `trademan.in.th/Portfolio` with
  `#dropDownAccountPort` visible, and wrote `data/session_state.json` (60 cookies). Gate 6 verified **LIVE**.

## REFLECT (on any FAIL)

1. **4-tier self-annealing** (`root_cause_and_escalation.md` Invariant 3): dismiss obstructive popups → try fallback selectors → wait 1–2s for re-render → escalate.
2. **Log RCA** into `rca/krungsri/rca_krungsri_trademan.md` in PDCA format (Incident ID, Symptom, RCA, Edge Cases, Proven Solution).
3. **Reconcile** any changed selector/step order into `learned_workflows/krungsri/trademan_session_reconnect.md` immediately (Zero-Contradiction §3).
4. If unresolved after ~3 attempts → **escalate** via KDE Connect (`🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: ...`).

## Cross-references
- `.agents/rules/loop_engineering.md` — canonical loop + decomposition rules
- `.agents/rules/broker_pdca_rca.md` — PDCA logging + Zero-Contradiction
- `.agents/rules/root_cause_and_escalation.md` — 4-tier self-annealing + KDE escalation
- `.agents/skills/stepwise-approval/SKILL.md` — human-confirm verification for hardware/OTP gates
