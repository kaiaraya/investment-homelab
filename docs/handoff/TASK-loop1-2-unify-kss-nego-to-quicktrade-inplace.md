# TASK-loop1-2: รวม /nego kss → QuickTrade in-place (เลิก Cancel+Replace) + Guardrails G4/G5

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Krungsri (KSS · QuickTrade Native In-Place Change · MARGIN 3024959)
- Status: DRAFT
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
| 1 | เพิ่ม `MAX_TICKS_EXCEEDED` + G4/G5 ใน `plan_negotiation` | ราคาห่างเกิน 3 tick → outcome `MAX_TICKS_EXCEEDED` | `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py -q` | ✅ 29 passed |
| 2 | เพิ่ม `quicktrade_driver.list_open_orders()` | คืนออเดอร์ค้าง MARGIN จาก `#orderBodyEq` | `.venv/bin/python -m pytest tests/test_quicktrade_driver.py -q` | ✅ 22 passed |
| 3 | เปลี่ยน `_broker_modify` (kss) → quicktrade in-place | ไม่มีการเรียก `modify_order_price` ในเส้น LIVE | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ 73 passed |
| 4 | รวม `/negotiate` เป็น alias ของ `/nego kss` | มีเส้นทางเดียว ไม่มีโค้ดซ้ำ | `.venv/bin/python -m pytest tests/test_line_cli_parser.py tests/test_line_cli_flow.py -q` | ✅ passed |
| 5 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py` | ✅ PASS (124 targeted, compileall OK) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py tests/test_quicktrade_driver.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่เด็ดขาด** — เฉพาะ `amend_price` (in-place) เท่านั้น · ห้ามใช้ Cancel+Replace
- ห้ามยิง SMS OTP · ห้าม restart gateway · ห้ามแก้ selectors ของ LIB (การ์ด 3)
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit test / mock เท่านั้น)

---

## Cline Report
- Files changed (worktree `d6c3e`, 2026-10-15):
  - `app/services/quicktrade_negotiation_service.py` — `NegotiationOutcome` +`MAX_TICKS_EXCEEDED`(G5)/`INVALID_TICK_SIZE`(G4); new pure `tick_distance()` (counts SET ticks, `None` = fail-closed, never guesses) + `_to_float`; `plan_negotiation(order, quote, *, max_ticks=None)` applies G4 (`validator.validate_tick_size`) then G5 (`LINE_NEGO_MAX_TICKS`, reason carries the tick count); `negotiate_order_price()` pins `account_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN` (3024959) and now mirrors the reason for **every** fail-closed outcome (not just `UPTICK_VIOLATION`).
  - `app/brokers/krungsri/quicktrade_driver.py` — new read-only `list_open_orders(account_no=None)` (MARGIN `#orderBodyEq`, session reuse, returns `success`/`account_no`/`selected_account`/`orders`) + pure `filter_open_orders()` (`balance > 0`, not cancelled/matched, tags the account); module docstring updated.
  - `app/services/line_cli/handlers.py` — `_broker_open_orders("kss")` now reads the Quick Trade ledger (`list_open_orders`), unreadable ledger ⇒ `RuntimeError` (honest error, never an empty queue); `_broker_modify(..., current_price=None)` LIVE `kss` → `negotiate_order_price(..., price=current_price, balance=volume, execute=True)` (TradeMan `modify_order_price` gone from the LIVE route, TEST still uses the virtual dispatcher); `_handle_nego` routes `/nego kss <order_no>` into the new shared `_nego_quicktrade()` (single-order `negotiate_card` + `LINE_CLI_NEGO` audit) and keeps `nego_card` for the batch/symbol path; `_handle_negotiate()` reduced to a thin alias (G1/G2 + own lock key → `_nego_quicktrade`); help text updated (`/negotiate` = alias, KSS = in-place, G4/G5).
  - Tests: `tests/test_quicktrade_negotiation_policy.py` (G4/G5, `tick_distance`, pinned MARGIN account, G5 end-to-end), `tests/test_quicktrade_driver.py` (`filter_open_orders` ×3, `list_open_orders` happy-path with mock DOM + no-session fail-closed), `tests/test_line_cli_flow.py` (`/nego kss <no>` = Quick Trade flow, no `trademan.modify_order_price`, `/negotiate` alias parity, `MAX_TICKS_EXCEEDED` reported honestly, KSS ledger source, TEST-mode dispatch unchanged). No `verify_changes.py` change needed (the 3 modules were already mapped).
  - Docs (zero-contradiction, report-only): `learned_workflows/krungsri/quicktrade_native_change_order.md` (§4 rows + new §4.5 Before/After) · `rca/krungsri/rca_krungsri_quicktrade.md` (new `KSS-QT-RCA-004` + surface list).
- Summary: the KSS in-place path is now a single route — `/nego kss <order_no>` (single-order card) and `/nego kss` / `/nego kss SYMBOL` (batch card over the Quick Trade ledger), with `/negotiate <order_no>` as a thin alias; the LIVE amendment always goes through Quick Trade `Change Price& Volume` (`negotiate_order_price`), and G4/G5 live in the policy so every caller (LINE + REST) gets them. No new order, no cancel+replace, no SMS OTP, no gateway restart, no LIB selector touched; no browser was launched (unit/mock only).
- Tests run + result: `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py` → **PASS** (`124 passed`, `compileall OK`, ~34s). Per-unit: policy `29 passed` · driver `22 passed` · LINE flow `73 passed`.
- Open questions:
  1. `cards._NEGOTIATE_OUTCOME` has no key for `MAX_TICKS_EXCEEDED` / `INVALID_TICK_SIZE`, so the card shows the fallback (ℹ️ + raw outcome label, reason line still printed). `cards.py` is outside this card's scope — add the Thai labels in a follow-up (runbook §4.5 note).
  2. `plan_negotiation` G6 still uses the policy's `max(Offer1, Last)` rule; `validator.validate_short_uptick` is stricter (rejects `price == last`, no zero-plus tick). Left untouched (out of scope) — if a short is amended exactly to `LastPrice` the broker may still reject it.
  3. `/nego kss` (batch) plans with the TradeMan quote (`_broker_quote("kss")`) while the single-order route uses the Quick Trade quote — two quote sources inside KSS. Not in this card's scope; worth unifying in the next loop.
  4. `_broker_open_orders("kss")` now needs a live Quick Trade session; if `data/session_state.json` is stale the batch command reports an error instead of silently doing nothing (intended, Anti-Mock) — verify on the next live window.
  5. Live items stay with card 4: DRY-RUN `amend_price` probe + LIVE `/nego kss 11008198` card (runbook §4.4).
  6. This worktree did not contain the handoff file (it is untracked in the primary checkout), so this report was written into the primary copy at `Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-loop1-2-…md`.

---

## Cline Verification & Stepwise Approval
- [ ] Stage A (Code Audit) · [ ] Stage B (Verify) · [ ] Stage C (Visual/HITL) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS / CHANGES_REQUESTED

---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
