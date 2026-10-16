# TASK-sq1: Unify /nego Policy & Add DRY-RUN Badge

- Created: 2026-10-16 by Argon (Complex Task Owner · Antigravity)
- Loop: 1  (board: `docs/board/loop_board.md` — Section 6 Side-Quests)
- Broker: Shared (`kss` QuickTrade + `lib` WebTrade)
- Tier: 🟡 T1
- Implementer: JULES (`Gemini 3.1 Pro`)
- Pre-Coding Probe: NONE  (pure python policy + card badge logic; no DOM scraping needed)
- Git Branch: `task/sq1-nego-policy-and-dryrun-badge`
- Status: READY
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/quicktrade_negotiation_service.py`

## Directive delta (Argon เขียน — STEP 0)
อ้างอิง `directive/master_directive_v2.md` §2 Pillar 3 (Guardrails G1–G6) และ Open questions ข้อ 2 และข้อ 5 จาก `TASK-loop1-2`:
1. รวม policy ตรวจสอบ tick size (G4), max tick distance (G5), และ short uptick (G6) ระหว่าง `handlers._plan_nego` กับ `quicktrade_negotiation_service.plan_negotiation` ให้เป็น Single Source of Truth
2. เมื่อ `settings.DRY_RUN_MODE` เป็น `True` (แม้ `TRADING_MODE="LIVE"`) ป้ายหัวการ์ดใน `cards.nego_card()` และ `cards.negotiate_card()` ต้องแสดงป้าย `"DRY-RUN"` อย่างชัดเจน (ห้ามปล่อยว่างให้เข้าใจผิดว่ายิงออเดอร์จริง)

## Context (Argon เขียน — STEP 0)
1. ใน `app/services/line_cli/handlers.py` ฟังก์ชัน `_plan_nego()` ยังมี copy ของการตรวจ tick distance และ uptick แยกต่างหาก ทำให้เสี่ยงต่อ policy drift กับ `quicktrade_negotiation_service.plan_negotiation()`
2. ใน `cards.nego_card()` และ `cards.negotiate_card()` ตัวแปร `is_test` ถูกคำนวณจาก `not trade_dispatcher.is_live` เพียงอย่างเดียว หากผู้ใช้ตั้ง `TRADING_MODE="LIVE"` แต่เปิด `DRY_RUN_MODE=True` หัวการ์ดจะไม่ขึ้นป้ายเตือนว่าเป็น DRY-RUN

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/handlers.py`
- `app/services/line_cli/cards.py`
- `app/services/quicktrade_negotiation_service.py`
- `tests/test_line_cli_flow.py`

## Context map
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `app/services/line_cli/cards.py` | `nego_card` L369 · `negotiate_card` L420 | edit: รองรับ `dry_run: bool = False` หรือแสดงป้าย `"DRY-RUN"` เมื่อ `dry_run` เป็น True |
| `app/services/line_cli/handlers.py` | `_plan_nego` L818-860 | edit: ใช้ helper / policy จาก `quicktrade_negotiation_service` สำหรับ tick distance และ uptick |
| `app/services/line_cli/handlers.py` | L984-1011 (card dispatch) | edit: ส่ง flag `dry_run=settings.DRY_RUN_MODE` เข้าการ์ด |
| `tests/test_line_cli_flow.py` | test_nego / test_negotiate | edit/add: เพิ่ม assertions ตรวจว่าเมื่อ `DRY_RUN_MODE=True` หัวการ์ดมีป้าย DRY-RUN |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | ปรับ `cards.nego_card` และ `cards.negotiate_card` | มี badge `"DRY-RUN"` เมื่อ `dry_run=True` (สี `#F59E0B` WARN_COLOR) | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 2 | ส่ง `dry_run=settings.DRY_RUN_MODE` จาก `handlers.py` | การ์ดแสดงป้าย DRY-RUN ถูกต้องตาม settings | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 3 | ปรับ `_plan_nego` ใน `handlers.py` ให้ใช้ validation เดียวกันกับ `plan_negotiation` | ไม่มี logic ซ้ำซ้อน / policy drift | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ⬜ |
| 4 | รัน verify_changes.py ครบทุกไฟล์ | PASS ทั้งหมด | `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/quicktrade_negotiation_service.py` | ⬜ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/quicktrade_negotiation_service.py`
- `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q`

## Out of scope / ห้ามแตะ
- ห้าม place order หรือยิง live HTTP ไปยัง broker จริง
- ห้ามแตะ credentials หรือ `.env`
- ห้ามแตะ driver ของ Liberator และ Krungsri QuickTrade ในส่วนการส่งคำสั่ง

---

## Jules Report (Jules เขียนบน Cloud VM — STEP 2a · Gemini 3.1 Pro)
- Git Commit(s):
- Files changed: `app/services/line_cli/cards.py`, `app/services/line_cli/handlers.py`, `tests/test_line_cli_flow.py`
- Summary: Refactored `_plan_nego` in `handlers.py` to use `quicktrade_negotiation_service.plan_negotiation` for centralized validation logic (tick size, distance, uptick rule). Updated `nego_card` and `negotiate_card` in `cards.py` to accept `dry_run: bool` and display a `DRY-RUN` badge with `#facc15` color. Supplied `dry_run=settings.DRY_RUN_MODE` from `handlers.py`. Removed `_tick_distance_exceeds` which is no longer needed. Updated tests to cover dry-run badges and modified exception text from centralized service.
- Tests run + result (Cloud VM): `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py app/services/line_cli/cards.py app/services/quicktrade_negotiation_service.py` -> 117 passed in 18.24s
- Open questions: None.

---

## Cline Triage Report (Cline plugin เขียนในเครื่อง — STEP 2b)
- Local Branch Checked:
- Invariant & Scope Audit:
- Local Verify Result:
- Triage Verdict & Summary for Argon:
