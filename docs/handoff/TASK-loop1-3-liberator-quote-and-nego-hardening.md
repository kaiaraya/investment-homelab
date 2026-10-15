# TASK-loop1-3: Liberator — Quote ตรงตัว + /nego lib Hardening (Fail-Closed)

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Liberator WebTrade (LIB · CASH)
- Status: DRAFT
- Run mode: HYBRID — โค้ด+unit = HEADLESS (Kanban card `045ac`) · live quote = INTERACTIVE (ห้อง Antigravity)
- Depends on: TASK-loop1-1
- Unblocks: TASK-loop1-4
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D2 (lib), D3, D4 (lib)
- Verify: `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §2 Pillar 3 ข้อ 3.3/3.4 — LIB ต้องยืนยันราคา bid/offer จากหน้าจอจริง และ `/nego lib` ต้อง fail-closed เมื่อ symbol ไม่ตรง/อ่านราคาไม่ได้ (ห้ามเดา)

## Context
- `get_market_bid_offer` (driver L766) ยังมีเส้นทาง `_unknown_quote` (L751) ที่คืนราคา default/เดาเมื่ออ่าน DOM ไม่ได้ → เสี่ยงต่อการแก้ออเดอร์ด้วยราคาผิด (Anti-Mock)
- `/nego lib` ยังไม่ยืนยันว่า symbol ที่ขอ ตรงกับออเดอร์ที่เลือกจริง ก่อนกด Change Order → อาจแก้ผิดตัว
- ยังไม่มี unit test คุมพฤติกรรม fail-closed

อ้างอิง RCA: `rca/liberator/` (ถ้ามี LIB-RCA ที่เกี่ยวข้อง)

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/brokers/liberator/driver.py`
- `app/brokers/liberator/plugin.py`
- `app/services/line_cli/handlers.py`
- `tests/test_liberator_change_order.py`, `tests/test_line_cli_flow.py`

## Context map
| File | Symbol / Lines | Why |
|---|---|---|
| `app/brokers/liberator/driver.py` | `_unknown_quote` L751 · `get_market_bid_offer` L766–… | edit: อ่าน DOM ไม่ได้ → `raise` หรือคืน `{"success": False, "status": "QUOTE_UNAVAILABLE"}` แทนการเดาราคา |
| 〃 | `change_order` L1214–… | edit: ยืนยัน symbol ก่อนกดเปลี่ยนราคา (fail-closed ถ้าไม่ตรง) |
| `app/brokers/liberator/plugin.py` | `change_order` L263 · `get_market_bid_offer` L291 | edit: ส่งผ่าน status ใหม่ + map error ให้ถูกต้อง |
| `app/services/line_cli/handlers.py` | `_broker_modify` branch `lib` | edit: ถ้า quote ไม่ได้ / symbol ไม่ตรง → `cards.unavailable_card()` + หยุด (ห้ามกด) |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | `get_market_bid_offer` fail-closed | อ่าน DOM ไม่ได้ → `QUOTE_UNAVAILABLE` ไม่คืนราคาเดา | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 2 | `change_order` ยืนยัน symbol | symbol ไม่ตรง → ไม่กด + error | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 3 | `_broker_modify` (lib) fail-closed | ไม่มีราคา/ไม่ตรง → `unavailable_card` | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 4 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py …` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_liberator_change_order.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** · ห้ามแตะ KSS/QuickTrade (การ์ด 2) · ห้ามยิง SMS OTP · ห้าม restart gateway
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit/mock เท่านั้น)

---

## Cline Report
- Git Commit(s): `TASK-loop1-N: <type>(<scope>): <summary>`
- Files changed:
- Summary:
- Tests run + result:
- Open questions:
---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED
---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...

---

## Session carry-over (from the TASK-loop1-2 session, 2026-10-15)

**Start here (new session)**: read this file + the files in its Context map only. Run mode = interactive
(`stepwise-approval`), one atomic step per turn, `verify_changes.py` after every step, `--full` once at close.

**Prerequisites now on `main` (TASK-loop1-2, card `2b7ff`)**
- `/nego kss` = `/negotiate` = **one** path (`handlers._handle_nego`); the LIVE `kss` amendment goes in place through
  `negotiate_order_price()` (SAC red line: `trademan_driver.modify_order_price` must stay unreachable from `/nego`).
- `quicktrade_negotiation_service.plan_negotiation()` owns G4/G5/G6 and returns the enum
  `OK / NO_CHANGE / UPTICK_VIOLATION / **TICK_SIZE_VIOLATION** / **MAX_TICKS_EXCEEDED** / NO_QUOTE / UNSUPPORTED_SIDE`
  (every refusal clears `target_price` and sets `error`).
- `quicktrade_driver.list_open_orders()` + `pending_orders()` read the `#orderBodyEq` ledger (MARGIN first).
- Handler seams to reuse: `_broker_open_orders(broker)`, `_broker_modify(broker, …)` (kss branch returns
  `path="QUICKTRADE_INPLACE"`), `_apply_quicktrade_result(row, res)` (service outcome → card row: refusal/NO_CHANGE =
  `skip`, DRY-RUN labelled). `/nego lib` still runs the **old** preview path (`_plan_nego` → `_broker_modify` →
  `liberator_plugin.change_order`) — that is exactly what this card hardens.

**Carry-over questions that touch this card**
1. `_plan_nego` is now only a preview for `kss` but the real path for `lib` → decide whether LIB also gets a
   service-level policy, or document why the preview stays authoritative for LIB (avoid two drifting policies).
2. Strict SHORT uptick (target == `LastPrice` refused) is applied for kss since 2026-10-15; LIB's `/nego lib` must
   not silently use the looser rule — check `_plan_nego`'s G6 for the lib path in Step 3.
3. `/negotiate` returns `{"status": "CLI_NEGO", "order_no", "ok", "skipped", "failed"}` now (the old `outcome` key is
   gone) — keep the test file consistent when touching `tests/test_line_cli_flow.py`.

**Test-harness gotchas (learned the hard way)**
- `tests/test_line_cli_flow.py` has an **autouse** `_broker_edges` fixture that stubs `_broker_open_orders` /
  `_broker_modify` / `_broker_quote`; a test that must exercise the routing has to restore the real function
  (`REAL_BROKER_OPEN_ORDERS` / `REAL_BROKER_MODIFY` are captured at module import — same pattern as `REAL_LIVE_CARD`).
- `--full` (verify_changes.py) lets the annealing tests overwrite the tracked
  `learned_workflows/click2win/click2win_order_submit.md` and `learned_workflows/shared/test_anneal_wf.md`
  (open item F-11 "Self-Annealed ×75"). After every `--full`, `git checkout --` those two files.

**Out of scope reminders**: no KSS/QuickTrade edits, no new orders, no OTP/login, no gateway restart, no LIVE calls
(live quote evidence belongs to `TASK-loop1-4`). Close with `TASK-loop1-3: <type>(<scope>): <summary>` commits on
`main` (same convention as `TASK-loop1-2`).
