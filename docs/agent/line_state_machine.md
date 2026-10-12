# LINE conversation state machine (multi-step flows — 2026-10-12)

> ย้ายมาจาก AGENTS.md (คำต่อคำ) เมื่อ 2026-10-12 — ต้นฉบับเต็ม: `docs/agent/full/AGENTS_full.md`

- เดิม LINE command ทุกตัวเป็น **single-shot** (`line_service._handle_text_message()` = if/elif chain)
  → flow หลายจบ (symbol → side → volume → price → confirm) ไม่มีที่เก็บ slots ระหว่าง 2 webhook delivery
- Engine: **`app/services/conversation_state.py`** — ไม่มี I/O เลย (ไม่มี DB / LINE API / network) = store + flow specs
  - key = `source.userId` · TTL 300s (`CONVERSATION_TTL_SECONDS` module constant) · lazy eviction
  - orchestrator: `line_service._handle_conversation_turn()` แทรก **หลัง** kill-switch/MODE/OTP และ
    **ก่อน** single-shot matcher ทุกตัว — ถ้าไม่มี `source.userId` = ข้ามทั้งบล็อก (พฤติกรรมเดิมไม่เปลี่ยน)
  - **Authorization gate (Decision A 2026-10-12)**: allow เมื่อ `LINE_SIMULATION_MODE=True` **หรือ**
    `source.groupId == LINE_GROUP_ID` **หรือ** แชท 1:1 กับ OA (`source.type == "user"`)
    — **ไม่ใช้ `LINE_ADMIN_USER_ID`** · ไม่อนุญาต = ตอบปฏิเสธ + **ไม่สร้าง state**
  - flow ที่ implement แล้ว: `symbol_query` (trigger `query`/`check`/`เช็คหุ้น`/`ถามหุ้น`/`ข้อมูลหุ้น`
    + fast-path `QUERY PTT`) อ่านจาก **DB เท่านั้น** (`positions`/`sbl_borrow_lots`/`watchlist_triggers`/`orders`)
    — ห้าม scrape broker (Invariant 7: chat lookup ต้องไม่กระตุ้น login/OTP)
  - **Order safety**: `order_entry` (design-only) terminal step ต้องผ่าน
    `trade_center_service.prepare_order_approval()` (=> `validator.validate_all` = board lot / SET tick /
    value ceiling / SHORT uptick) แล้วให้ user กดยืนยันผ่าน card + HITL gate —
    **ห้าม** เรียก `trade_dispatcher.dispatch_order()` / broker driver ตรง ๆ จาก flow
- Handoff: `docs/handoff/TASK-line-conversation-state.md`
- Tests: `tests/test_conversation_state.py` (engine), `tests/test_line_conversation_flow.py` (E2E ผ่าน webhook)
- ⚠️ แก้โค้ดฝั่งนี้แล้วต้อง restart gateway เสมอ (LINE-RCA-011)
