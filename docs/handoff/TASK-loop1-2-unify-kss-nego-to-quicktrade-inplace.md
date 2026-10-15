# TASK-loop1-2: รวม /nego kss → QuickTrade in-place (เลิก Cancel+Replace) + Guardrails G4/G5

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Krungsri (KSS · QuickTrade Native In-Place Change · MARGIN 3024959)
- Status: DRAFT
- Run mode: HYBRID — โค้ด+unit = HEADLESS (Kanban card `2b7ff`) · live amend = INTERACTIVE (ห้อง Antigravity)
- Depends on: TASK-loop1-1
- Unblocks: TASK-loop1-4
- Supersedes: `TASK-cli-p3-unified-nego-and-orders-visibility.md`
- Closes Acceptance (`loop_acceptance_and_tasks.md` §1): D1, D2 (kss), D4 (kss)
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`

## Directive delta (Argon — PHASE 0)
อ้างอิง `directive/master_directive_v2.md` §2 Pillar 3 ข้อ 3.3 (In-Place Change เท่านั้น) — จุดวิกฤต D1: เส้นทาง LIVE ของ `/nego kss` ยังเรียก Cancel+Replace ต้องเปลี่ยนเป็น QuickTrade in-place

## Context
**หัวใจของ Loop 1** — ณ ปัจจุบันมี 2 เส้นทางซ้อนกัน และเส้นทางหลักผิดกฎ:
- `/nego kss` → `_handle_nego` (L801) → `_plan_nego` (L759, มี G4–G6) → `_broker_modify` (L159) → **`trademan_driver.modify_order_price` = Cancel+Replace (ผิดกฎเหล็ก D1)**
- `/negotiate <order_no>` → `_handle_negotiate` (L882) → `quicktrade_negotiation_service.negotiate_order_price` (L146, in-place ถูกต้อง แต่ยังขาด G4/G5 ในชั้น policy)

งานนี้: รวม 2 เส้นทางเป็นหนึ่งเดียวให้ `/nego kss [SYMBOL|order_no]` วิ่งเข้า QuickTrade in-place + ทำ `/negotiate` เป็น alias + เติม G4/G5 ลง `plan_negotiation`

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/quicktrade_negotiation_service.py`
- `app/brokers/krungsri/quicktrade_driver.py`
- `app/services/line_cli/handlers.py`
- `tests/test_quicktrade_negotiation_policy.py`, `tests/test_quicktrade_driver.py`, `tests/test_line_cli_flow.py`
- `scripts/verify_changes.py` (`MODULE_TEST_MAP` ถ้ามีไฟล์/เทสต์ใหม่)

## Context map
| File | Symbol / Lines | Why |
|---|---|---|
| `app/services/quicktrade_negotiation_service.py` | `NegotiationOutcome` L33 | edit: เพิ่ม `MAX_TICKS_EXCEEDED = "MAX_TICKS_EXCEEDED"` |
| 〃 | `plan_negotiation` L128–141 | edit: เติม G4 (`validator.validate_tick_size(new)[0]`) + G5 (`|new-old|` ≤ `settings.LINE_NEGO_MAX_TICKS`) — เกิน → `MAX_TICKS_EXCEEDED` + เหตุผลว่าห่างกี่ tick |
| 〃 | `negotiate_order_price` L146–239 | edit: ล็อกบัญชี `settings.TRADEMAN_ACCOUNT_NO_MARGIN` (3024959) |
| `app/brokers/krungsri/quicktrade_driver.py` | `amend_price` L438 · `candidate_accounts` L399 | read: กลไกกด Change Price&Volume; ใช้ candidate accounts |
| 〃 | `list_open_orders` (**ยังไม่มี — ต้องเพิ่ม**) | new: ดึงออเดอร์ค้าง (`balance > 0`) จากตาราง `#orderBodyEq` ของบัญชี Margin (รองรับ `/nego kss` / `/nego kss PTT`) |
| `app/services/line_cli/handlers.py` | `_broker_modify` L159–181 | edit: branch `kss` (L174-179) เลิกเรียก `trademan_driver.modify_order_price` → เรียก `quicktrade_negotiation_service.negotiate_order_price` |
| 〃 | `_handle_nego` L801–876 | edit: ให้ `/nego kss [...]` วิ่ง QuickTrade; target = order_no เดียว → `cards.negotiate_card`, batch → `cards.nego_card` |
| 〃 | `_handle_negotiate` L882–… | edit: ทำเป็น alias → เรียก flow เดียวกับ `/nego kss <order_no>` (ลบโค้ดซ้ำ) |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | เพิ่ม `MAX_TICKS_EXCEEDED` + G4/G5 ใน `plan_negotiation` | ราคาห่างเกิน 3 tick → outcome `MAX_TICKS_EXCEEDED` | `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py -q` | ⬜ |
| 2 | เพิ่ม `quicktrade_driver.list_open_orders()` | คืนออเดอร์ค้าง MARGIN จาก `#orderBodyEq` | `.venv/bin/python -m pytest tests/test_quicktrade_driver.py -q` | ⬜ |
| 3 | เปลี่ยน `_broker_modify` (kss) → quicktrade in-place | ไม่มีการเรียก `modify_order_price` ในเส้น LIVE | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 4 | รวม `/negotiate` เป็น alias ของ `/nego kss` | มีเส้นทางเดียว ไม่มีโค้ดซ้ำ | `.venv/bin/python -m pytest tests/test_line_cli_parser.py tests/test_line_cli_flow.py -q` | ⬜ |
| 5 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py tests/test_quicktrade_driver.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่เด็ดขาด** — เฉพาะ `amend_price` (in-place) เท่านั้น · ห้ามใช้ Cancel+Replace
- ห้ามยิง SMS OTP · ห้าม restart gateway · ห้ามแก้ selectors ของ LIB (การ์ด 3)
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit test / mock เท่านั้น)

---

## Cline Report
- Git Commit(s): `d7bde41` (`TASK-loop1-2: fix(nego)…` — code + tests) · the follow-up `TASK-loop1-2: docs(rca)…` commit on `main` (2026-10-15)
  (a self-referencing hash is deliberately avoided — the docs commit carries its own message)
- Files changed:
  - `app/services/quicktrade_negotiation_service.py` — `plan_negotiation()` now enforces **G4**
    (`validate_tick_size` → `TICK_SIZE_VIOLATION`), **G5** (`tick_distance_exceeds()` ≤
    `settings.LINE_NEGO_MAX_TICKS` → `MAX_TICKS_EXCEEDED`, reason states the tick count) and **G6**
    (`validate_short_uptick`, strict → `UPTICK_VIOLATION`); new enum values + shared helpers
    `tick_distance()` / `tick_distance_exceeds()`; every refusal clears `target_price` and sets `error`;
    `max_ticks` is injectable.
  - `app/brokers/krungsri/quicktrade_driver.py` — new `list_open_orders(account_no=None, symbol=None)` (read-only
    `#orderBodyEq`, MARGIN first, same session/lock/launch path as `get_order`) + `pending_orders()` filter
    (`balance > 0`, exact symbol, unparsed balance dropped).
  - `app/services/line_cli/handlers.py` — kss discovery = Quick Trade ledger (raises on an unreadable ledger);
    LIVE `kss` `_broker_modify` → `negotiate_order_price()` tagged `path="QUICKTRADE_INPLACE"` (cancel+replace is
    unreachable); `_apply_quicktrade_result()` folds the service result into the card row; `_handle_nego` picks
    `cards.negotiate_card` (one explicit order_no) or `cards.nego_card` (batch) and counts skip/ok/fail from the row;
    `_handle_negotiate` is a 2-line alias of `/nego kss`; help texts updated.
  - Tests: `tests/test_quicktrade_negotiation_policy.py` (+6), `tests/test_quicktrade_driver.py` (+4),
    `tests/test_line_cli_flow.py` (+5, 3 `/negotiate` tests rewritten for the alias).
  - Docs: `rca/krungsri/rca_krungsri_quicktrade.md` (KSS-QT-RCA-004),
    `learned_workflows/krungsri/quicktrade_native_change_order.md` (§3 invariant 1, §4 rows, new §5).
- Summary: `/nego kss` and `/negotiate` are one path now, both amending in place on the same Settrade order number
  through Quick Trade; G4/G5/G6 live in the service (single source of truth) and the card/audit report the service's
  own numbers (Anti-Mock). Order discovery moved to the platform that is actually amended. No real order was
  touched: all work is unit/mock only, no OTP, no login, no gateway restart, no LIB selectors.
- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`
    → **PASS (targeted 125 tests, compileall OK)**
  - `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py tests/test_quicktrade_driver.py tests/test_line_cli_flow.py -q --tb=line` → **125 passed**
  - `--full` suite deliberately **not** run per step (run once at task close).
- Open questions:
  1. **Strict SHORT uptick** (a target equal to `LastPrice` is refused, not just a down-tick) was applied on the
     user's decision 2026-10-15; the broker's own behaviour at exact equality is still unverified → witness in
     `TASK-loop1-4`.
  2. `_plan_nego` is now a *preview* for `kss` and stays the real path for `lib` — `TASK-loop1-3` should decide
     whether LIB gets a service-level policy too (two previews must not drift).
  3. `/negotiate`'s return shape changed to `{"status": "CLI_NEGO", "order_no", "ok", "skipped", "failed"}` (the
     `outcome` key is gone). Any external consumer of the old shape must be updated.
  4. TEST-mode `/nego kss` now reads the Quick Trade ledger instead of the TradeMan portfolio screen — intended
     (one source of truth), but it does need a live session to be exercised → `TASK-loop1-4`.
  5. LIVE + `DRY_RUN_MODE=True` can still show a LIVE header while nothing was sent (pre-existing); the row reason
     now says `DRY-RUN — ยังไม่กดส่ง` — worth aligning with the dispatcher's mode flag in a later card.
---

## Cline Verification & Stepwise Approval
- [x] Stage A (Code Audit) · [x] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: **PASS (code + unit)** — Stage A: diff audited against the allowed scope (3 source files + 3 test files
  + the two broker docs), invariants held (Anti-Mock: refusals are skips and `submitted` is never inferred from
  `success`; Zero-OTP: no login/SMS path touched; Uptick: strict G6 added, not weakened; Broker isolation: LIB
  untouched) · Stage B: `verify_changes.py` PASS 125 targeted + compileall OK.
- Stage C (live witness) and Stage D (commit/merge = human gate #2) are **open** — live evidence is deliberately
  deferred to `TASK-loop1-4` (no order was placed or amended).
---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
