# TASK-line-cli-help: update /help text + board snapshot

- Created: 2026-10-28 by Hermes `default` (planner lane)
- Loop: LINE CLI reshape · Kanban card: `t_4458dea1`
- Lane: `homelab-build` · Tier: 🟢 T0 · Model: `gemini-3.8-flash` (provider `antigravity-subscription-directsdk`)
- Broker: N/A · Probe: NONE
- Branch: `task/line-cli-help` (off `main`, AFTER `task/line-cli-nego-all` merged) · human squash → `main` = gate #2
- Verify: `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py`

## Context (planner)
`_HELP_TEXT` (handlers.py L529) still advertises `/login`, `/logout`, `/quicktrade`, `/halt` and omits the new `/sync` and `/nego all`. Rewrite it to match the reshaped CLI, then regenerate the board snapshot so `docs/board/loop_board.md` reflects the new cards.

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/handlers.py` (`_HELP_TEXT` only)
- `tests/test_line_cli_flow.py` (help-text assertion)
- `docs/board/loop_board.md` (GENERATED — via `scripts/board_snapshot.py`, never hand-edit)

## Steps / Task Decomposition (atomic)

1. **handlers.py** — replace `_HELP_TEXT` (L529 block) with:
   ```
   📖 คำสั่ง Homelab (KSS / LIB)
   Pillar 2 · ข้อมูล & Sync
     /port [kss|lib|all] [sync]   หุ้นที่ถือ + P/L
     /cash [kss|lib|all] [sync]   เงินสด / กำลังซื้อ
     /orders [kss|lib|all] [sync] ออเดอร์วันนี้
     /sync [portfolio|orders|borrow|balance]
          sync broker ↔ DB (ไม่ระบุ = ครบทุกอย่าง ทั้ง 2 โบรก)
   Pillar 3 · เทรด
     /buy /sell /short /cover ...  (รอ confirm card)
     /nego kss|lib|all [SYM|เลข]   ต่อราคา (all = ทั้ง 2 โบรกเกอร์)
     /negotiate <order_no>         แก้ราคาในที่ (Quick Trade)
   Pillar 4 · หุ้นยืม SBL (KSS เท่านั้น)
     /sbl [sync] · /sbl pool <sym> · /borrow <sym> <vol> · /return <sym> [vol|all]
   Session: เปิด CDP session ผ่าน RustDesk เอง (ไม่ทำผ่าน LINE)
   ฉุกเฉิน: PANIC · RESET · MODE
   พิมพ์ /help nego เพื่อดูรายละเอียดต่อราคา
   ```

2. **tests** — extend the existing `/help` test to assert the text contains `/sync` and does NOT contain `/login kss` or `/quicktrade`.
   - Verify: `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q`

3. **board snapshot** — run `.venv/bin/python scripts/board_snapshot.py` (it rewrites `docs/board/loop_board.md` from the board DB; `--check` must exit 0 afterward).

## Acceptance / Done when
- `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` → green (targeted only).
- `.venv/bin/python scripts/verify_changes.py app/services/line_cli/handlers.py` → PASS.
- `docs/board/loop_board.md` regenerated (snapshot `--check` clean).
- Committed to `task/line-cli-help` (never `main`). Commit msg: `TASK-line-cli-help: docs(line_cli): /help reflects retire + /sync + /nego all`.

## Out of scope / ห้ามแตะ
- Command behaviour (other cards). Rich menu layout (unchanged). Driver code.

## Worker contract (บังคับ)
- Targeted test only. Fail-closed. Commit to `task/line-cli-help` off `main`; never `git add -A`; never `main`.
- Fill `## Worker Report` before done.
