# Handoff to Hermes: Loop 2 Verification (`LOOP2-VERIFY`)

> **Task ID**: `LOOP2-VERIFY`  
> **Status**: `REVIEW`  
> **Board**: `kanban_board.csv` (Hermes 8-Status Model)  
> **Target Workspace**: `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab`  
> **Reference Plan**: [TASK-loop2-implementation-plan.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-loop2-implementation-plan.md)  
> **Auditor Handoff**: [sentinel_auditor/handoff.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/teamwork/sentinel_auditor/handoff.md)

---

## 1. Context Map & Scope

### Modified Core Files
- `app/api/v1/endpoints/webhook_line.py`: Fast HTTP 200 acknowledgment; sync bypass for OTP & emergency stops; background queue delegation.
- `app/services/line_cli/queue.py`: In-memory `AsyncCommandQueue` worker with per-command timeouts (30s / 180s) and push notifications.
- `app/services/line_cli/parser.py`: Value-based order parsing (`50k`, `100000b`, `30000฿`, detached `50,000 บาท`), `/sbl`, `/borrow`, `/return` aliases.
- `app/services/line_cli/handlers.py`:
  - Board lot sizing (multiples of 100 shares rounded down from live quotes).
  - SBL handlers (`_handle_sbl`, `_handle_sbl_borrow`, `_handle_sbl_return`).
  - Multi-lot FIFO deduction on return and aggregate inventory check on `/short`.
  - Fix double `reply_token` reuse bug in `handle_postback` (execution results now delivered via `push_message`).
- `app/services/line_cli/cards.py`: Flex message cards for SBL status, SBL pool, SBL borrow confirmation, and SBL return receipt.
- `app/services/line_cli/rich_menu.py`: 2x2 grid mobile Rich Menu specification and HTML template.
- `scripts/setup_rich_menu.py`: Headless Playwright script rendering pixel-perfect 2500x1686 PNG and provisioning to LINE OA.
- `app/brokers/krungsri/sbl_realtime_driver.py`: Production scraper and deterministic XD/XR risk hard-blocker (`check_symbol_risk`).

---

## 2. Guardrails & Safety Invariants Verified

1. **DRY_RUN_MODE**: Governs both trade orders and SBL operations. Simulated lots in SQLite DB (`sbl_borrow_lots`) never execute real broker transactions when `DRY_RUN_MODE=True`.
2. **Invariant 9 (OTP Relay Readiness)**: Never triggers full automated login or SMS OTP if relay readiness check returns false.
3. **Broker Isolation**: SBL operations strictly restricted to **Krungsri MARGIN 3024959**; rejected on Cash or Liberator accounts.
4. **Single-Use Reply Token**: Webhook and postback handlers never attempt second replies with an exhausted `reply_token`.
5. **Anti-Mock**: No fabricated balances, fills, or mock accounts reported as live success.

---

## 3. Verification Instructions for Hermes

### Command A: Fast Targeted Unit Test Suite (62 tests)
```bash
.venv/bin/python -m pytest \
    tests/test_line_async_queue.py \
    tests/test_line_cli_sbl.py \
    tests/test_line_cli_handlers_sbl.py \
    tests/test_line_cli_value_orders.py -q --tb=line
```
*Expected Result*: `62 passed in ~17s` (Exit code 0).

### Command B: Rich Menu Image & Spec Verification
```bash
.venv/bin/python scripts/setup_rich_menu.py --render-only
.venv/bin/python scripts/setup_rich_menu.py --dry-run
```
*Expected Result*: Renders 2500x1686 PNG to `data/rich_menu_2500x1686.png` (~1.7 MB) and simulates LINE API registration (Exit code 0).

### Command C: Full Change Verification via Gatekeeper Script
```bash
.venv/bin/python scripts/verify_changes.py \
    app/services/line_cli/parser.py \
    app/services/line_cli/handlers.py \
    app/services/line_cli/cards.py \
    app/services/line_cli/queue.py \
    app/services/line_cli/rich_menu.py \
    scripts/setup_rich_menu.py \
    app/brokers/krungsri/sbl_realtime_driver.py
```
*Expected Result*: `289 passed in ~79s` (Exit code 0).

### Command D: Check / Promote Kanban Task Status
To inspect the board:
```bash
python3 /home/araya-sawasdichai/.gemini/antigravity/scratch/agy-kanban-orchestrator/kanban_cli.py --sheet kanban_board.csv --mode status
```
To run targeted verification via Hermes orchestrator:
```bash
python3 /home/araya-sawasdichai/.gemini/antigravity/scratch/agy-kanban-orchestrator/kanban_cli.py --sheet kanban_board.csv --task LOOP2-VERIFY
```

---

## 4. Key Behavioral Edge Cases Resolved in Peer Review
- **Multi-Lot SBL FIFO Return**: If a user has borrowed 1,000 shares on Day 1 and 2,000 shares on Day 3, returning 1,500 shares correctly marks Lot 1 as `FULLY_RETURNED` and Lot 2 as `PARTIAL_RETURNED` with 1,500 remaining.
- **Aggregate Short Sizing**: SBL balance check sums `remaining_qty` across all active lots before permitting `/short`.
- **Detached Currency Formatting**: Correctly handles input with spacing before currency units (`/buy PTT 50k บาท` or `/buy PTT 50,000 ฿`).
- **XD/XR Hard-Block**: Immediately rejects `/borrow` and `/short` on symbols with active XD/XR dates in the SBL calendar (`is_blocked=True`).
