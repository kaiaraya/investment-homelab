# TASK-line-cli-retire: retire /login /logout /quicktrade /halt → RustDesk

- Created: 2026-10-28 by Hermes `default` (planner lane)
- Loop: LINE CLI reshape · Kanban card: `t_ccaf8647`
- Lane: `homelab-build` · Tier: 🟡 T1 · Model: `gemini-3.1-pro` (provider `antigravity-subscription-directsdk`)
- Broker: N/A · Probe: NONE (no DOM/XHR touched)
- Branch: `task/line-cli-retire` (off `main`) · human squash → `main` = gate #2
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/line_cli/parser.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/line_service.py`

## Context (planner)
Retire four slash commands from the LINE CLI. Session (CDP) is now opened by the human via RustDesk, not through LINE, so `/login` and `/logout` handlers are deleted. `/quicktrade` is dead (order entry is `/buy /sell /short /cover`). `/halt` slash command is dead — the kill switch stays reachable only via the `PANIC` / `KILL` keywords in `line_service.py`. The command aliases STAY in the parser so a retired command answers with a short Thai pointer instead of the generic "ไม่รู้จักคำสั่ง".

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/parser.py`
- `app/services/line_cli/handlers.py`
- `app/services/line_cli/cards.py`
- `app/services/line_service.py`
- `tests/test_line_cli_parser.py`
- `tests/test_line_cli_flow.py`
- `tests/test_line_cli_handlers_sbl.py`

## Context map (grep anchors — line numbers drift, trust the symbols)
| File | Symbol | Why |
|------|--------|-----|
| `app/services/line_cli/parser.py` | `_ALL_BROKERS`, `_REQUIRE_BROKER`, `flags.discard("force")` | edit (drop retired cmds from sets) |
| `app/services/line_cli/handlers.py` | `handle()` L2556-2572 (`cmd == "login"/"logout"/"quicktrade"/"halt"`) | edit (delete branches, add retired short-circuit) |
| `app/services/line_cli/handlers.py` | `_CDP_PORT` L189, `_attach_session_cdp` L192, `_detach_session_cdp` L236, `_handle_login` L711, `_close_owned_browsers` L803, `_handle_logout` L837 | DELETE (login/logout-only) |
| `app/services/line_cli/handlers.py` | `_ATTACH_PURPOSE`, `_broker_session_alive` | KEEP (used by `/sync`, `/nego`, `/status`) |
| `app/services/line_cli/cards.py` | `unavailable_card` L302, `UNAVAILABLE_HINT` | edit (drop login button) |
| `app/services/line_cli/handlers.py` | `unavailable_card(` call sites L1104/1134/1159/1184/1631 | edit (rename kwarg) |
| `app/services/line_service.py` | `clean_cmd == "halt"` L178, `LOGIN_TIMEOUT_SECONDS` L169/188 | edit (remove bypass + timeout) |

## Steps / Task Decomposition (atomic — ทำทีละ step ห้าม batch)

1. **parser.py** — `_ALL_BROKERS` → `{"help", "status", "port", "cash", "orders"}` (remove login/logout/quicktrade/halt). `_REQUIRE_BROKER` → `{"nego"}`. Replace the two flag-discard lines with `flags.discard("force")` (unconditional) + the existing `sync` guard. Keep the `login`/`logout`/`quicktrade`/`trade`/`halt`/`หยุด` entries in `COMMAND_ALIASES`.
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_parser.py -q`

2. **handlers.py** — add a module-level `RETIRED_COMMANDS: Dict[str, str]` mapping `login`/`logout`/`quicktrade`/`halt` → Thai pointer messages (login/logout mention "เปิด CDP session ผ่าน RustDesk เอง"; halt mentions "ใช้คำว่า PANIC หรือ KILL แทน"). In `handle()`, right after the `CliError` block and BEFORE the `TradeOrder` isinstance check, insert:
   ```python
   if isinstance(parsed, CliCommand):
       retired = RETIRED_COMMANDS.get(parsed.cmd)
       if retired is not None:
           await service._send_reply(reply_token, _text(retired))
           return {"status": "CLI_RETIRED", "cmd": parsed.cmd}
   ```

3. **handlers.py** — delete the `cmd == "login"`, `cmd == "logout"`, `cmd == "quicktrade"`, `cmd == "halt"` branches in `handle()` (L2558-2576). Leave `status`/`nego`/other branches intact.

4. **handlers.py** — delete the dead functions `_CDP_PORT`, `_attach_session_cdp`, `_detach_session_cdp`, `_handle_login`, `_close_owned_browsers`, `_handle_logout` (and any now-unused imports they were the only consumers of — check with grep). KEEP `_ATTACH_PURPOSE` and `_broker_session_alive`.
   - Verify: `grep -rn '_handle_login\|_handle_logout\|_attach_session_cdp\|_detach_session_cdp\|_close_owned_browsers\|_CDP_PORT' app/ | grep -v '\.pyc'` → no matches (except the pycache binary).

5. **line_service.py** — remove the `if clean_cmd == "halt": return await _cli_handlers.handle(...)` bypass block (L178) and collapse the timeout map to `NEGO_TIMEOUT_SECONDS if clean_cmd in ("nego", "negotiate") else DEFAULT_TIMEOUT_SECONDS`. Drop `LOGIN_TIMEOUT_SECONDS` from the `from app.services.line_cli.queue import (...)` list (L169). (Leave the constant in `queue.py` unless grep proves it is used nowhere.)

6. **cards.py** — rewrite `unavailable_card(*, broker: str, login_cmd: str)` → `unavailable_card(*, broker: str, hint: str)`: render the hint as plain warn text, remove the `🔐 {login_cmd}` message button (no slash command to fire). Update the 5 call sites in handlers.py to `hint="เปิด CDP session ผ่าน RustDesk"` (and remove the now-unused `login_cmd` local at ~L1104).

7. **tests** — 
   - `tests/test_line_cli_parser.py`: keep `test_login_force_and_logout_aliases` asserting the aliases STILL parse to `CliCommand(cmd="login"/"logout")`; add `test_retired_commands_still_parse` asserting `/quicktrade`, `/halt`, `/login`, `/logout` parse to the right `cmd`.
   - `tests/test_line_cli_flow.py`: DELETE the login/logout flow tests (they reference deleted handlers) and add ONE `test_retired_login_replies_pointer` asserting `/login kss` → `res["status"] == "CLI_RETIRED"` and the reply text contains "RustDesk".
   - `tests/test_line_cli_handlers_sbl.py`: change `test_quicktrade_command` to assert `res["status"] == "CLI_RETIRED"`.
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_parser.py tests/test_line_cli_flow.py tests/test_line_cli_handlers_sbl.py -q`

## Acceptance / Done when
- Targeted tests green (NO full suite — ห้ามรัน pytest ทั้งชุด): `.venv/bin/python -m pytest tests/test_line_cli_parser.py tests/test_line_cli_flow.py tests/test_line_cli_handlers_sbl.py -q`
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/parser.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/line_service.py` → PASS
- `grep` proves zero remaining references to the deleted login/logout symbols.
- Committed to `task/line-cli-retire` (never `main`, never `git add -A` — stage only these files). Commit msg: `TASK-line-cli-retire: refactor(line_cli): retire login/logout/quicktrade/halt → RustDesk`.

## Out of scope / ห้ามแตะ
- `PANIC`/`KILL`/`RESET`/`MODE` keyword handling in `line_service.py` (kill switch stays).
- `/sync` and `/nego all` (separate cards).
- Settrade Streaming / Liberator drivers.
- The uncommitted model19 work on `task/snap1` (do NOT stage or commit it).

## Worker contract (บังคับ)
- Targeted test only — never `pytest` the full suite.
- Fail-closed: if a stale cache or unexpected state appears, stop and report, don't force through.
- Create `task/line-cli-retire` off `main`; stage ONLY your card's files; never `git add -A`; never commit to `main`.
- Fill `## Worker Report` (commit, files, summary, tests run, open questions) before marking done.
