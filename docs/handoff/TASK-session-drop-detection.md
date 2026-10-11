# TASK-session-drop-detection: Proactive Session-Drop Detection (Phase A)

- Created: 2026-10-06 by Cline
- Broker: Krungsri (TradeMan) + cross-cutting (Sentinel / Preflight / MCP)
- Status: DONE — Phase A (session-drop detection) complete & verified; Phase B (Gate D live headed verification) is next

## Context (RCA — Session-Drop Blindness)
Gate D (live headed verification, Pillar-2 portfolio refactor) was blocked by a **session-drop
blindness** defect: the system reported readiness while sessions were actually missing/expired.

Three concrete gaps found (root cause, 3-point):

1. **MCP drift from REST (F1/F2):** `session_get_health` (`app/mcp/pillars/pillar1_session.py`
   L27–30) reads **in-memory driver state only** (`auth_driver.status` / `is_authenticated`) and
   never looks at the on-disk session file. The REST endpoint
   `GET /api/v1/session/status` (`app/api/v1/endpoints/session.py` L39/L46) *does* expose
   `session_file_exists`. ⇒ MCP agents see `DISCONNECTED` but cannot tell
   "no saved session at all" from "saved session present but driver not attached".
2. **Sentinel blind to file transitions:** `SessionSentinel._monitor_loop`
   (`app/browser/session_sentinel.py` L66–68) only runs `_perform_health_check()` when
   `auth_driver.is_authenticated and auth_driver.page` — so with **no live tab** it never notices
   that `data/session_state.json` disappeared.
3. **Alerts gated to trading hours:** `_perform_health_check` only calls
   `trigger_auto_reconnect()` inside `is_trading_hours()` (09:30–16:35 Mon–Fri). A session that
   drops overnight/after-close is surfaced **silently** (or not at all).

**Evidence:** `data/session_state.json` is MISSING right now (see `data/` listing, 2026-10-06),
Liberator `data/liberator_session.json` present since Oct-5 19:01 (~27h → expired), yet preflight
Krungsri step (`scripts/preflight_check.py` L165–176) still prints
`✅ Krungsri TradeMan: Saved cookies exist` purely from `os.path.exists()`.

**Related RCA:** `LIB-RCA-007` (`rca/liberator/rca_liberator.md`) — preflight ≠ driver verdict.
Already reconciled for Liberator + Click2Win; **Krungsri remains open** and is closed by A5 here.

**Verified facts:**
- `settings.SESSION_STATE_PATH = "data/session_state.json"`, `SESSION_HEARTBEAT_INTERVAL = 1800`.
- Preflight already imports the shared Liberator helper (`app.brokers.liberator.session_health`)
  and has `_path(key, default)` + `click2win_session_status(path)` helpers.
- `tests/conftest.py::isolate_external_side_effects` already stubs
  `kdeconnect_service.send_critical_alert` (AsyncMock) and `LINE_SIMULATION_MODE=True` for all tests.

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/brokers/krungsri/session_health.py` (NEW — shared browser-free inspector)
- `app/mcp/pillars/pillar1_session.py` (expose file-backed session state)
- `app/browser/session_sentinel.py` (file-transition detection + pre-market warning)
- `scripts/preflight_check.py` (Krungsri step uses the shared helper → close LIB-RCA-007)
- `tests/test_krungsri_session_health.py` (NEW)
- `tests/test_session_drop_detection.py` (NEW — MCP + sentinel)
- `tests/test_preflight_check.py` (extend Krungsri render tests)
- `rca/krungsri/rca_krungsri_trademan.md`, `rca/liberator/rca_liberator.md` (LIB-RCA-007 → RESOLVED)
- `learned_workflows/krungsri/krungsri_market_open_operational_runbook.md` (Zero-Contradiction)

## Steps / Task Decomposition (Loop Engineering — บังคับ)

> Mapping to the approved plan: user's A1→A2, A2→A3, A3→A4, A4→A5, A5→A6.
> A1 below is a **new prerequisite** (extract the shared helper) so A2/A5 share a single
> source of truth (no duplicated logic → Zero-Contradiction by construction).

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| A0 | สร้าง handoff นี้ + Task Decomposition | ไฟล์มี decomposition + scope | เปิดไฟล์อ่าน | ✅ |
| A1 | NEW `app/brokers/krungsri/session_health.py`: `session_file_info(path, max_age_hours=12)` → `{exists, mtime, mtime_iso, age_seconds, age_hours, cookie_count, needs_fresh_login, reason}` (reason ∈ MISSING/STALE/RECENT) | missing→`needs_fresh_login=True`/`MISSING`; fresh→`False`/`RECENT`; old mtime→`True`/`STALE` | `.venv/bin/python -m pytest tests/test_krungsri_session_health.py -q` | ✅ |
| A2 | `pillar1_session.session_get_health()` → เพิ่มใน `krungsri_trademan`: `session_file_exists`, `session_file_mtime`, `session_file_age_hours`, `needs_fresh_login`, `session_file_reason` (ใช้ helper A1) | keys ใหม่ปรากฏ + ค่าตรงกับไฟล์จริง/ทดสอบ | `.venv/bin/python -m pytest tests/test_session_drop_detection.py -q -k health` | ✅ |
| A3 | `SessionSentinel`: `check_session_file_state()` + `_check_session_file_transition()` (baseline → present/missing/expired) → log `SESSION_FILE_LOST`/`SESSION_FILE_EXPIRED` + LINE + KDE alert **โดยไม่ต้องมี live tab และไม่ผูกกับ trading hours**; เรียกใน `_monitor_loop` เสมอ | ไฟล์หาย → มี SessionLog + LINE + KDE alert | `.venv/bin/python -m pytest tests/test_session_drop_detection.py -q -k transition` | ✅ |
| A4 | `SessionSentinel`: pre-market warning — pure helpers `bkk_now()`/`is_premarket_window()`/`seconds_until_premarket_window()` + `_check_premarket_warning()` (Weekday **09:45–09:55 BKK** ตาม `KSS-RCA-009`, once/day) + `_next_wait_seconds()` cap sleep; เรียกใน `_monitor_loop` | วันหยุด/นอกหน้าต่าง=False; ในหน้าต่าง+needs login → alert 1 ครั้ง/วัน; sleep ไม่ข้ามหน้าต่าง | `.venv/bin/python -m pytest tests/test_session_drop_detection.py -q -k premarket` | ✅ |
| A5 | `scripts/preflight_check.check_krungsri_session()` ใช้ `session_file_info()` แทน `os.path.exists()` → เลิกพิมพ์ ✅ ลอย ๆ; เพิ่ม `krungsri_session_status()` (mirror `liberator_session_status`) | missing→⚠️; fresh→ℹ️ (ไม่มี ✅); stale→⚠️ EXPIRED | `.venv/bin/python -m pytest tests/test_preflight_check.py -q` | ✅ |
| A6 | Full per-file pytest sweep + อัปเดต RCA (KSS-RCA-011 + LIB-RCA-007→RESOLVED) + runbook (Zero-Contradiction) + Cline Report | suite เขียวทั้งชุด; เอกสารไม่ขัดกับโค้ด | `.venv/bin/python -m pytest tests/<f> -q` ทุกไฟล์ | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python -m pytest tests/test_krungsri_session_health.py tests/test_session_drop_detection.py tests/test_preflight_check.py tests/test_remote_mcp.py tests/test_phase2_auto_reconnect.py -q`
- Full per-file sweep (repo convention): `.venv/bin/python -m pytest tests/<file> -q` for every file in `tests/`

## Out of scope / ห้ามแตะ
- Order placement / cancel / modify, tick size, price/volume validation
- `auth_driver.verify_saved_session()` DOM/purge logic (live path — untouched; A1 is additive/offline)
- Liberator / Click2Win driver internals (already reconciled; only the preflight Krungsri step changes)
- Placing any live order or triggering a real OTP in Phase A

---

## Cline Report (Cline เขียน)
- Files changed (repo ไม่มี git → path เต็มคือแหล่งตรวจเดียว):
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/krungsri/session_health.py` **(NEW)**
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/mcp/pillars/pillar1_session.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/session_sentinel.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/preflight_check.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_krungsri_session_health.py` **(NEW)**
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_session_drop_detection.py` **(NEW)**
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_preflight_check.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/krungsri/rca_krungsri_trademan.md`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/liberator/rca_liberator.md`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/krungsri/krungsri_market_open_operational_runbook.md`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-session-drop-detection.md`

- Summary (Phase A — session-drop detection):
  1. **A1** shared browser-free inspector `session_file_info()` — single source of truth
     (`MISSING` / `STALE` >12h / `RECENT` + `needs_fresh_login`).
  2. **A2** MCP `session_get_health().krungsri_trademan` เพิ่ม `session_file_exists`,
     `session_file_mtime`, `session_file_age_hours`, `needs_fresh_login`, `session_file_reason`
     (align กับ REST `/api/v1/session/status`).
  3. **A3** `SessionSentinel._check_session_file_transition()` ตรวจทุก tick (ไม่ต้องมี live tab /
     ไม่ผูก trading hours) → log `SESSION_FILE_LOST` / `SESSION_FILE_EXPIRED` + alert LINE + KDE.
  4. **A4** pre-market warning Weekday 09:45–09:55 BKK (`KSS-RCA-009`) once/day +
     `_next_wait_seconds()` cap sleep ให้ loop ไม่ข้ามหน้าต่าง.
  5. **A5** preflight Krungsri ใช้ `krungsri_session_status()` → เลิกพิมพ์ ✅ ลอย ๆ
     (missing→⚠️ / stale→⚠️ EXPIRED / recent→ℹ️) ⇒ **LIB-RCA-007 ปิดครบทุกโบรกเกอร์**.
  6. **A6** full sweep เขียว + อัปเดต RCA/runbook.

- Tests run + result (รันจริงทั้งหมด):
  - `.venv/bin/python -m pytest tests/test_krungsri_session_health.py -q` → **6 passed**
  - `.venv/bin/python -m pytest tests/test_session_drop_detection.py -q` → **15 passed**
  - `.venv/bin/python -m pytest tests/test_preflight_check.py -q` → **22 passed**
  - `.venv/bin/python -m pytest tests/test_remote_mcp.py tests/test_phase2_auto_reconnect.py -q` → **11 passed**
  - Full per-file sweep `for f in tests/test_*.py; do pytest "$f" -q; done` → **46 ไฟล์ / 223 passed / 0 failed**
    (log: `/tmp/pytest_sweep3.log`)
  - **หลักฐานสด #1** (`timeout 60 .venv/bin/python scripts/preflight_check.py`):
    `⚠️ Krungsri TradeMan: No saved session (data/session_state.json missing) — fresh login + SMS OTP required.`
    (ไม่มี ✅ ปลอมอีก) และ `⚠️ Liberator WebTrade: Saved session EXPIRED (~14413s ago)` — จบใน 0.22s
  - **หลักฐานสด #2** (in-process โค้ดจริง): `session_get_health()['krungsri_trademan']` →
    `session_file_exists=false, session_file_mtime=null, needs_fresh_login=true, session_file_reason="MISSING"`

- Open questions / สิ่งที่ไม่แน่ใจ:
  1. **uvicorn ยัง cache โมดูลเก่า** — REST `GET /api/v1/session/health` ที่รันอยู่ **คืน payload เก่า**
     (ไม่มี key ใหม่) เพราะ process เริ่มก่อนแก้โค้ดและไม่ได้เปิด `--reload`
     → **ต้อง restart uvicorn ก่อนเริ่ม Gate D (Phase B)** ไม่งั้น MCP/console จะเห็นค่าเดิม
  2. **เกณฑ์ STALE = 12 ชม.** (`DEFAULT_MAX_AGE_HOURS`) เป็นค่าอนุรักษ์นิยมที่ผมเลือก เพราะ TradeMan SSO
     เป็น session cookie (ไม่มี JWT `exp` ให้ decode) — ถ้าทราบ TTL จริงของ SSO ควรปรับค่านี้
     (แก้ที่ `app/brokers/krungsri/session_health.py` ที่เดียว)
  3. `_next_wait_seconds()` เปลี่ยนจังหวะ sleep ของ loop **ก่อน** ถึงหน้าต่าง 09:45 (หดลงเป็นช่วง ๆ)
     — ตั้งใจให้เป็นแบบนั้นและมีขอบเขต (ไม่ busy-loop) แต่ถ้าไม่ต้องการให้แตะจังหวะ loop เดิม
     ให้ถอด `_next_wait_seconds()` ออกแล้วคง `asyncio.sleep(self.interval_seconds)`
  4. Sentinel baseline เป็น **in-memory** (`_last_session_file_exists`) → restart แล้ว tick แรกจะไม่ alert
     (by design กัน alert spam ตอน start) ถ้าต้องการข้าม restart ต้อง persist ลง DB (นอก scope)
  5. `check_premarket_readiness()` เปิดไว้ให้ console/API เรียกใช้ต่อได้ แต่**ยังไม่ wire** เข้า
     console/endpoint (นอก scope ของ task นี้)
  6. ไม่ได้ทดสอบการยิง alert จริงไปมือถือ (LINE_SIMULATION_MODE + KDE mock ในเทสต์ตามนโยบาย);
     การยิงจริงจะพิสูจน์ได้ตอน Gate D / เมื่อ session หลุดจริง

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
