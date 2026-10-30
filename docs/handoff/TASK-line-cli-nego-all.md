# TASK-line-cli-nego-all: add `/nego all` (ต่อราคาทั้ง 2 โบรกเกอร์)

- Created: 2026-10-28 by Hermes `default` (planner lane)
- Loop: LINE CLI reshape · Kanban card: `t_ee9bd654`
- Lane: `homelab-build` · Tier: 🟡 T1 · Model: `gemini-3.1-pro` (provider `antigravity-subscription-directsdk`)
- Broker: kss + lib (amend via existing broker-routed path) · Probe: NONE (reuses `_scrape_nego_orders` + `_broker_modify`/`_kss_cancel_replace`)
- Branch: `task/line-cli-nego-all` (off `main`, AFTER `task/line-cli-sync` merged) · human squash → `main` = gate #2
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py`

## Context (planner)
`/nego <broker> [SYM|เลข]` already amends all unmatched orders of one broker. Add `broker="all"`: scrape unmatched orders from BOTH brokers via `_scrape_nego_orders()` (already normalized with a `broker` tag), then amend each in place through the same broker-routed path the single-broker flow uses. Keep every existing guardrail (kill-switch, `LINE_NEGO_WINDOWS`, alive session, SET tick size, `LINE_NEGO_MAX_TICKS`=3, strict short uptick) untouched. This is a pure refactor + one `all` branch — the amend logic must not change.

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/handlers.py`
- `tests/test_line_cli_flow.py` (add cases)
- `tests/test_line_cli_nego_menu.py` (add/confirm cases)

## Context map (grep anchors)
| File | Symbol | Why |
|------|--------|-----|
| `app/services/line_cli/handlers.py` | `_handle_nego` (the `for o in orders:` amend loop) | extract `_amend_one`; add `all` branch |
| `app/services/line_cli/handlers.py` | `_scrape_nego_orders` | returns both brokers, tagged `broker` |
| `app/services/line_cli/handlers.py` | `_broker_open_orders`, `_plan_nego`, `_broker_modify`, `_kss_cancel_replace`, `_apply_quicktrade_result`, `_apply_cancel_replace_result`, `_NEGO_HALT_STATUSES`, `_audit_nego`, `_broker_session_alive`, `BROKER_LABEL` | reuse |
| `app/core/config.py` | `KSS_AMEND_MODE`, `LINE_NEGO_CDP_GATE`, `LINE_NEGO_MAX_TICKS` | read settings (do not change) |
| `tests/test_line_cli_nego_menu.py` | existing nego tests | pattern to copy |

## Steps / Task Decomposition (atomic)

1. **handlers.py** — extract the per-order amend body (currently inlined in `_handle_nego`'s loop) into a new helper placed right before `_handle_nego`:
   ```python
   async def _amend_one(broker: str, o: Dict[str, Any], max_ticks: int) -> Tuple[Dict[str, Any], bool]:
       # returns (row, halted); kss → _kss_cancel_replace or _broker_modify(quicktrade) per KSS_AMEND_MODE;
       # lib → _plan_nego then _broker_modify, halted=True when status in _NEGO_HALT_STATUSES
   ```
   Move the existing kss/lib logic verbatim (do NOT change the amend logic). `_handle_nego`'s loop becomes `row, halted = await _amend_one(broker, o, max_ticks)` plus the existing count/append/`_audit_nego`/halt-break tail.
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_flow.py -k nego tests/test_line_cli_nego_menu.py -q` (existing single-broker nego tests still green — proves the refactor is behaviour-preserving).

2. **handlers.py** — add the `broker == "all"` branch at the top of the order-gathering section: `orders = await _scrape_nego_orders()`; if empty → "ℹ️ ไม่มีออเดอร์ค้าง (ยังไม่ match) ทั้ง 2 โบรกเกอร์". Per-broker G3 gate: for `b in ("kss","lib")`, if session not alive → drop those orders from the list and report "🔴 <labels> session หลุด — ต่อราคาเฉพาะ broker ที่เปิด CDP อยู่". Use `label = "ALL"`. In the loop, resolve each order's broker via `o["broker"]` and pass it to `_amend_one` and `_audit_nego`.

3. **handlers.py** — make the result card push use `label` (so the `all` case renders "ALL" instead of a single broker label). No card API change otherwise.

4. **tests** — add to `tests/test_line_cli_flow.py`: `test_nego_all_scrapes_both_and_amends_each` (monkeypatch `_scrape_nego_orders` → 2 orders tagged kss+lib; spy `_amend_one`; assert called once per order with the order's own broker), `test_nego_all_skips_down_broker` (lib session False → lib order dropped, kss order amended). Add a direct `_amend_one` unit test asserting the kss path (calls `_broker_modify`/`_kss_cancel_replace`) vs the lib path (calls `_plan_nego` + `_broker_modify`).
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_flow.py tests/test_line_cli_nego_menu.py -q`

## Acceptance / Done when
- `.venv/bin/python -m pytest tests/test_line_cli_flow.py tests/test_line_cli_nego_menu.py -q` → green (targeted only, NO full suite).
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py` → PASS.
- `/nego all` parses to `CliCommand(cmd="nego", broker="all")` (add/confirm a parser assertion) and dispatches into the new branch.
- Existing single-broker nego behaviour unchanged (tests green before AND after).
- Committed to `task/line-cli-nego-all` (never `main`, never `git add -A`). Commit msg: `TASK-line-cli-nego-all: feat(line_cli): /nego all across both brokers`.

## Out of scope / ห้ามแตะ
- Amend guardrails (max ticks, uptick, windows, kill-switch) — behaviour-preserving only.
- Live witness (🔴 T2, separate card, human at screen).
- `/sync`, `/login` retirement (separate cards). Settrade Streaming drivers.

## Worker contract (บังคับ)
- Targeted test only. Fail-closed. Commit to `task/line-cli-nego-all` off `main`; stage ONLY your files; never `git add -A`; never `main`.
- Fill `## Worker Report` before done. Note any open question as a NEW `--triage` card, never scope-widening.
