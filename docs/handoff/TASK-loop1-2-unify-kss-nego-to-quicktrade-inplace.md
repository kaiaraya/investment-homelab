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
