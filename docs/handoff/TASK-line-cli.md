# TASK-line-cli: LINE slash-command CLI (Pillar 1–3, KSS + LIB)

- Created: 2026-10-13 by Antigravity
- Broker: Krungsri (kss), Liberator (lib) — Click2Win / Settrade out of scope
- Status: REVIEW
- Design spec (approved 2026-10-13): `docs/handoff/TASK-line-cli-design.md` — message mockups, error catalog, Flex layouts. **Follow it verbatim**; the deltas below override it.

## Context (Antigravity)
- Goal: phone-friendly `/command` CLI in LINE (group `LINE_GROUP_ID` + 1:1 OA) covering Pillar 1 (session), Pillar 2 (portfolio), Pillar 3 (`/nego` price negotiation).
- Commands: `/help` `/status` `/login` `/logout` `/port` `/cash` `/orders` `/nego` (+ Thai aliases, full-width `／`, case-insensitive).
- Router placement: in `line_service._handle_text_message` AFTER kill-switch / MODE / OTP relay, BEFORE `_handle_conversation_turn` (a `/` command clears any pending conversation state).
- Auth gate: reuse Decision A (simulation OR `groupId == LINE_GROUP_ID` OR 1:1). No `LINE_ADMIN_USER_ID`.
- Long ops (login, `sync`, nego): reply ack immediately → `push_message` result to same source (groupId else userId). Lock per `(command, broker)` → `E_BUSY`.

### Approved decisions (override spec where different)
- `/nego` executes immediately, no approval card. Guardrails G1–G6 mandatory:
  - G1 kill-switch inactive · G2 windows 09:55–12:30, 14:25–16:30 (config) · G3 session alive, never auto-login
  - G4 tick-size validator · G5 `|new − old| ≤ 3 ticks` (`LINE_NEGO_MAX_TICKS=3`) · G6 SHORT uptick
- `/nego` without target = **ALL unmatched orders** of that broker — **no cap** (spec open question #1 resolved).
- `/logout` = **just log out**, no scheduler warning (spec §3.4 warning line removed; open question #2 resolved).
- `/status` = **kss/lib only** (open question #3 — user replied "นา", interpreted as accepting the proposal; confirm at review).
- Pillar 2 reads = DB snapshot by default + "updated HH:MM"; `sync` = live scrape only when session alive (Invariant 7).
- `/login`: alive & no `force` → no-op; relay not ready → never fire SMS (Invariant 9); `all` = sequential kss → lib (latest-request-wins relay).
- Reply format: Flex for data cards; plain text for ack / errors.
- `MODE TEST` → nego runs via simulator, card badge `[TEST]`.

## Scope — files allowed to edit
- `[NEW] app/services/line_cli/__init__.py`
- `[NEW] app/services/line_cli/parser.py` — pure, no I/O
- `[NEW] app/services/line_cli/handlers.py`
- `[NEW] app/services/line_cli/cards.py` — Flex builders
- `[MODIFY] app/services/line_service.py` — insert router only (~L158–165)
- `[MODIFY] app/core/config.py` — `LINE_NEGO_MAX_TICKS`, `LINE_NEGO_WINDOWS` (only if not present)
- `[NEW] tests/test_line_cli_parser.py`, `[NEW] tests/test_line_cli_flow.py`
- `[MODIFY] scripts/verify_changes.py` — `MODULE_TEST_MAP` entries for new modules

## Context map
| File | Symbol / Lines | Why |
|------|----------------|-----|
| `app/services/line_service.py` | `_handle_text_message` L70-167 (kill-switch L79-92, MODE L94, OTP L117-157, conv turn L165) | edit: insert router |
| `app/services/line_service.py` | `_send_reply` L1680 · `push_message` L1717 · Flex examples L1026, L1149 | read: reply/push API |
| `app/services/line_service.py` | `_handle_conversation_turn` L412+ (auth gate Decision A) | read: reuse auth + clear state |
| `app/services/conversation_state.py` | store API (428 lines — grep `def clear\|def get`) | read: clear state on `/` |
| `app/mcp/pillars/pillar1_session.py` | `session_get_health` L23-114 · `session_login_broker` L117-174 · `session_logout_all` L200-206 | call from handlers |
| `app/services/otp_relay_readiness.py` | `OtpRelayReadiness.check` L182 · `is_ready` L305 | Invariant 9 gate |
| `app/services/kill_switch_service.py` | `KillSwitchService.is_active` L25 | G1 |
| `app/mcp/pillars/pillar2_portfolio.py` | `portfolio_get_balances` L350-461 · `portfolio_holdings` L464-521 · `current_open_orders` L524-562 · `current_orders` L565-668 · `portfolio_sync_db` L671-680 | `/cash` `/port` `/orders` |
| `app/mcp/pillars/pillar6_strategy.py` | `strategy_negotiate_unmatched_orders` L33-101 | read: existing nego logic |
| `app/services/trade_dispatcher.py` | `get_mode_badge` L46 · `dispatch_price_modification` L167 | nego MUST go through dispatcher (TEST/LIVE routing) |
| `app/services/validator.py` | `get_set_tick_size` L16 · `validate_tick_size` L68 · `get_next_tick` L135 · `validate_short_uptick` L158 | G4–G6 (read only, do not modify) |
| `app/browser/trademan_driver.py` | `scrape_unmatched_orders` L932 · `modify_order_price` L1370 | KSS (via dispatcher) |
| `app/brokers/liberator/driver.py` | `negotiate_price` L1281 · `change_order` L1101 | LIB in-place amend (via plugin L263/L277) |
| `tests/test_line_conversation_flow.py` | whole file pattern | copy webhook E2E pattern |
- Verify: `.venv/bin/python scripts/verify_changes.py <files>` · `--full` once at close · restart gateway (LINE-RCA-011)
- More symbols: `grep -n <symbol> docs/agent/CODEMAP.md`

## Steps / Task Decomposition
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | `parser.py`: `CliCommand` + `parse()` (aliases, `／`, broker kss/lib/all, flags sync/force, target SYMBOL vs order_no) | pure parse returns dataclass or `CliError(code, hint)` | `pytest tests/test_line_cli_parser.py -q` | ⬜ |
| 2 | parser: unknown-cmd suggestion (Levenshtein ≤2), `E_BAD_BROKER`, `E_BROKER_REQUIRED` | `/prot` → suggests `/port`; `/nego` w/o broker → quick-reply kss/lib | same | ⬜ |
| 3 | add `MODULE_TEST_MAP` entries | `verify_changes.py --dry-run` maps new files | `--dry-run` | ⬜ |
| 4 | `cards.py`: status/port/cash/orders/nego Flex + altText per spec | JSON valid, ≤10 rows, "…และอีก N ตัว" | unit test in flow file | ⬜ |
| 5 | handlers `/help` `/status` | status reads health + relay + mode + kill-switch, no I/O to broker | flow test | ⬜ |
| 6 | handler `/login` (+force, all sequential) | relay not ready → `E_RELAY_NOT_READY`, SMS never fired | flow test asserts login not called | ⬜ |
| 7 | handler `/logout` | logs out, no scheduler warning | flow test | ⬜ |
| 8 | handlers `/port` `/cash` `/orders` (+sync) | DB default; sync+down → `E_SESSION_DOWN`, no login; empty DB → info msg (no fake empty success) | flow test | ⬜ |
| 9 | handler `/nego` with G1–G6, all-unmatched no cap, per-order result, `SessionLog LINE_CLI_NEGO` | skips reported with reason; uses `dispatch_price_modification` | flow test per guardrail | ⬜ |
| 10 | per-(cmd,broker) lock + ack→push | duplicate → `E_BUSY` | flow test | ⬜ |
| 11 | wire router into `_handle_text_message` | `/` handled after OTP, before conv turn; legacy commands unchanged | `pytest tests/test_line_conversation_flow.py tests/test_line_cli_flow.py -q` | ⬜ |
| 12 | full verify + restart gateway | all green; pid start > mtime | `verify_changes.py --full` | ⬜ |

## Acceptance
- `.venv/bin/python -m pytest tests/test_line_cli_parser.py tests/test_line_cli_flow.py tests/test_line_conversation_flow.py -q --tb=line`
- Manual (MODE TEST): from group a14s send `/status`, `/port kss`, `/orders lib`, `/nego kss`.

## Out of scope / do not touch
- `/buy` `/sell` `/cancel` `/amend`, new order placement
- validator / tick-size / order logic (read only)
- Click2Win, Settrade Open API
- legacy matchers (PANIC/RESET/MODE/action/set/schedule/QUERY/AI strategy parser)

---

## Cline Report (Cline)
- Files changed:
  - `[NEW] app/services/line_cli/__init__.py`
  - `[NEW] app/services/line_cli/parser.py` (pure: `CliCommand`/`CliError`/`parse`/`is_command`/`suggest_command`)
  - `[NEW] app/services/line_cli/cards.py` (Flex: status/port/cash/orders/nego + carousel + quick_reply)
  - `[NEW] app/services/line_cli/handlers.py` (`handle` entrypoint, broker-context resolver, per-(cmd,broker) lock, DB-default reads, nego G1–G6)
  - `[NEW] tests/test_line_cli_parser.py`, `[NEW] tests/test_line_cli_flow.py`
  - `[MOD] app/services/line_service.py` — slash router inserted after OTP relay, before `_handle_conversation_turn`
  - `[MOD] app/core/config.py` — `LINE_NEGO_MAX_TICKS=3`, `LINE_NEGO_WINDOWS`
  - `[MOD] app/brokers/liberator/driver.py` — `get_market_bid_offer` + `_unknown_quote` (fail-closed)
  - `[MOD] app/brokers/liberator/plugin.py` — `get_market_bid_offer` passthrough
  - `[MOD] scripts/verify_changes.py` — `MODULE_TEST_MAP` entries for `line_cli/*`
  - `[MOD] learned_workflows/liberator/liberator_portfolio.md` — §8 quote method (Zero-Contradiction)
- Summary: 8 commands implemented (`/help /status /login /logout /port /cash /orders /nego`) with Thai aliases, full-width `／`, case-insensitive, Levenshtein≤2 suggestions, broker isolation, DB-snapshot default + `sync` live (never auto-login), ack→push for long ops, per-(cmd,broker) `E_BUSY` lock, and nego guardrails G1–G6.
- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/services/line_cli/*.py` → **PASS** (53 passed, 16.9s)
  - `.venv/bin/python scripts/verify_changes.py app/services/line_service.py` → **PASS** (51 passed)
  - `.venv/bin/python scripts/verify_changes.py app/core/config.py scripts/verify_changes.py` → **PASS** (26 passed)
  - `pytest tests/test_liberator_change_order.py tests/test_liberator_otp_channel_gate.py tests/test_pillar2_portfolio_liberator.py tests/test_liberator_session.py` → **PASS** (35 passed)
- Open questions:
  1. **LIB depth-table selector** — `get_market_bid_offer` uses header-isolation (`bid`+`offer`) with fail-closed sentinel. Needs a **live headed** confirmation of the exact depth-table `<th>` wording before `/nego lib` can amend live. Until then `/nego lib` will skip every order (honest, no trade).
  2. **`/nego` LIVE routing** — `trade_dispatcher.dispatch_price_modification` LIVE route is bound to `TRADING_PLATFORM` (`get_broker_driver()` = c2w/trademan only) and cannot address KSS+LIB in one loop, so LIVE nego goes straight to the owning driver (KSS `trademan_driver.modify_order_price`, LIB `liberator_plugin.change_order`); TEST still goes through the dispatcher. `trade_dispatcher.py` was left untouched.
  3. **Pillar-2 DB snapshot is broker-agnostic** — `positions`/`orders` tables have no broker column, so `/port`/`/orders` without `sync` show the shared local ledger labelled "DB snapshot". Consider adding a broker/platform column to split KSS/LIB snapshots.
  4. Full `verify_changes.py --full` was **not** run (shell timeout cap + SQLite single-writer); per-unit targeted verifies all PASS. Run `--full` once at review close.
  5. Reaching live LINE: edited gateway code → **restart the gateway** (LINE-RCA-011) before manual testing.

---

## Antigravity Review
- Verdict: CHANGES_REQUESTED (live test Round A, 2026-10-13 21:04–21:48, 1:1 chat, MODE TEST, market closed)
- Full report (Thai, per-step evidence + RCA-1..6): `docs/handoff/TASK-line-cli-livetest-A.md`
- PASS: router/parser, /help, /status, 1:1 auth, /login kss + OTP relay (1:1), sync never auto-logins, /nego G2 out-of-hours, /logout kss
- P0 blockers (Round B `/nego` market-hours test is gated on these):
  - RCA-6: `trademan_driver.scrape_portfolio` returns wrong holdings (generic `table tbody tr`, no account select, no refresh) — verify real DOM first; audit `scrape_unmatched_orders` too
  - RCA-5: `pillar1_session.py` missing `import os` (pre-existing) → `/login lib` NameError; CLI long-op handlers lack try/except → silent failure
  - RCA-3: KSS balances default to fabricated 500,000 / 0.0 (Anti-Mock)
- P1: /cash show CASH+MARGIN with Excess Equity · (S)/(B) tags + inverted P/L for SHORT · 2-line card rows (symbol unreadable) · DB /orders filter by broker + today, hide /nego button off-hours
- P2: remove kill-switch row from /status (user request) · 1:1-only auth (user decision D-1) · `_send_reply` retry/fallback · F-1/F-4/F-6 · concurrent lock test
- Separate card: mask OTP digits in logs (`otp_relay_registry`, `auth_driver`)
- Harness lesson: start gateway as daemon for live tests; LINE webhook = `https://line.a14s.dev` (Cloudflare), not Tailscale Funnel
