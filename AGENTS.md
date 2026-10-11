# InvestmentHomelab — Agent Rules (shared: Antigravity + Cline)

ไฟล์นี้เป็นกฎกลางที่ทั้ง Antigravity และ Cline (DeepSeek) อ่าน — แก้ที่นี่ที่เดียว

## Project
- Python / FastAPI + Playwright broker automation (Krungsri TradeMan, Settrade Click2Win, Liberator, Settrade Open API).
- venv: `.venv/bin/python`
- Tests (เต็มชุด — รันครั้งเดียวตอนปิดงานเท่านั้น): `.venv/bin/python -m pytest tests/ -q`
- **Verify hook ต่อ unit (บังคับ — Loop Engineering)**: `.venv/bin/python scripts/verify_changes.py <ไฟล์ที่แก้...>`
  → `compileall` + เฉพาะ test ที่แมปกับไฟล์นั้น (exit `0`=PASS · `1`=FAIL · `2`=BLOCKED/UNMAPPED)
  · mapping SSOT = `MODULE_TEST_MAP` ในสคริปต์ · รายละเอียด `.agents/rules/loop_engineering.md` §3
  - **ห้ามรัน full suite ต่อ loop** — ใช้ `scripts/verify_changes.py --full` ครั้งเดียวตอนปิดงาน
  - **ห้ามรัน pytest สองตัวพร้อมกัน** (`test_homelab.db` single-writer → SQLite deadlock จริง 2026-10-08)
  - อยากดูแผนก่อนรัน: `--dry-run` (ไม่กินเวลา, ไม่ถูก gate)
- Backend gateway (single entrypoint ตั้งแต่ 2026-10-08): **`app.main:app`** (uvicorn) —
  ให้บริการ `/api/v1/*` (รวม `/api/v1/webhook/line`), `/console`, `/sse`, `/health`
  - ⚠️ **แก้โค้ดฝั่ง gateway แล้วต้อง restart process เสมอ (LINE-RCA-011)** — `uvicorn app.main:app`
    รันโดยไม่มี `--reload`; โปรเซสที่รันอยู่จะยังใช้โมดูลรุ่นเก่า (แก้บนดิสก์ ≠ แก้ที่รันอยู่)
    ทำให้เห็นอาการหลอกที่เหมือนบั๊กเดิมกลับมา · ยืนยันด้วย `ps -o lstart= -p <pid>` เทียบ mtime ของ source
  - ⚠️ `python -m app.mcp.mcp_server` (stdio / playwright-homelab) = **legacy/retired** — อย่าใช้เป็น entrypoint
    เพราะคนละโปรเซสกับ gateway → LINE webhook + `event_bus` OTP relay ติดต่อกันไม่ได้
- MCP server (เดิม): `app.mcp.mcp_server` (playwright-homelab) เท่านั้น
  - **`homelab-trading-gateway` MCP ถูกถอดออกแล้ว (2026-10-06)** — stdio MCP (`app.mcp.server` ผ่าน `scripts/mcp_launch.sh`) มี env ขาด `DBUS_SESSION_BUS_ADDRESS`/`XDG_RUNTIME_DIR` → KDE Connect OTP capture พัง (ดู `rca/shared/rca_kdeconnect_bridge.md` KDE-RCA-007)
  - การเทรด/พอร์ต/เซสชัน เข้าผ่าน **REST API `/api/v1/*`** หรือ SSE gateway ที่ uvicorn mount ที่ `/sse` (backend module `app.mcp.server` ยังอยู่ ไม่ได้ลบ)

## OTP relay — LINE group (ช่องทางหลักตั้งแต่ 2026-10-08)
- **LINE relay** ผ่าน OA `@678clhio` (`a14s homelab`) — รองรับ 2 channel; **KDE Connect เป็น dormant** (โค้ดยังอยู่ ไม่ลบ)
  - `line_group` (preferred): บอทอยู่ในกลุ่ม `a14s homelab` → ใช้ `LINE_GROUP_ID`
  - `line_direct` (LINE-RCA-006): ใช้แชท 1:1 กับ OA → ใช้ `LINE_ADMIN_USER_ID` (ไม่ต้องมีกลุ่ม)
- Gate เดียว (single source of truth): `app/services/otp_relay_readiness.py`
  - พร้อมเมื่อ: LINE token จริง + `LINE_SIMULATION_MODE=False` + (`LINE_GROUP_ID` **หรือ** `LINE_ADMIN_USER_ID`) + backend `:8000` listen
    **+ เป้าหมายนั้น deliverable จริง** — `_probe_target()` ยิง `group/summary` (C…) / `room/summary` (R…) / `profile/{id}` (U…) ต้องได้ 200
    (`LINE-RCA-007`: "id มีค่า" ≠ "ส่งถึงได้" — ค่า 404 = gate ปิด **fail-closed** ไม่ fallback ไป 1:1)
  - ใช้ร่วมกันโดย `auth_driver`, `liberator_driver`, `scripts/daily_readiness.py`, `scripts/start_homelab.py` (Stage 1)
- **ห้ามยิง SMS OTP ถ้า `otp_relay_readiness.check().ready != true`** (Invariant 9 — LINE variant)
- Push target auto-capture: พิมพ์ข้อความใน **กลุ่ม** → จับ `source.groupId` → `LINE_GROUP_ID`;
  พิมพ์ใน **แชท 1:1** → จับ `source.userId` → `LINE_ADMIN_USER_ID` (`webhook_line.py` เขียนลง `.env`, ไม่ต้อง restart)
- Push target lifecycle (self-healing — `LINE-RCA-008`): event **`leave`** → เคลียร์ `LINE_GROUP_ID`,
  **`unfollow`** → เคลียร์ `LINE_ADMIN_USER_ID` (เขียน `.env` เป็น `KEY=` แบบ atomic + รีเซ็ต de-dup guard);
  **`memberLeft`** = สมาชิกคนอื่นออก → ไม่จับ/ไม่เคลียร์ (บอทออกจากกลุ่มเมื่อไร ค่าตายจะถูกปล่อยเองทันที)
  - เงื่อนไขฝั่ง LINE: OA จะถูกเชิญเข้ากลุ่มได้ต้องเปิด `Allow bot to join group chats` ก่อน (default = Disabled — `LINE-RCA-005`)
- Webhook: `https://line.a14s.dev/api/v1/webhook/line` (cloudflared → `:8000`) — backend = `app.main:app`
- **Multi-broker attribution (`LINE-RCA-010`)**: relay persist ผ่าน `app/services/otp_relay_registry.py` เท่านั้น
  - **pin primary DB** (`AsyncSessionLocal`) — **ห้าม**ใช้ platform-aware `get_db()` กับ relay
    (เดิม `TRADING_PLATFORM=CLICK2WIN` ทำให้ row ไปลง `investment_homelab_click2win.db` → driver ทุกตัว timeout)
  - `push_otp_request()` เขียน marker `OTP_REQUESTED` (broker+ref) **ก่อน** push → ACK ระบุโบรกเกอร์จริง (ไม่ hardcode)
  - **latest-request-wins** (TTL 300s) · row มี tag `(Broker: X)` · driver กรองด้วย `broker_matches()`
- เริ่มระบบ: `scripts/start_homelab.py [--keep-open]` (Stage 1 เปิด gateway ให้เอง) หรือ
  `.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- RCA: `rca/shared/rca_line_otp_group.md` (LINE-RCA-001/002/003/**010**) · Handoff: `docs/handoff/TASK-line-otp-group-relay.md`,
  `docs/handoff/TASK-otp-channel-authoritative.md`

## Daily readiness (ใช้ทุกวันก่อนทดสอบ pillar)
- Skill: `.agents/skills/daily-readiness/SKILL.md` · Runner: `scripts/daily_readiness.py`
- คำสั่งเดียว: `.venv/bin/python scripts/daily_readiness.py` → exit `0` = GO (พร้อม), `1` = NO-GO (ต้อง HITL)
- Auto re-login ทันทีเมื่อ OTP relay live; **ห้ามยิง SMS OTP ถ้า `otp_relay_readiness.check().ready != true`** (Invariant 9)
- Tests: `.venv/bin/python -m pytest tests/test_daily_readiness.py tests/test_otp_relay_readiness.py -q`
- Handoff/RCA: `docs/handoff/TASK-daily-readiness-skill.md`, `docs/handoff/TASK-line-otp-group-relay.md`

## Mandatory rules
- อ่านและทำตาม `.agents/rules/broker_pdca_rca.md` และ `.agents/rules/root_cause_and_escalation.md` ทุกครั้ง
- ห้าม mock / แต่งข้อมูลบัญชี ยอดเงิน order id (Anti-Mock Guardrail)
- ห้ามนำพฤติกรรมของโบรกเกอร์หนึ่งไปใช้กับอีกโบรกเกอร์ (Broker Knowledge Isolation)
- อ่านและทำตาม `.agents/rules/loop_engineering.md` — แตกงานเป็น atomic steps แล้ววน loop DECOMPOSE→EXECUTE→VERIFY→REFLECT→REPEAT ทุกงาน

## Trading safety (CRITICAL)
- ห้ามเรียก MCP tool ที่ place / modify / cancel order เว้นแต่ผู้ใช้สั่งในแชทอย่างชัดเจนใน task นั้น
- ห้ามแก้ logic ส่วน order, tick size, price/volume validation ถ้าไม่ได้ระบุไว้ใน scope ของไฟล์ handoff
- ห้ามแสดง / คัดลอกค่า credential จาก `.env` ลงในไฟล์อื่น, log หรือแชท

## Handoff protocol (Antigravity → Cline → Antigravity)
- งานมาจาก `docs/handoff/TASK-xxx.md` (template: `docs/handoff/_TEMPLATE.md`) — ทำเฉพาะ scope ที่ระบุ
- ก่อนเริ่มงาน: เขียน "Task Decomposition" (atomic steps + per-step verify) ลงในไฟล์ handoff แล้วทำทีละ step (ห้าม batch)
- เริ่มใน Plan mode, ยืนยันแผนกับผู้ใช้ แล้วจึงสลับเป็น Act mode
- เมื่อเสร็จต้องเติมส่วน `## Cline Report` ในไฟล์ handoff:
  - Files changed (path เต็มทุกไฟล์ — repo นี้ไม่มี git จึงเป็นแหล่งเดียวที่ใช้ตรวจ)
  - Summary ของการเปลี่ยนแปลง
  - คำสั่งเทสต์ที่รัน + ผลลัพธ์
  - Open questions / สิ่งที่ไม่แน่ใจ
- ถ้าเจอปัญหานอก scope ให้บันทึกใน Open questions แทนการแก้เอง
