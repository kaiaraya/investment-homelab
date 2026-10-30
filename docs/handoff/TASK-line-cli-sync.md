# TASK-line-cli-sync: add `/sync portfolio|orders|borrow|balance`

- Created: 2026-10-28 by Hermes `default` (planner lane)
- Loop: LINE CLI reshape · Kanban card: `t_53b32b72`
- Lane: `homelab-build` · Tier: 🟡 T1 · Model: `gemini-3.1-pro` (provider `antigravity-subscription-directsdk`)
- Broker: kss + lib (read-only sync to DB) · Probe: NONE (reuses existing CDP writers)
- Branch: `task/line-cli-sync` (off `main`, AFTER `task/line-cli-retire` merged) · human squash → `main` = gate #2
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/line_cli/parser.py app/services/line_cli/handlers.py`

## Context (planner)
Add one explicit DB-hydration command: `/sync [portfolio|orders|borrow|balance]`, default (no arg) = all four, always both brokers (kss + lib), SBL borrow = kss only (Krungsri-only). Reuses the trusted writers `sync_portfolio_from_cdp` (writes `broker_accounts` AND `positions`) and `sync_orders_from_cdp` (writes manual orders). The SBL borrow sync is currently INLINED inside `_handle_sbl` — extract it to `_sync_sbl_lots(db)` so both `/sbl sync` and `/sync borrow` share it.

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/parser.py`
- `app/services/line_cli/handlers.py`
- `tests/test_line_cli_parser.py` (add parse cases)
- `tests/test_line_cli_sync.py` (NEW)

## Context map (grep anchors)
| File | Symbol | Why |
|------|--------|-----|
| `app/services/line_cli/parser.py` | `COMMAND_ALIASES`, `_SBL_COMMANDS`, `SblCommand`, `ParseResult`, `_parse_sbl(` | pattern to copy; wire `_parse_sync` next to it |
| `app/services/line_cli/handlers.py` | `_handle_sbl` (inline `force_browser` sync block) | extract `_sync_sbl_lots(db)` from it |
| `app/services/line_cli/handlers.py` | `_handle_read`, `_broker_session_alive`, `_lock_for`, `_STARTED`, `_now_bkk`, `_text`, `BROKER_LABEL` | reuse for `_handle_sync` |
| `app/services/line_cli/handlers.py` | `handle()` dispatch | add `cmd == "sync"` branch |
| `app/services/broker_cdp/sync_service.py` | `sync_portfolio_from_cdp` L433, `sync_orders_from_cdp` L665 | call (they open/commit their own session) |
| `app/brokers/krungsri/sbl_realtime_driver.py` | `krungsri_sbl_driver.scrape_sbl_lots` | call for borrow |
| `app/db/models.py` | `SBLBorrowLot` | upsert target |

## Steps / Task Decomposition (atomic)

1. **parser.py** — add `SyncCommand` dataclass (`cmd: str = "sync"`, `target: Optional[str] = None`); extend `ParseResult` union with `SyncCommand`; add aliases `"sync": "sync", "ซิงค์": "sync"` to `COMMAND_ALIASES`; add `_SYNC_TYPES` map (portfolio/orders/borrow/balance + Thai aliases); add `_parse_sync(rest)` (one target token allowed, else `CliError`); wire `if canonical == "sync": return _parse_sync(rest)` into `parse()` next to the SBL command branches.
   - Verify: new parser cases (see step 5) — write them first as RED.

2. **handlers.py** — extract `_sync_sbl_lots(db) -> int` out of `_handle_sbl`'s inline `force_browser` block: scrape via `krungsri_sbl_driver.scrape_sbl_lots(...)`, UPSERT active lots into `SBLBorrowLot` (update `remaining_qty` on existing ACTIVE row, else insert), `await db.commit()`, return count. Replace the inline block in `_handle_sbl` with `await _sync_sbl_lots(db)`.
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_handlers_sbl.py -q` (existing `/sbl sync` tests still green).

3. **handlers.py** — add `_handle_sync(parsed, service, reply_token, push_target, db)`:
   - lock via `_lock_for("sync", target or "-")` (reply "⏳ กำลังทำงานอยู่" if locked); set `_STARTED[key]`.
   - For each broker in `("kss","lib")`: if `not await _broker_session_alive(b)` → append "🔴 <label> session หลุด — เปิด CDP ผ่าน RustDesk ก่อน" and `continue`.
   - `portfolio`/`balance` share ONE `sync_portfolio_from_cdp(b)` call (writes both `broker_accounts` + `positions`); report positions count (portfolio) and line/cash (balance).
   - `orders` → `sync_orders_from_cdp(b)`, report `new_manual_count`.
   - `borrow` (target None/"borrow") → `_sync_sbl_lots(db)` (kss only), report lot count.
   - push the report (or "✅ sync ครบถ้วน") via `service.push_message(..., to_user_id=push_target)`; wrap in try/except that pushes `❌ sync ไม่สำเร็จ: <Type>: <msg[:120]>`; `_STARTED.pop(key)` in finally.
   - Return `{"status": "CLI_SYNC_ALL", "target": target}`.

4. **handlers.py** — dispatch: add `if cmd == "sync": return await _handle_sync(parsed, service, reply_token, push_target, db)` in `handle()` (before the unknown-command fallback).

5. **tests** — `tests/test_line_cli_sync.py` (NEW): `test_parse_sync_default` (`/sync` → `SyncCommand(target=None)`), `test_parse_sync_each_type` (4 targets + Thai aliases), `test_parse_sync_bad_param` (`/sync foo` → `CliError`), `test_handle_sync_routes_to_writers` (AsyncMock session-alive→True; monkeypatch the three writers; assert each awaited once per broker and report lists all four), `test_handle_sync_skips_down_broker` (lib session False → lib writers not called, report mentions "หลุด").
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_sync.py tests/test_line_cli_parser.py -q`

## Acceptance / Done when
- `.venv/bin/python -m pytest tests/test_line_cli_sync.py tests/test_line_cli_parser.py tests/test_line_cli_handlers_sbl.py -q` → green (targeted only, NO full suite).
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/parser.py app/services/line_cli/handlers.py` → PASS (if it flags a new file mapping for `test_line_cli_sync.py`, pass `--tests` or note it explicitly in the review).
- `/sync` dispatches (grep: `cmd == "sync"` in `handle()`), `/sbl sync` still works via the extracted helper.
- Committed to `task/line-cli-sync` (never `main`, never `git add -A`). Commit msg: `TASK-line-cli-sync: feat(line_cli): /sync portfolio/orders/borrow/balance`.

## Out of scope / ห้ามแตะ
- Changing the writers in `sync_service.py` (reuse as-is).
- `/nego all` (separate card). Order entry / tick logic. Settrade Streaming drivers.

## Worker contract (บังคับ)
- Targeted test only. Fail-closed. Commit to `task/line-cli-sync` off `main`; stage ONLY your files; never `git add -A`; never `main`.
- Fill `## Worker Report` before done.
