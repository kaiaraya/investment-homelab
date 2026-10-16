# TASK-loop1-3: Liberator — Quote ตรงตัว + /nego lib Hardening (Fail-Closed)

- Created: 2026-10-15 by Argon (Complex Task Owner)
- Broker: Liberator WebTrade (LIB · CASH)
- Status: DONE (unit + live quote gate · merged `9ed1f5a`; live amend witness in `TASK-loop1-4`)
- Run mode: INTERACTIVE (ห้องนี้ · `stepwise-approval`) — โค้ด+unit รันในห้องนี้; การ์ด `045ac` ถูกลบ 2026-10-15 ตาม `.agents/skills/task-router/SKILL.md` §3 fallback (kanban session start จาก agent terminal ถูก cancel; root cause ยังเปิด) · live quote = live witness ใน `TASK-loop1-4`
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
| 1 | `get_market_bid_offer` fail-closed (D1 → **D3 ย้ายไป quote API**) | อ่าน quote ไม่ได้/ไม่ตรง symbol → `QUOTE_UNAVAILABLE` ไม่คืนราคาเดา | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ✅ D1+D3 (35) |
| 2 | `change_order` ยืนยัน symbol | symbol ไม่ตรง → ไม่กด + error | `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` | ✅ D3 |
| 3 | `_broker_modify` (lib) fail-closed | ไม่มีราคา/ไม่ตรง → `unavailable_card` | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ D1+D3 |
| 4 | verify ครบ 3 ไฟล์ | PASS | `.venv/bin/python scripts/verify_changes.py …` | ✅ PASS (162) |
| 5 | **D3: quote ต้องพิสูจน์ตัวหุ้นได้จริง** | `n == symbol` จาก `/vb/stock/info`; ไม่ตรง ⇒ `SYMBOL_MISMATCH` | `scripts/liberator/live_check_quote_gate.py` (สด, read-only) | ✅ PASS (live) |
| 6 | **D3: e2e `/nego lib`** (symbol filter / order_no filter / G5 tick distance) | 3 เคสใหม่ผ่าน | `.venv/bin/python -m pytest tests/test_line_cli_flow.py -q` | ✅ (85) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`
- `.venv/bin/python -m pytest tests/test_liberator_change_order.py tests/test_line_cli_flow.py -q --tb=line`

## Out of scope / ห้ามแตะ
- **ห้ามส่งออเดอร์ใหม่** · ห้ามแตะ KSS/QuickTrade (การ์ด 2) · ห้ามยิง SMS OTP · ห้าม restart gateway
- การทดสอบ LIVE จริงเป็นของการ์ด 4 (งานนี้ unit/mock เท่านั้น)

---

## Cline Report
- Git Commit(s): `9ed1f5a` (`TASK-loop1-3: fix(liberator): symbol-verified quote API + fail-closed /nego lib`)
- Files changed:
  - `app/brokers/liberator/driver.py` — `get_market_bid_offer()` อ่านผ่าน quote API + **symbol gate** (D3);
    helper ใหม่ `_to_float`/`_to_int`/`_extract_order_book_id`/`_resolve_order_book_id`/`_fetch_stock_info`
  - `app/brokers/liberator/plugin.py` — passthrough (D1/D3, รอบก่อนหน้า)
  - `app/services/line_cli/handlers.py` — fence ชั้น 2 + `/nego` batch halt (D1/D3, รอบก่อนหน้า)
  - `tests/test_liberator_change_order.py` — 7 เคส quote API (แทน 5 เคส DOM เดิม)
  - `tests/test_line_cli_flow.py` — +3 e2e `/nego lib` (symbol filter / order_no filter / G5 "ห่างเกิน 3 tick")
  - `scripts/liberator/probe_liberator_board_symbol.py` **(ใหม่)** — headed probe + ดัก XHR (หลักฐาน DOM/HTTP)
  - `scripts/liberator/probe_liberator_quote_api.py` **(ใหม่)** — ยืนยัน schema ของ quote API (headless)
  - `scripts/liberator/live_check_quote_gate.py` **(ใหม่)** — live check ของโค้ด production (read-only, exit code)
  - `rca/liberator/rca_liberator.md` — +`LIB-RCA-020` (registry + deep dive), ปรับรายละเอียด D1 ของ `LIB-RCA-019`
  - `learned_workflows/liberator/liberator_portfolio.md` — §8 เขียนใหม่ทั้งหัวข้อ (DOM depth table → quote API)
- Summary:
  - **Root cause (live-proven)**: กระดาน WebTrade key ด้วย **`orderBookId`** ไม่ใช่ symbol text และ depth table
    บนจอไม่มีข้อมูล identity เลย ⇒ หลักฐานสด: ขอ `BCH` แต่กระดานยิง
    `POST /vb/stock/bid-offer {"orderBookId": 65781}` → `n:"A"` / AREEYA = **คนละหุ้น**
  - **Fix**: `GET /vb/config` (map symbol→orderBookId; `set` ก่อน `tfex`) → `POST /vb/stock/info`
    → **gate `n == symbol`**; ไม่ตรงหรืออ่านไม่ได้ ⇒ `QUOTE_UNAVAILABLE` + `SYMBOL_MISMATCH` โดยทุกตัวเลขเป็น `None`
  - Bonus: `prior_close`/`ceiling`/`floor` มีค่าจริงจาก API (`prior`/`cl`/`fl` — ตรวจแล้วตรงกับ ±30% ของ prior ทั้ง 3 ตัว)
- Tests run + result:
  - `tests/test_liberator_change_order.py` → **35 passed**
  - `tests/test_line_cli_flow.py` → **85 passed** (82 → +3)
  - `verify_changes.py app/brokers/liberator/driver.py tests/test_liberator_change_order.py tests/test_line_cli_flow.py` → **PASS (162 tests)**
  - `verify_changes.py --full` (task close) → **PASS (677 passed, 214s)**
  - `scripts/liberator/live_check_quote_gate.py` (โค้ด production + broker สด) → **RESULT: PASS** (exit 0)
- Open questions:
  1. ✅ `verify_changes.py --full` → **PASS (677 passed, 214s)** — รอบนี้ไม่ค้างที่ ~87% (log: `/tmp/verify_full.log`)
  2. **ขอบเขต commit**: commit เฉพาะ 3 ไฟล์ D3 (driver + 2 test) หรือรวม D1 ที่ยังไม่ commit (`plugin.py`, `handlers.py`) ด้วย?
     (working tree ยังมี `directive/*`, `.agents/skills/task-router/SKILL.md`, `docs/handoff/TASK-loop1-4*` ที่ **ไม่ใช่** งานการ์ดนี้)
  3. `board_lot`/`flag` ยังเป็น `None` — ไม่พบ field ใน `/vb/stock/info` (ต้อง probe เพิ่มถ้าจะใช้)
  4. `bp`/`op` = `"0"` (halt/pre-close) ถูกตีความเป็น `0.0` ไม่ใช่ `None` — ตรงกับพฤติกรรมเดิม; ถ้าต้องการ fail-closed
     ตอน halt ต้องตกลงนโยบายก่อน (นอก scope การ์ดนี้)
  5. `/Portfolio` ตั้งต้นที่ `orderBookId 65781` = `A` — ยังไม่รู้ว่ามาจาก workspace/watchlist ไหน (ไม่มีผลต่อ fix แล้ว เพราะ gate ที่ API)
  6. ✅ **ปิดแล้ว (user, 2026-10-15)**: หลักฐานของการ์ดนี้ = headless network capture ×2 (`probe_liberator_quote_api.py`,
     `live_check_quote_gate.py`) + unit/e2e + `--full` PASS; **screen witness (headed, ดูกับตา) ยกไปการ์ด 4 / `TASK-loop1-4`**
     (Live Round B) ตามที่ตกลง
---

## Verification & Stepwise Approval
- [x] Stage A (Code Audit) · [x] Stage B (Verify — 162 targeted + 677 full PASS) · [x] Stage C (Live Quote API Gate `live_check_quote_gate.py` PASS; headed order-amend witness deferred to `TASK-loop1-4`) · [x] Stage D (Verdict + Merge `9ed1f5a`)
- Verdict: **PASS (code + unit + live quote gate)** / live amend witness = `TASK-loop1-4`
---

## Argon Analysis
- **Direction alignment**: PASS — ค้นพบและปิด Root Cause สำคัญ (`LIB-RCA-020`): ตาราง Bid/Offer บน DOM ของ `/Portfolio` ผูกกับ `orderBookId` ตั้งต้น (`65781` = `A`) ไม่ได้เปลี่ยนตามช่องค้นหาเสมอไป การย้าย `get_market_bid_offer()` มาอ่านผ่าน Quote API (`GET /vb/config` → `POST /vb/stock/info`) พร้อมบังคับ Gate `n == symbol` ป้องกันการนำราคาหุ้นผิดตัวมาแก้คำสั่งได้เด็ดขาด
- **Directive consistency**: ตรงตาม `directive/master_directive_v2.md` §2 Pillar 3 และ §4 Invariant 1 (Anti-Mock Fail-Closed: เมื่อชื่อหุ้นไม่ตรงหรือดึงไม่ได้ คืน `QUOTE_UNAVAILABLE` + ตัวเลข `None` ทั้งหมด และ `handlers.py` หยุดด้วย `unavailable_card`)
- **Code vulnerability scan**:
  - Open question #4 (`bp`/`op` = `"0"` ช่วง Halt / Pre-open ถูกแปลงเป็น `0.0`): แม้ G4 (`validate_tick_size(0.0)` = False) และ G5 (`tick_distance_exceeds`) จะช่วยบล็อกไม่ให้ส่งราคา `0.0` ออกไป แต่ควรแปลง `<= 0` ใน `_to_float` ของ `bid_1`/`offer_1` เป็น `None` (หรือ `NO_QUOTE`) ในรอบถัดไปเพื่อความชัดเจนตั้งแต่ชั้น Driver
- **Next loop improvement**: ยืนยัน `/nego lib <order_no>` และ `/nego lib <sym ผิด>` บนตลาดจริงพร้อมพยานใน `TASK-loop1-4` ขั้นที่ 5–6

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
