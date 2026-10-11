# TASK-daily-readiness-skill: Unified Daily Readiness Skill (Mobile Bridge + Broker Sessions)

- Created: 2026-10-08 by Cline
- Broker: Krungsri / Liberator (+ Click2Win report-only)
- Status: IN_PROGRESS

## Context (Antigravity เขียน)

### ปัญหา / เป้าหมาย
- ผู้ใช้ต้องการ **skill เดียวที่ใช้ทุกวัน** เพื่อ "เตรียมความพร้อม" ก่อนไปทดสอบ pillar อื่น (ตอนนี้ค้างอยู่ที่ pillar 1–2)
- ครอบคลุม 2 ด้านเป็นหลัก: (1) **Mobile bridge** (KDE Connect OTP relay พร้อมรับ SMS OTP) และ (2) **Broker sessions** (Krungsri TradeMan, Liberator, Click2Win)
- ปัจจุบัน readiness กระจายอยู่หลายที่: `scripts/preflight_check.py` (ตรวจ), `scripts/start_homelab.py` (Stage1–4), `kdeconnect_service`, runbooks รายโบรกเกอร์ — แต่ไม่มี "พิธีกรรมประจำวัน" ที่รวมเป็นคำสั่งเดียวและคืน GO/NO-GO

### RCA / บทเรียนที่เกี่ยวข้อง
- `KDE-RCA-008` / Invariant 8 — readiness ของสะพานต้องเช็ค real-time D-Bus `isReachable` (ห้ามเชื่อ `iconName`)
- `KDE-RCA-009` — มือถือ + Wi-Fi (Home LAN) ใช้ได้ ไม่ต้องเปิด Tailscale เมื่ออยู่บ้าน
- `KSS-RCA-011` / `LIB-RCA-007` — session health ต้องใช้ inspector ตัวเดียวกับ driver (single source of truth)
- Invariant 9 — ห้ามยิง SMS OTP ถ้าสะพานไม่ live (`is_device_reachable()` ต้องเป็น true)

### User Decision (2026-10-08)
**Auto re-login ทันทีเมื่อ bridge พร้อม** (ยิง SMS OTP อัตโนมัติผ่าน KDE Connect) — มือว่างจบในตัวเดียว
> หมายเหตุ: ต่างจาก `start_homelab.py` Stage 3 ซึ่ง *ไม่* ทำ headed Liberator login (anti-2FA policy) — daily skill นี้ทำ headed login ให้ Liberator ด้วย โดยมี gate `is_device_reachable()` คั่นทุกครั้ง

## Scope — ไฟล์ที่อนุญาตให้แก้

- `.agents/skills/daily-readiness/SKILL.md` (สร้างใหม่)
- `scripts/daily_readiness.py` (สร้างใหม่)
- `AGENTS.md` (ลงทะเบียน skill + วิธีใช้ — เฉพาะส่วนที่จำเป็น)
- `docs/handoff/TASK-daily-readiness-skill.md` (ไฟล์นี้)
- (ถ้าจำเป็น) cross-ref ใน runbooks/RCA ที่ขัดแย้ง

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 0 | เขียน Task Decomposition ลง handoff | ไฟล์นี้มีตารางครบ | `wc -l docs/handoff/TASK-daily-readiness-skill.md` | ✅ |
| 1 | สร้าง `scripts/daily_readiness.py` (skeleton: flags, imports, ANSI, `asyncio.run`) | ไฟล์เกิด + `py_compile` ผ่าน | `.venv/bin/python -m py_compile scripts/daily_readiness.py` → OK | ✅ |
| 2 | Step: mobile bridge (reuse `kdeconnect_service.is_device_reachable` + `refresh_devices` + ping) | reachable=true/false จริง + ping ยิงจริง | รันจริง: `isReachable = true` + `pinged: true` (JSON) | ✅ |
| 3 | Step: session verdicts (reuse `session_file_info` + `session_health`) | verdict ตรงกับ preflight | เทียบ output กับ `preflight_check.py` → ตรง (`MISSING` / `expired=False remaining=6234s`) | ✅ |
| 4 | Step: auto re-login (Krungsri `auth_driver.login`, Liberator `liberator_driver.login`) — gate bridge ก่อน | login เกิดเฉพาะ bridge live; ไม่ยิง OTP เมื่อ bridge down | unit tests ปิด gate (login spy `assert_not_awaited`) + **real OTP login = รอ user ยืนยัน** (gate HITL) | ✅ (code) / ⏸ (live run) |
| 5 | Step: GO/NO-GO banner + JSON + exit code (0=GO, 1=NO-GO) | exit code ถูกต้อง | `dr.main([...])` → 0/1 (tests) + รันจริง `EXIT=1` เมื่อ Krungsri MISSING | ✅ |
| 6 | สร้าง `.agents/skills/daily-readiness/SKILL.md` (procedure + decision tree + safety gates + cross-refs) | ไฟล์เกิด + frontmatter ถูก | `head -8` → `name: daily-readiness` + description ครบ; cross-check ไฟล์ที่อ้างมีจริงทุกไฟล์ | ✅ |
| 7 | ลงทะเบียน skill (AGENTS.md) | grep เจอ | เพิ่มหัวข้อ `## Daily readiness` ใน `AGENTS.md` | ✅ |
| 8 | End-to-end verify + บันทึก PDCA/RCA (edge case) | GO/NO-GO ถูกต้องจริง | `pytest tests/test_daily_readiness.py -q` → 16 passed; regression 56 passed; RCA `rca/shared/rca_daily_readiness.md` (READY-RCA-001) | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python -m py_compile scripts/daily_readiness.py`
- `.venv/bin/python scripts/daily_readiness.py` (รันได้, คืน GO/NO-GO + exit code)
- `.venv/bin/python -m pytest tests/ -q` (subset ที่เกี่ยวข้อง: kdeconnect / preflight / session_health)

## Out of scope / ห้ามแตะ
- Order placement / tick size / price-volume validation
- `scripts/preflight_check.py`, `scripts/start_homelab.py` (ใช้เป็นแหล่งอ้างอิง ไม่แก้)
- MCP tools ที่ place/modify/cancel order
- `tests/test_phase3_api.py` hang (แยก loop)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/daily_readiness.py` (สร้างใหม่ — runner)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/skills/daily-readiness/SKILL.md` (สร้างใหม่ — skill)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_daily_readiness.py` (สร้างใหม่ — 16 tests)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_daily_readiness.md` (สร้างใหม่ — READY-RCA-001)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/AGENTS.md` (เพิ่มหัวข้อ `## Daily readiness`)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/krungsri/krungsri_login_loop_checklist.md` (เพิ่ม cross-ref daily entrypoint)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/liberator/liberator_login_loop_checklist.md` (เพิ่ม cross-ref daily entrypoint)
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-daily-readiness-skill.md` (ไฟล์นี้)

- Summary:
  - **1 คำสั่งเดียว**: `.venv/bin/python scripts/daily_readiness.py` → Step 0 preflight(backend TCP) → Step 1 mobile bridge (real-time D-Bus `isReachable` → `refresh_devices()` → HITL escalate + ping human confirm) → Step 2 session verdict → Step 3 auto re-login (Krungsri `auth_driver.login()` / Liberator `liberator_driver.login()`) → Step 4 GO/NO-GO + exit code (`0`=GO, `1`=NO-GO) + `--json`
  - **Invariant 9 ฝังในโค้ด**: ถ้า `is_device_reachable() != true` → `status=BRIDGE_DOWN` และ **ไม่เรียก `login()` เลย** (ไม่ยิง SMS OTP) — มี unit test ปิดไว้
  - **ไม่สร้างซ้ำ (single source of truth)**: ใช้ `kdeconnect_service`, `krungsri/session_health.session_file_info`, `liberator/session_health.session_health` และ `auth_driver.login()` / `liberator_driver.login()` ตัวเดียวกับ production (Zero-Contradiction) — ไม่ import/แก้ `preflight_check.py` หรือ `start_homelab.py`
  - **Flags**: `--json` / `--no-login` (report-only) / `--force-fresh` / `--no-ping` / `--skip-liberator` / `--click2win`
  - **พบ+แก้ edge case ระหว่างทาง**: verdict แบบ report-only รายงาน NO-GO ปลอม → แยกเป็น pure functions `_krungsri_ready()` / `_liberator_ready()` (ใช้ offline verdict ของแต่ละโบรกเกอร์, Broker Knowledge Isolation) → บันทึกใน `READY-RCA-001`
  - **Zero-Contradiction**: ระบุชัดใน SKILL.md ว่า daily-readiness ทำ headed login ให้ Liberator ต่างจาก `start_homelab.py` Stage 3 (anti-2FA policy) โดยมี gate `isReachable` + human confirm คั่น

- Tests run + result:
  - `.venv/bin/python -m pytest tests/test_daily_readiness.py -q` → **16 passed** (13.95s)
  - `.venv/bin/python -m pytest tests/test_daily_readiness.py tests/test_preflight_check.py tests/test_kdeconnect_service.py tests/test_start_homelab_stages.py -q` → **56 passed** (29.34s)
  - `.venv/bin/python -m py_compile scripts/daily_readiness.py` → OK
  - รันจริง: `.venv/bin/python scripts/daily_readiness.py --no-login --no-ping --json` → `EXIT=1` (NO-GO, reason: `Krungsri TradeMan ไม่พร้อม (SKIPPED / verdict=MISSING)`) — ถูกต้องตามความจริง
  - รันจริง (ก่อนหน้า): `--no-login --json` → mobile bridge `isReachable=true`, `pinged=true` (ยิง ping ไปมือถือจริง), Liberator `expired=False remaining=6234s`, backend :8000 DOWN

- Open questions:
  1. **Live OTP login ยังไม่ได้รัน** (Unit #4 live run) — `data/session_state.json` ของ Krungsri **ขาดหาย** และ credential ถูกตั้งไว้ครบ (`KRUNGSRI_USERNAME/PASSWORD` set = True) → การรันจริงจะ**ยิง SMS OTP จริง**และเปิด headed Chrome จึงรอ user ยืนยันก่อน (gate HITL) — ต้องมี KDE Connect สะพาน live ซึ่งตอนนี้ live
  2. **ขอบเขตโบรกเกอร์**: ทำ Krungsri + Liberator (auto) + Click2Win (report-only, sandbox ไม่มี JWT) — Settrade Open API ไม่มี browser session จึงอยู่นอก scope
  3. `--click2win` ยังเป็นแค่ข้อความแนะนำ (ไม่ผูก auto web-login) เพราะ sandbox ไม่มี OTP — ถ้าต้องการให้ runner login Click2Win จริง บอกได้ (นอก scope เดิม)
  4. Backend :8000 ไม่ได้ auto-start ใน runner นี้ (กันค้าง/กันชนกับ `start_homelab.py`) — ถ้าต้องการให้ runner สตาร์ท uvicorn ให้ด้วย ต้องตัดสินใจเรื่อง process ownership ก่อน

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
