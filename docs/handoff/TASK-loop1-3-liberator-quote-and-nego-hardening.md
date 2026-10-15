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
| 1 | `get_market_bid_offer` fail-closed | อ่าน DOM ไม่ได้ → `QUOTE_UNAVAILABLE` ไม่คืนราคาเดา | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 2 | `change_order` ยืนยัน symbol | symbol ไม่ตรง → ไม่กด + error | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ⬜ |
| 3 | `_broker_modify` (lib) fail-closed | ไม่มีราคา/ไม่ตรง → `unavailable_card` | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 4 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_liberator_change_order.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** · ห้ามแตะ KSS/QuickTrade (การ์ด 2) · ห้ามยิง SMS OTP · ห้าม restart gateway
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit/mock เท่านั้น)

---

## Cline Report
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
