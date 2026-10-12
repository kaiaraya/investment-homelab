# TASK-line-conversation-state: Per-user LINE Conversation State Machine

- Created: 2026-10-12 by Cline (Plan mode, from operator brief)
- Broker: N/A (LINE gateway / cross-broker orchestration layer)
- Status: IN_PROGRESS

## Context (Cline เขียนจาก code inspection)

**ปัญหา**: LINE command ทุกตัวในระบบเป็น **single-shot**
- `app/services/line_service.py:68 _handle_text_message()` เป็น if/elif chain
  เส้นตรง — ทุก branch ตอบแล้ว `return` ทันที
  (kill-switch l.77 → `MODE` l.95 → OTP relay l.101 → action l.157 → SET l.168 →
  schedule l.183 → daily-strategy AI l.201 → TP/SL l.330 → trade regex l.350 →
  `close <SYM>` l.366 → `IGNORED` l.392)
- ยังไม่มีที่เก็บ "slots" ที่รับมาครึ่งทางระหว่าง 2 webhook delivery
  (precedent ที่มีคือ in-memory dict: `TradeCenterService._pending_batches`
  `trade_center_service.py:30`, `ActionCenterService._pending_actions`
  `action_center_service.py:25` — ทั้งคู่ไม่มี TTL eviction)

**เป้าหมาย**: conversation state machine น้ำหนักเบา ต่อผู้ใช้ (key = `source.userId`)
มี timeout แล้วพิสูจน์ด้วย **1 flow ตัวแทนแบบ end-to-end** (`symbol_query`)

**Gate**: `source.userId` / `source.groupId` มีอยู่ใน event แล้ว —
`webhook_line.py:234-249` อ่านไปใช้แค่ OTP target capture และส่ง `events`
ทั้งก้อนเข้า `line_service.process_webhook_events(db, events)` (l.251)
⇒ **ไม่จำเป็นต้องแก้ `webhook_line.py`**

**Authorization gate (Decision A, operator 2026-10-12)** — A1 ปรับ:
allow เมื่อ `LINE_SIMULATION_MODE=True` (tests/dev) **หรือ**
`source.groupId == settings.LINE_GROUP_ID` (กลุ่มส่วนตัวของ operator) **หรือ**
`source.type == "user"` (แชท 1:1 กับ OA)
- **ไม่ใช้ `LINE_ADMIN_USER_ID`** (operator ระบุชัด) — แชท 1:1 กับ OA คือช่อง operator
- ไม่อนุญาต → ตอบปฏิเสธ + **ไม่สร้าง state** + ไม่แตะเส้นทาง order ใด ๆ

**Order safety contract (บังคับ — ยังไม่ implement ในงานนี้)**
- `order_entry` flow (symbol → side → volume → price → confirm) ทำ **design-only**
  terminal step ต้องเรียก `trade_center_service.prepare_order_approval()`
  เท่านั้น (`=> validator.validate_all` = board-lot / SET tick size / value ceiling /
  SHORT uptick) แล้วให้ user ยืนยันผ่าน card → postback `confirm_order`
  → `execute_confirmed_order` → `trade_dispatcher` (PIN-gated LIVE + value limit + HITL)
- **ห้าม** เรียก `trade_dispatcher.dispatch_order()` / broker driver ตรง ๆ จาก flow
- Edge case ที่ต้องแก้ก่อนเปิด order flow: numeric slot (volume/price) อยู่ *หลัง* OTP
  extractor — ต้อง consult FSM ก่อน OTP เมื่อ pending step เป็น numeric หรือบังคับ prefix `/`

## Scope — ไฟล์ที่อนุญาตให้แก้

- `app/services/conversation_state.py` (ใหม่ — engine + flow specs, ไม่มี I/O)
- `app/services/line_service.py` (เพิ่ม `_handle_conversation_turn()` + call-site 1 จุด
  + `_execute_symbol_query()` / `_execute_conversation_terminal()`)
- `tests/test_conversation_state.py` (ใหม่)
- `tests/test_line_conversation_flow.py` (ใหม่)
- `scripts/verify_changes.py` (`MODULE_TEST_MAP` เพิ่มเท่านั้น)
- `AGENTS.md` (pointer subsection สั้น ๆ)
- `docs/handoff/TASK-line-conversation-state.md` (ไฟล์นี้)

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify | Status |
|---|----------------------------|------------------|--------|--------|
| 1 | สร้างไฟล์ handoff นี้ (context + scope + ตารางนี้) | ไฟล์มีครบตาม `_TEMPLATE.md` | report-only (docs) — อ่านเทียบโค้ด | ✅ |
| 2 | ใหม่ `app/services/conversation_state.py` — store + TTL/cancel/restart/purge + flow specs + gate | module import ได้, ไม่มี side-effect (ไม่มี DB/LINE/network) | `scripts/verify_changes.py app/services/conversation_state.py` — compileall OK (mapping มา unit 4) | ✅ |
| 3 | ใหม่ `tests/test_conversation_state.py` — engine: start/get/advance/touch/expiry/isolation/cancel/restart/purge/parsers/gate | ทุก test ผ่าน | `scripts/verify_changes.py app/services/conversation_state.py tests/test_conversation_state.py` → **exit 0 (27 passed)** | ✅ |
| 4 | เพิ่ม `MODULE_TEST_MAP`: new module → tests, และเพิ่ม flow test เข้า mapping ของ `line_service.py` | mapping resolve, target มีอยู่จริงบนดิสก์ | `scripts/verify_changes.py scripts/verify_changes.py` → **exit 0 (17 passed)** | ✅ |
| 5 | แก้ `line_service.py` — `_handle_conversation_turn()` + call-site แทรกหลัง OTP block ก่อน action center | ข้อความ trigger เริ่ม flow; ตอน idle พฤติกรรมเดิมทุกอย่าง | `scripts/verify_changes.py app/services/line_service.py` → **exit 0 (37 passed, ไม่มี regression)** | ✅ |
| 6 | เพิ่ม `_execute_symbol_query()` / `_execute_conversation_terminal()` (DB-only report, Anti-Mock) | อ่านค่าจริงจาก DB; ไม่พบ → ข้อความตรงไปตรงมา | รวมในข้อ 5/7 (ไฟล์เดียวกัน) | ✅ |
| 7 | ใหม่ `tests/test_line_conversation_flow.py` — E2E ผ่าน `/api/v1/webhook/line` (seed DB): happy path 3 turns, fast-path, invalid retry, CANCEL, restart, timeout, per-user isolation, gate denial/allow, non-trigger regression | ทุก test ผ่าน; reply มีค่าที่ seed จริง | `scripts/verify_changes.py ... ` → **exit 0 (79 passed รวม regression set)** | ✅ |
| 8 | อัปเดต `AGENTS.md` (pointer) + ยืนยัน doc ตรงกับโค้ด (Zero-Contradiction) | doc ไม่ขัดกับโค้ด | report-only — อ่านเทียบโค้ด | ✅ |
| 9 | ปิดงาน: `--dry-run` แล้ว `--full` **ครั้งเดียว** + เติม Cline Report | full suite เขียว | `.venv/bin/python scripts/verify_changes.py --full` → **410 passed / 4 failed (env-only, ดู Open Q1)** | ⚠️ |

## Loop Reflection (RCA — loop_engineering §4)

**RCA-1 (2026-10-12) — `AttributeError: 'ConversationStateStore' object has no attribute 'FLOWS'`**
- *Symptom*: 6/14 E2E tests ล้มทันทีที่ถึง turn 2 (`ptt`) — `line_service.py:474`
  `conversation_state.FLOWS.get(state.flow)`
- *Root cause*: `FLOWS` อยู่ที่ **module scope** แต่ `line_service` import **singleton instance**
  (`from app.services.conversation_state import conversation_state`) ซึ่ง **บังชื่อ module**
  → `conversation_state.FLOWS` ไป resolve บน instance ไม่ใช่ module
- *Proved fix*: เพิ่ม accessor `ConversationStateStore.get_flow(name)` (+ `flow_names`) แล้วเรียก
  `conversation_state.get_flow(...)` ทั้ง 2 call-site + เพิ่ม regression test
  `test_get_flow_accessor_exposes_the_registry`
- *บทเรียน*: helper/module constant ของ engine ต้องเข้าถึงได้ผ่าน singleton — อย่าให้ caller
  ต้อง import module กับ instance พร้อมกัน (ชื่อชนกัน)
- *ทำไมจับได้เร็ว*: รัน E2E จริงต่อ unit (ไม่ batch) — ถ้าไป verify ตอนจบจะเจอพร้อมกัน 6 เคส

## Acceptance / Tests ที่ต้องผ่าน

- `.venv/bin/python scripts/verify_changes.py app/services/conversation_state.py tests/test_conversation_state.py`
- `.venv/bin/python scripts/verify_changes.py app/services/line_service.py`
- `.venv/bin/python scripts/verify_changes.py tests/test_line_conversation_flow.py`
- `.venv/bin/python scripts/verify_changes.py --full` (ครั้งเดียวตอนปิดงาน)

## Out of scope / ห้ามแตะ

- `app/services/validator.py`, `app/services/trade_center_service.py`,
  `app/services/trade_dispatcher.py`, `app/core/config.py`,
  `app/api/v1/endpoints/webhook_line.py`, broker drivers ทุกตัว
- `order_entry` flow (design-only ในงานนี้)
- งาน place/modify/cancel order ใด ๆ
- พฤติกรรมของ flow หนึ่งห้ามปนกับโบรกเกอร์อื่น (Broker Knowledge Isolation)

---

## Cline Report (Cline เขียน)

**Files changed** (repo ไม่ใช้ git เป็นแหล่งอ้างอิง → ระบุ path เต็มทุกไฟล์)

| สถานะ | Path เต็ม |
|-------|-----------|
| ใหม่ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/app/services/conversation_state.py` |
| แก้ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/app/services/line_service.py` |
| ใหม่ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/tests/test_conversation_state.py` |
| ใหม่ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/tests/test_line_conversation_flow.py` |
| แก้ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/scripts/verify_changes.py` (เฉพาะ `MODULE_TEST_MAP`) |
| แก้ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/AGENTS.md` (เพิ่ม section "LINE conversation state machine") |
| ใหม่ | `/home/araya-sawasdichai/.cline/worktrees/f7424/InvestmentHomelab/docs/handoff/TASK-line-conversation-state.md` |

ไม่ได้แตะ: `validator.py`, `trade_center_service.py`, `trade_dispatcher.py`, `core/config.py`,
`api/v1/endpoints/webhook_line.py`, broker drivers (ตาม scope §Out of scope)

**Summary**

1. **Engine ใหม่ `app/services/conversation_state.py`** — ไม่มี I/O เลย
   - `ConversationState` (user_id/flow/step/slots/chat_id/chat_type/created_at/updated_at/expires_at)
   - `ConversationStateStore`: `start` / `start_flow(preselect)` / `get` / `is_active` / `advance` /
     `touch` / `clear` / `purge_expired` / `snapshot` / `set_ttl` / `reset` / `get_flow` / `flow_names`
     + `is_authorized()` gate + `is_cancel` / `is_restart` / `match_flow`
   - TTL 300s (`CONVERSATION_TTL_SECONDS`) evict แบบ lazy ตอน `get()` (ไม่มี background sweeper)
   - Flow specs แบบ declarative (`StepSpec`/`FlowSpec`) + pure parsers (`parse_symbol`, `parse_metric`)
   - Flow ที่ implement: **`symbol_query`** (2 steps → terminal read-only report)
2. **ต่อเข้ากับ `line_service.py`** (surgical, 1 call-site)
   - `_handle_conversation_turn()` แทรกที่ **"2.5"** — หลัง kill-switch/MODE/OTP, ก่อน single-shot matcher ทุกตัว
   - `_start_conversation_flow()`, `_execute_conversation_terminal()`, `_execute_symbol_query()`
   - `_execute_symbol_query()` อ่าน **DB เท่านั้น** (`positions`/`sbl_borrow_lots`/`watchlist_triggers`/
     `orders` 5 ล่าสุด) → ไม่มี scrape/login/OTP; ไม่พบข้อมูล → บอกตรง ๆ ว่าไม่พบ (ไม่แต่งค่า)
   - ไม่มี `source.userId` → คืน `None` ทันที ⇒ พฤติกรรมเดิมของทุก command ไม่เปลี่ยน
3. **Authorization gate (Decision A)** — `LINE_SIMULATION_MODE=True` **หรือ**
   `source.groupId == LINE_GROUP_ID` **หรือ** `source.type == "user"` (1:1 OA)
   · **ไม่ใช้ `LINE_ADMIN_USER_ID`** · ปฏิเสธ = ตอบข้อความ + ไม่สร้าง state
4. **Order safety**: ไม่มีโค้ดสั่ง order ใหม่เลยในงานนี้ — `order_entry` เป็น design-only
   และเขียนสัญญาไว้ใน docstring + AGENTS.md ว่าต้องผ่าน `trade_center_service.prepare_order_approval()`
   (=> `validator.validate_all`) + HITL gate เท่านั้น

**Tests run + result** (Loop Engineering: targeted ต่อ unit, `--full` ครั้งเดียวตอนปิดงาน)

| คำสั่ง | ผล |
|--------|-----|
| `.venv/bin/python scripts/verify_changes.py app/services/conversation_state.py tests/test_conversation_state.py --tests tests/test_conversation_state.py` | **exit 0** — 27 passed |
| `.venv/bin/python scripts/verify_changes.py scripts/verify_changes.py` | **exit 0** — 17 passed |
| `.venv/bin/python scripts/verify_changes.py app/services/line_service.py` | **exit 0** — 37 passed (regression set ไม่พัง) |
| `.venv/bin/python scripts/verify_changes.py app/services/conversation_state.py app/services/line_service.py tests/test_conversation_state.py tests/test_line_conversation_flow.py` | **exit 0** — 79 passed |
| `.venv/bin/python scripts/verify_changes.py --full` (ครั้งเดียว) | **410 passed / 4 failed** ใน 139.88s — 4 เคสเป็น env-only (ดู Open Q1) |

**Open questions / สิ่งที่ไม่แน่ใจ**

1. **4 full-suite failures เป็น env-only ไม่เกี่ยวกับงานนี้ (มีหลักฐาน)**
   - `tests/test_mcp_and_workflow_engine.py::test_mcp_handle_tool_call_buffered_recording`
   - `tests/test_mcp_and_workflow_engine.py::test_mcp_json_rpc_stdio_subprocess`
   - `tests/test_sbl_account_driver.py::test_scrape_account_summary_dry_run`
   - `tests/test_sbl_account_driver.py::test_scrape_account_summary_live_dom`
   - ทั้ง 4 ล้มด้วย error เดียวกัน: `playwright._impl._errors.TargetClosedError —
     "Looks like you launched a headed browser without having a XServer running.
     Set either 'headless: true' or use 'xvfb-run'"` (session นี้ไม่มี X display/`DISPLAY`)
   - หลักฐานว่าไม่เกี่ยวกับ diff นี้: ทั้งสองไฟล์ **ไม่ import/reference** `conversation_state`
     หรือ `line_service` เลย (`grep -c conversation_state` = 0 ทั้งคู่) — ต้นทางคือ
     `app/mcp/mcp_server.py:321 → auth.launch_browser()` และ `trademan_driver` headed browser
   - ต้องรันใน session ที่มี display จริง (`xvfb-run` / X จริง) เพื่อยืนยันเพิ่ม — **ยังไม่ได้ทำ**
2. **ยังไม่ได้ยืนยันกับ LINE จริง (live)** — พิสูจน์ระดับ unit + E2E ผ่าน ASGI เท่านั้น
   หากต้องการ live: restart gateway (LINE-RCA-011) แล้วพิมพ์ `query` ในกลุ่ม/1:1 OA ⇒ ต้องมี human confirm
3. **State อยู่ในหน่วยความจำโปรเซสเดียว** — restart/multi-worker ทำ flow ที่ค้างหาย (ตั้งใจ; ดู module docstring)
   หากต้องการคงทนต้องมี persistent store (future unit)
4. **Gate ยอมรับทุกข้อความในแชท 1:1 กับ OA** (ตาม Decision A) — ใครก็ตามที่เป็นเพื่อน OA และคุย 1:1
   จะถือเป็น operator; ถ้าต้องการเข้มขึ้นต้องเพิ่ม allowlist (เช่น `LINE_ALLOWED_USER_IDS`) — future unit
5. **Numeric-slot edge case สำหรับ `order_entry` (ยังไม่ implement)** — volume/price parse อยู่หลัง OTP extractor
   จึงต้อง consult FSM ก่อน OTP เมื่อ pending step เป็น numeric หรือบังคับ prefix `/` (จดไว้ใน module docstring)
6. **พบ latent bug นอก scope (ไม่ได้แก้)**: `line_service.send_text_message()` ถูกเรียกจาก
   `app/services/kill_switch_service.py:66,118` และ `app/services/self_annealing_engine.py:191`
   แต่ `LineMessagingService` **ไม่มีเมธอดนี้** (มี `send_alert`/`push_message`) → `AttributeError` ตอน runtime
   · ต้องมี handoff แยก (ห้ามแก้เองนอก scope)
7. `git status` ยังแสดงไฟล์ที่ถูกแก้ค้างอยู่ก่อนแล้วและไม่เกี่ยวกับงานนี้:
   `learned_workflows/click2win/click2win_order_submit.md`, `learned_workflows/shared/test_anneal_wf.md` (ไม่ได้แตะ)

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
