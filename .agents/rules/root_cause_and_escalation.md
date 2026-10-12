# Rule: Root Cause First, Anti-Mock & Escalation (core)

Full version (Invariants 1–9 with history): `docs/agent/full/root_cause_and_escalation_full.md`.

1. **Anti-Mock** — never return mock accounts, fabricated balances, dummy order ids, or empty arrays as valid data when a step fails. Report honestly or return maintenance status.
2. **3-point RCA before patching** — session/context collision or expired cookies · live DOM (headed browser / Playwright console, don't guess selectors) · data schema/column order (Equity vs TFEX).
3. **Self-annealing before escalation** — dismiss popups → fallback selectors → wait 1–2 s for re-render → escalate with anomaly snapshot.
4. **HITL escalation** on critical failure (account switch, order, SBL, persistent scrape anomaly): notify Admin (`🚨 มาดูที่จอหน่อย มีปัญหาให้ช่วย: [สาเหตุ]`). Never loop forever, fail silently, or guess.
5. **Degraded MCP/API state** → `status: "UNDER_MAINTENANCE"`, `success: false`; never let a remote agent act on unverified data.
6. **Type-safety** — Pydantic + explicit Enums (`MCPToolStatus`) for MCP I/O; every fix covered by tests.
7. **Preflight** — check dependencies (`scripts/preflight_check.py`) before tests/automation; background jobs must never trigger full login / SMS OTP (use cached data).
8. **Phone bridge** — readiness only via real-time D-Bus `isReachable` (+ TCP 1716), never `iconName`/`statusIconName`/cached `kdeconnect-cli -l`. Never delete `session_state.json` on transient errors.
9. **Never fire SMS OTP unless the relay gate is live** (`otp_relay_readiness.check().ready`; LINE is primary, KDE Connect dormant) → otherwise abort with `BRIDGE_DOWN`.
