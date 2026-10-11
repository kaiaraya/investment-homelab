# TASK-pillar1-acceptance: Pillar-1 Acceptance — `start_homelab.sh` Clean End-to-End (Stages 1–4 Green)

- Created: 2026-10-06 by Antigravity
- Broker: N/A (cross-broker startup orchestrator: Krungsri + Liberator + Click2Win + KDE bridge)
- Status: DONE

## Context (Antigravity เขียน)
Pillar-1 (Session Sentinel) acceptance gate: run `./start_homelab.sh` and confirm all 4 startup stages
resolve green. This is a **verification / operations run** (no planned code change). Related evidence chain:
KDE-RCA-005 (dual-link OTP) LIVE-CONFIRMED, KSS-RCA-010 (Krungsri Zero-OTP) Live S2 PASS. A NEW anomaly was
discovered during verification → logged as **KDE-RCA-007** (stale MCP process without a D-Bus session bus).

## Scope — ไฟล์ที่อนุญาตให้แก้
- (none planned) Contingency only if a stage failed: `scripts/start_homelab.py`,
  `app/services/kdeconnect_service.py`, `app/browser/auth_driver.py`,
  `app/brokers/liberator/driver.py`.

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 1 | Pre-flight `scripts/preflight_check.py` | KDE reachable + Krungsri session present + Liberator JWT active + no orphan Chrome | 7-step preflight output | ✅ |
| 2 | Run `./start_homelab.sh` (headed, `DISPLAY=:0`), tee to `/tmp/start_homelab_run.log` | Stages 1→4 proceed | `/tmp/start_homelab_run.log` | ✅ |
| 3 | Stage 1 — KDE bridge | bridge online (dual-path probe) | `gdbus isReachable=<true>`, `statusIconName=smartphoneconnected`, notif plugin `activeNotifications` present | ✅ |
| 4 | Stage 2 — Krungsri | Zero-OTP pass, **no SMS** | log: `Validating existing session cookies with TradeMan Portfolio` → browser closed | ✅ |
| 5 | Stage 3 — Liberator | cached JWT verified (no 2FA) | log: `Liberator active session verified: https://webtrade.liberator.co.th/Portfolio` | ✅ |
| 6 | Stage 4 — gateway | uvicorn on :8000 + `/console` | log: `Uvicorn running on http://0.0.0.0:8000` + `GET /console 200` | ✅ |
| 7 | Verify artifacts | `/health` 200; `/console` 200; gateway unified health → KDE ONLINE | curl outputs (below) | ✅ |
| 8 | REFLECT | PASS recorded + new anomaly logged | `rca/shared/rca_kdeconnect_bridge.md` KDE-RCA-007 | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health` → `200`
- `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/console` → `200`
- `curl -s http://localhost:8000/api/v1/session/health` → `kdeconnect.status == "ONLINE"`, `reachable == true`

## Out of scope / ห้ามแตะ
- Order placement / tick size / price-volume validation logic.
- Restarting the long-lived MCP server processes (flagged as remediation only — see Open questions).

## Cline Report (Cline เขียน)

### Files changed
- **NEW** `docs/handoff/TASK-pillar1-acceptance.md` (this file).
- **MODIFY** `rca/shared/rca_kdeconnect_bridge.md` — appended incident **KDE-RCA-007** (no code change).
- **MODIFY** `implementation_plan.md` — prepended the Pillar-1 acceptance section; status → DONE/PASS.
- **No production code changed** (verification run).

### Summary
Ran `./start_homelab.sh` headed on `DISPLAY=:0` (background + log tee). **All 4 stages resolved green**:
- Stage 1 KDE bridge online (D-Bus `isReachable=<true>`, icon `smartphoneconnected`, notifications plugin present).
- Stage 2 Krungsri TradeMan verified via the **Zero-OTP saved-session fast-path** (no SMS/OTP).
- Stage 3 Liberator cached-JWT session verified (no 2FA).
- Stage 4 FastAPI gateway started (uvicorn :8000) and `/console` opened (200 OK).

Artifacts verified: `/health` → 200, `/console` → 200, and the freshly-started gateway's own
`/api/v1/session/health` reports `kdeconnect.status = ONLINE`, `reachable = true`.

**New anomaly diagnosed (KDE-RCA-007):** the MCP tool `session_get_health` returned
`kdeconnect: OFFLINE / reachable:false` *while the phone was demonstrably online*. Root cause: the
long-lived MCP server processes (`app.mcp.server` PID 19686 started 15:17; `app.mcp.mcp_server` PID 4056
started 15:16) were launched **without `DBUS_SESSION_BUS_ADDRESS`**, so every `gdbus call --session` probe
inside them fails → `is_device_reachable()` returns `False`, while the socket-based `get_network_routes()`
still reports `TAILSCALE ACTIVE` (the self-contradictory payload). The fresh gateway (PID 49915, which has
the session bus) correctly reports ONLINE — proving the run is green and the `OFFLINE` is a stale-MCP
artifact, not a hardware-bridge failure.

### Tests run + result
- `.venv/bin/python scripts/preflight_check.py` → **7/7 steps** (only FastAPI DOWN, which Stage 4 starts).
- `./start_homelab.sh` → Stages 1–4 green; log `/tmp/start_homelab_run.log`.
- `curl /health` → **200**; `curl /console` → **200**.
- `curl /api/v1/session/health` (gateway PID 49915) → `kdeconnect.status=ONLINE, reachable=true` ✅.
- `session_get_health` (stale MCP PID 19686) → `kdeconnect.status=OFFLINE, reachable=false` ❌ (KDE-RCA-007).
- Standalone `.venv/bin/python -c "...is_device_reachable()"` → `True` (function correct; env is the differentiator).
- No `pytest` run (no code changed).

### Open questions
1. **KDE-RCA-007 remediation:** restart the long-lived MCP servers (`app.mcp.server`, `app.mcp.mcp_server`)
   with `DBUS_SESSION_BUS_ADDRESS` (+ `DISPLAY`) inherited so their live D-Bus probes work. Until then,
   any agent querying `session_get_health` via the stale MCP will wrongly see the OTP bridge OFFLINE.
   Follow-up handoff recommended (optionally make `is_device_reachable()` fail-safe when the session bus is
   absent — design change, own task + test).
2. `session_get_health.brokers.krungsri.status = DISCONNECTED` is **expected**: Stage 2 verifies the saved
   session then closes the browser, so the gateway holds no live tab (`session_file_exists=true`); the next
   broker op resumes Zero-OTP.
3. Liberator saved JWT had ~92 min left at run start; a long gap before the next Liberator op will require a
   fresh login (by design, anti-2FA).

---

## Antigravity Review
- Verdict: PASS
- Notes:
