# TASK-loop1-3: Liberator — Quote ตรงตัว + /nego lib Hardening (Fail-Closed)

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Liberator WebTrade (LIB · CASH)
- Status: DRAFT
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
| 1 | `get_market_bid_offer` fail-closed | อ่าน DOM ไม่ได้ → `QUOTE_UNAVAILABLE` ไม่คืนราคาเดา | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ✅ PASS (25) |
| 2 | `change_order` ยืนยัน symbol | symbol ไม่ตรง → ไม่กด + error | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ✅ PASS (29) |
| 3 | `_broker_modify` (lib) fail-closed | ไม่มีราคา/ไม่ตรง → `unavailable_card` | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ PASS (87) |
| 4 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py …` | ✅ PASS (164) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_liberator_change_order.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** · ห้ามแตะ KSS/QuickTrade (การ์ด 2) · ห้ามยิง SMS OTP · ห้าม restart gateway
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit/mock เท่านั้น)

---

## Cline Report
- Files changed:
  - `app/brokers/liberator/driver.py` — `_unknown_quote` → `_quote_unavailable` + `LiberatorDriver.QUOTE_UNAVAILABLE`; `get_market_bid_offer` now returns `{success,status,…}` (success=`OK`/`liberator_board`, failure=`QUOTE_UNAVAILABLE`/`unavailable`/`error`) on all 4 failure paths (blank symbol, no page, read exception, depth table not found); `change_order(..., expected_symbol=None)`; `_amend_order_in_place` verifies the live row symbol **before** the Change control (`SYMBOL_MISMATCH`, 0 clicks); `negotiate_price` passes `expected_symbol=ord_symbol`.
  - `app/brokers/liberator/plugin.py` — `change_order(..., symbol=None)` passthrough → `expected_symbol`; `get_market_bid_offer` docstring = new contract.
  - `app/services/line_cli/handlers.py` — `_NEGO_HALT_STATUSES`; `_plan_nego` also fails closed on `success=False`; `_broker_modify` LIB/LIVE gate (quote unreadable / quote-symbol ≠ order symbol / needed side empty → `QUOTE_UNAVAILABLE`, driver never called, symbol handed down); `_handle_nego` breaks the batch on a halt and pushes `cards.unavailable_card()` instead of `nego_card` (+ `halted`/`halt_status` in the result dict).
  - `tests/test_liberator_change_order.py` (+11 tests), `tests/test_line_cli_flow.py` (+8 tests).
  - Docs (zero-contradiction): `learned_workflows/liberator/liberator_portfolio.md` §8, `rca/liberator/rca_liberator.md` (`LIB-RCA-019`).
- Summary: LIB quote is now either a proven board reading or an explicit `QUOTE_UNAVAILABLE` envelope (no sentinel that still looks like a quote); `/nego lib` verifies the order's identity + price basis twice (plan-time and again at amend-time, LIVE) and, on any unproven basis, presses nothing, stops the batch and reports honestly with the “อ่านไม่ได้” card. No order-placing path was touched; KSS/QuickTrade untouched.
- Tests run + result:
  - `pytest tests/test_liberator_change_order.py -q` → **31 passed** (unit 1+2+3)
  - `pytest tests/test_line_cli_flow.py -q` → **87 passed** (unit 4)
  - `scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py` → **PASS** (compileall OK, 164 targeted tests passed, exit 0)
- Open questions:
  1. 2 doc files were updated despite not being in the 5-file scope — mandated by Zero-Contradiction (old text documented `_unknown_quote`). Revert if you want docs in a separate commit.
  2. `_broker_modify` LIB/LIVE adds one extra board read per amended order (second gate). Accepted for fail-closed; revisit if the LIB board read is slow.
  3. Out of scope, still fail-open: `app/mcp/pillars/pillar6_strategy.py:64-66` and `app/services/price_negotiation_service.py:89+` do `quote.get("bid_1") or order_price` — with the new envelope they now receive `None` and still fall back to the order's own price. Suggest a follow-up card.
  4. LIB depth-table selector wording is still not live-verified (pre-existing); after this change an unverified selector surfaces as `QUOTE_UNAVAILABLE` (honest) instead of a bogus quote. Live proof belongs to TASK-loop1-4.
  5. Batch halt = whole batch stops (by design). Remaining orders are not listed as “skipped” on the card — confirm whether you want an explicit “ยกเลิกที่เหลือ N รายการ” line.

---

## Cline Verification & Stepwise Approval
- [x] Stage A (Code Audit) · [x] Stage B (Verify) · [ ] Stage C (Visual/HITL — TASK-loop1-4) · [ ] Stage D (Verdict + Merge)
- Verdict: PASS (unit/mock) — CHANGES_REQUESTED only for the 2 doc files if you want them dropped

---

## Argon Analysis
- Direction verdict: ...
- Next loop focus: ...
