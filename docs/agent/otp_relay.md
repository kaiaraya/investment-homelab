# OTP relay — LINE group (ช่องทางหลักตั้งแต่ 2026-10-08)

> ย้ายมาจาก AGENTS.md (คำต่อคำ) เมื่อ 2026-10-12 เพื่อลด token ที่โหลดทุก call — ต้นฉบับเต็ม: `docs/agent/full/AGENTS_full.md`

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

## MCP history (จาก AGENTS.md เดิม)
- MCP server (เดิม): `app.mcp.mcp_server` (playwright-homelab) เท่านั้น
  - **`homelab-trading-gateway` MCP ถูกถอดออกแล้ว (2026-10-06)** — stdio MCP (`app.mcp.server` ผ่าน `scripts/mcp_launch.sh`) มี env ขาด `DBUS_SESSION_BUS_ADDRESS`/`XDG_RUNTIME_DIR` → KDE Connect OTP capture พัง (ดู `rca/shared/rca_kdeconnect_bridge.md` KDE-RCA-007)
  - การเทรด/พอร์ต/เซสชัน เข้าผ่าน **REST API `/api/v1/*`** หรือ SSE gateway ที่ uvicorn mount ที่ `/sse` (backend module `app.mcp.server` ยังอยู่ ไม่ได้ลบ)
- 2026-10-12: `playwright-homelab` ถูกปิดใน `.agents/mcp_config.json` และ Cline MCP settings ด้วย (retired + ลด token ของ tool schema ทุก call)
