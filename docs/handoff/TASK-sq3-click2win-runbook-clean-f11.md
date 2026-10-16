# TASK-sq3: Click2Win Runbook Clean F-11

- Created: 2026-10-16 by Argon (Complex Task Owner · Antigravity)
- Loop: 1  (board: `docs/board/loop_board.md` — Section 6 Side-Quests)
- Broker: Settrade Click2Win (C2W)
- Tier: 🟢 T0
- Implementer: JULES (`Gemini 3.6 Flash`)
- Pre-Coding Probe: NONE  (pure markdown runbook text cleanup)
- Git Branch: `task/sq3-click2win-runbook-clean-f11`
- Status: READY
- Verify: `.venv/bin/python scripts/verify_changes.py tests/test_annealing_runbook_isolation.py learned_workflows/click2win/click2win_order_submit.md`

## Directive delta (Argon เขียน — STEP 0)
อ้างอิง `C2W-RCA-006` และ commit `28b3468`:
- ปัญหา test pollution (F-11) ก่อนหน้านี้ได้ถูกป้องกันแล้วด้วย test fixture isolation ใน `tests/conftest.py`
- การ์ดนี้มีหน้าที่เก็บตกทำความสะอาดไฟล์ `learned_workflows/click2win/click2win_order_submit.md` ที่เคยถูกเขียนข้อความ `(Self-Annealed: ...)` ซ้ำ 75 ครั้ง ให้กลับมาเป็นคำอธิบายกระชับ สะอาด และถูกต้อง

## Context (Argon เขียน — STEP 0)
ในไฟล์ `learned_workflows/click2win/click2win_order_submit.md` บรรทัดที่ 13 (Step 2) และ 17 (Step 6) มีข้อความ `(Self-Annealed: ...)` ต่อท้ายซ้ำซ้อนกันเป็นจำนวนมาก ทำให้ไฟล์บวมและยากต่อการอ่านของ Agent

## Scope — ไฟล์ที่อนุญาตให้แก้
- `learned_workflows/click2win/click2win_order_submit.md`

## Context map
| File | Symbol / Lines | Why (read / edit) |
|------|----------------|-------------------|
| `learned_workflows/click2win/click2win_order_submit.md` | Step 2 (L13), Step 6 (L17) | edit: ล้างข้อความ `(Self-Annealed: ...)` ที่ซ้ำซ้อนออก ให้เหลือเพียงคำอธิบายขั้นตอนที่กระชับ |

## Steps / Task Decomposition (Loop Engineering — บังคับ)
| # | Atomic Step | Expected Outcome | Verify | Status |
|---|---|---|---|---|
| 1 | ทำความสะอาด Step 2 และ Step 6 ใน `click2win_order_submit.md` | ข้อความซ้ำ 75 ครั้งหายไป เหลือคำอธิบายภาษาไทยกระชับตามขั้นตอนมาตรฐาน | ตรวจสอบเนื้อหาในไฟล์ | ✅ |
| 2 | รัน verify_changes.py | PASS ครบทุกเทสต์ | `.venv/bin/python scripts/verify_changes.py tests/test_annealing_runbook_isolation.py learned_workflows/click2win/click2win_order_submit.md` | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py tests/test_annealing_runbook_isolation.py learned_workflows/click2win/click2win_order_submit.md`
- `.venv/bin/python -m pytest tests/test_annealing_runbook_isolation.py -q`

## Out of scope / ห้ามแตะ
- ห้ามแก้โค้ด Python ใน `app/` หรือ `tests/`
- ห้ามแก้ไฟล์ runbook อื่น

---

## Jules Report (Jules เขียนบน Cloud VM — STEP 2a · Gemini 3.6 Flash)
- Git Commit(s): Pending submit
- Files changed: `learned_workflows/click2win/click2win_order_submit.md`, `docs/handoff/TASK-sq3-click2win-runbook-clean-f11.md`
- Summary: Cleaned up repeated `(Self-Annealed: ...)` text entries in Step 2 and Step 6 from `click2win_order_submit.md`.
- Tests run + result (Cloud VM):
  - `.venv/bin/python scripts/verify_changes.py tests/test_annealing_runbook_isolation.py learned_workflows/click2win/click2win_order_submit.md` -> PASS (2 passed in 0.40s, targeted test PASS)
- Open questions: None

---

## Cline Triage Report (Cline plugin เขียนในเครื่อง — STEP 2b)
- Local Branch Checked:
- Invariant & Scope Audit:
- Local Verify Result:
- Triage Verdict & Summary for Argon:
