# TASK: /console Redesign — Component Toggles + Real Reload + Pillar×Broker Feature Matrix

**Mode:** Plan → Act (approved 2026-10-10)
**Scope:** Add 3 operator capabilities to the existing `/console` in-place (same repo/machine).
**Rules applied:** `loop_engineering.md` (atomic units + per-unit verify), `broker_pdca_rca.md` (Zero-Contradiction), `root_cause_and_escalation.md` (Anti-Mock, pre-flight).

## User Requirements (Thai, verbatim intent)
1. รัน uvicorn แล้ว login Krungsri ผ่าน LINE OTP — ทำงานจริง
2. ต่อราคา + สั่งการผ่าน LINE — ทำงานจริง
3. DeepSeek — ใช้งานได้จริงใน production mode

## Decisions locked (2026-10-10)
| Item | Decision |
|------|----------|
| Rename flag | `ENABLE_PHASE3_SCHEDULER` → `ENABLE_INTRADAY_SCHEDULER` (default **OFF**) |
| P4 SBL / P6 Tactical / P7 Agentic | **ปิดไว้ก่อน** (logic untouched; revisit later) |
| Reload mechanism | `os.execv` re-exec of the uvicorn process (real restart) |
| Structure | Reuse existing repo/machine (NOT a separate `production/` folder) |

## Steps / Task Decomposition (atomic + per-step verify)

### Unit 1 — Rename config flag
- **Files:** `app/core/config.py`, `app/main.py`, `scripts/services_status.py`, `.env`
- **Expected:** no remaining `ENABLE_PHASE3_SCHEDULER` reference; value stays OFF
- **Verify:** `grep -rn ENABLE_PHASE3_SCHEDULER app/ scripts/ .env` → empty; `.venv/bin/python -c "import app.main"` exit 0

### Unit 2 — Feature matrix SSOT
- **File:** `app/core/feature_matrix.py` (NEW)
- **Expected:** `FEATURE_MATRIX` dict (Pillar × Broker × status) + helper `build_matrix_payload()`
- **Verify:** `.venv/bin/python -c "from app.core.feature_matrix import build_matrix_payload; print(build_matrix_payload()['pillars'][0]['key'])"`

### Unit 3 — Admin endpoint
- **File:** `app/api/v1/endpoints/admin.py` (NEW) + register in `app/api/v1/api.py`
- **Routes:** `GET /admin/feature-matrix`, `GET /admin/components`, `POST /admin/components/{key}`, `POST /admin/reload`
- **Expected:** toggles write `.env` atomically + update in-process `settings`; reload = `os.execv`
- **Verify:** `scripts/verify_changes.py app/api/v1/endpoints/admin.py` + new test

### Unit 4 — Console UI
- **File:** `app/console.py`
- **Expected:** Header gains 🔄 Reload button; new Feature Matrix table; new Component Toggles panel; JS wired to admin endpoints
- **Verify:** `/console` contains new element IDs; `test_console_cockpit_api.py` passes

### Unit 5 — Close-out
- **Verify:** `scripts/verify_changes.py --full` once

## Cline Report

**Status:** ✅ COMPLETE (all 5 units done + live smoke verified)
**Date:** 2026-10-10 · **Mode:** Plan → Act

### Files changed (full paths)
| # | Path | Lines | Change |
|---|------|-------|--------|
| 1 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/core/feature_matrix.py` | 146 | **NEW** — `FEATURE_MATRIX` (Pillar × Broker SSOT) + `build_matrix_payload()` |
| 2 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/api/v1/endpoints/admin.py` | 282 | **NEW** — 4 admin routes (feature-matrix, components GET/POST, reload `os.execv`) |
| 3 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/api/v1/api.py` | 29 | Register `admin` router |
| 4 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/console.py` | 2468 | Header 🔄 Reload button; Feature Matrix table; Component Toggles panel + JS wiring |
| 5 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/core/config.py` | 127 | Rename `ENABLE_PHASE3_SCHEDULER` → `ENABLE_INTRADAY_SCHEDULER` (default `False`) |
| 6 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/main.py` | 150 | Use renamed flag in startup log/guards |
| 7 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/services_status.py` | 309 | Report renamed flag |
| 8 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.env` | — | `ENABLE_INTRADAY_SCHEDULER=false` |
| 9 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/verify_changes.py` | 302 | `MODULE_TEST_MAP` entries for the new modules |
| 10 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_admin_console.py` | 115 | **NEW** — 5 admin endpoint tests |
| 11 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_console_cockpit_api.py` | 167 | 9 cockpit API/HTML tests |
| 12 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_services_status.py` | 30 | **NEW** — rename coverage |
| 13 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_verify_changes.py` | 165 | Mapping coverage |

### Summary
- **Single-writer `.env`**: admin toggle reuses `webhook_line._write_env_key` → atomic write (LINE-RCA-003), then updates in-process `settings`.
- **`restart_required`** grounded in code inspection — daemons (`intraday_scheduler`, `action_exit_dispatcher`, `agentic_orchestrator`) need a reload; safety/LINE flags apply immediately.
- **`TRADING_MODE` is NOT web-togglable** (by design) — LIVE switch only via LINE `MODE LIVE <PIN>`.
- **Reload = real restart** via `os.execv` (`--reload` intentionally dropped); verified by PID stability + fresh uvicorn boot.
- **Zero-Contradiction**: `ENABLE_PHASE3_SCHEDULER` fully removed from `app/`, `scripts/`, `.env` (only remaining hit is a docstring in `tests/test_services_status.py` *documenting* the rename).

### Tests run + results
1. `.venv/bin/python scripts/verify_changes.py app/api/v1/endpoints/admin.py ...` → **PASS** per unit (admin 5/5, cockpit 9/9, services_status, verify_changes).
2. **Live smoke** (throwaway `uvicorn ... --port 8099`, pid 26640):
   - `GET /api/v1/admin/feature-matrix` **200** · `GET /api/v1/admin/components` **200**
   - `.env` write/restore round-trip OK · `/console` contains all new element IDs
   - `POST /api/v1/admin/reload` → **real `os.execv`**: PID stayed **26640**, uvicorn re-booted `13:14:11 → 13:14:15`, `/health` **200** recovered.
   - Cleanup: pid 26640 killed (confirmed stopped); `/tmp/smoke_uvicorn.log`, `/tmp/smoke_console.html` removed.
3. **Visual verification** — `data/screenshots/console_redesign_feature_matrix_toggles.png` + `console_redesign_component_toggles.png`: Pillar × Broker matrix and toggle cards render correctly (Thai labels, badges, `controlPanel` height 921px, all 7 ids present). Checkbox states match reality: daemons OFF (unchecked), safety gates DRY_RUN + HITL checked.
4. **Close-out full gate** — `.venv/bin/python scripts/verify_changes.py --full` → **`3 failed, 365 passed` in 172s** (see Open questions).

### Open questions / notes
- ⚠️ **Out-of-scope pre-existing failures (NOT caused by this task).** The full gate reports 3 failures, all in `tests/test_liberator_change_order.py::test_negotiate_price_*`:
  `test_negotiate_price_amends_in_place_and_never_cancels`, `..._is_noop_when_already_at_target`, `..._propagates_amend_failure`.
  - **RCA (proven):** `LiberatorDriver.negotiate_price()` has a weekend guard `if now_bkk.weekday() in (5, 6): return {… "status": "MARKET_CLOSED" …}` — that branch has **no `action` key**. Today **2026-10-10 is a Saturday** (`weekday()==5`), so all three tests fall into the MARKET_CLOSED branch → `KeyError: 'action'` / `assert True is False`.
  - **Evidence:** re-running the identical three scenarios with the clock frozen to a weekday (Wed 2026-10-07) returns what the tests expect — `action='AMENDED_IN_PLACE'`, `action='NONE'`, `success=False + action='AMEND_UNVERIFIED'`. The only other market-closed test (`test_change_order_stages_...weekend`) passes because it explicitly monkeypatches `datetime` to a Saturday.
  - **Impact:** date-dependent (weekend-only) test brittleness; **zero** overlap with this task's files (no edits to `app/brokers/liberator/driver.py` or that test). Recommend a small follow-up: freeze the clock in the three `negotiate_price` tests (e.g. `monkeypatch` `datetime` to a weekday), same pattern as the weekend test.
- `python -m app.mcp.mcp_server` (stdio) remains legacy/retired — unchanged.
- No open blockers. All in-scope requirements (login + ต่อราคา + LINE ordering + DeepSeek in production) are unaffected by this task's scope (UI/admin capabilities only).
