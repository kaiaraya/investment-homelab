# TASK — LINE Group OTP Relay (แทน KDE Connect)

**Date:** 2026-10-08
**Mode:** Act
**Owner:** Cline
**Platform:** Ubuntu NUC (`NUC-Intel`) · backend = `app.main:app` (unified FastAPI gateway)

## Goal
ย้ายช่องทาง OTP relay จาก KDE Connect (D-Bus/GSConnect) → **LINE Group bot `a14s homelab`**
เพื่อให้ auto re-login ของ Krungsri TradeMan / Liberator ทำงานได้โดยไม่ต้องพึ่งมือถือ pairing

## Confirmed facts (verified 2026-10-08)
- `cloudflared` named tunnel `trademan` → public `https://line.a14s.dev` → ingress `http://localhost:8000` (running)
- Webhook URL: `https://line.a14s.dev/api/v1/webhook/line`
- `.env` มี credential จริงแล้ว + `LINE_SIMULATION_MODE=false` (secret len 34 / token len 172)
- `GET https://api.line.me/v2/bot/info` → **HTTP 200**, displayName = **`a14s homelab`**, basicId `@678clhio`
- โครงสร้าง LINE OTP มีอยู่แล้ว ~90%: `OTPSource.LINE_CHAT`, `_handle_text_message()` §2, `extract_otp_from_text()`, `event_bus.publish_otp(LINE_CHAT)`, `_wait_for_otp_multi_channel()` check `LINE_OTP_RECEIVED` ใน DB

## Known bugs / gaps
1. `webhook_line.py` ทำ `json.loads("")` บน empty body → LINE Console "Verify" ได้ 400 (ต้องตอบ 200 ก่อน parse)
2. ไม่มี `LINE_GROUP_ID` → `push_message()` ยังใช้ `LINE_ADMIN_USER_ID` (ว่าง) → ตกไป broadcast
3. `auth_driver` OTP readiness gate ยัง gate ด้วย `kdeconnect_service.is_device_reachable()`
4. `daily_readiness.py` gate ยังเป็น KDE Connect
5. `directive/kdeconnect.md` §4 สั่ง "ตัด LINE ออกจากระบบ OTP" → ขัดกับสถาปัตยกรรมใหม่

## Steps / Task Decomposition (atomic units)
| # | Unit | Expected Outcome | Verify |
|---|------|------------------|--------|
| U1 | `app/api/v1/endpoints/webhook_line.py`: empty-body → 200; capture `source.groupId` | LINE Console Verify → 200; groupId ถูก log/เก็บ | pytest + curl |
| U2 | `app/core/config.py`: add `LINE_GROUP_ID` | settings โหลดค่าได้ | `python -c` |
| U3 | `app/services/line_service.py`: push เลือก group ก่อน broadcast + `push_otp_request()` | push `to == groupId` | unit test payload |
| U4 | `app/browser/auth_driver.py`: gate KDE→LINE + push OTP request เมื่อ AWAITING_OTP | ไม่ยิง SMS ถ้า LINE ไม่พร้อม | unit test monkeypatch |
| U5 | `scripts/daily_readiness.py`: bridge check → LINE readiness | exit 0 = GO | รันจริง |
| U6 | start backend `uvicorn app.main:app --port 8000` | port 8000 listen | curl |
| U7 | Docs reconcile: `directive/kdeconnect.md`, `AGENTS.md`, `.agents/skills/daily-readiness/SKILL.md`, RCA | ไม่มีเนื้อหาขัดแย้ง | grep |
| U8 | Tests + live E2E | ผ่านทั้งหมด | pytest |

## Out of scope
- ไม่แตะ logic order / tick size / price validation
- ไม่ลบโค้ด KDE Connect (ทำเป็น dormant ตาม Zero-Contradiction)

## Cline Report

**วันที่:** 2026-10-08 · **Mode:** Act · **ผู้ทำ:** Cline

### Files changed (absolute paths)
| # | ไฟล์ | การเปลี่ยนแปลง |
|---|------|----------------|
| 1 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/api/v1/endpoints/webhook_line.py` | **LINE-RCA-001**: verify signature ก่อน → empty body (LINE Console Verify) ตอบ `200 {"note":"verify_ping"}` แทน 400 · **LINE-RCA-003**: อ่าน `source.groupId` แล้ว auto-capture ลง `.env` (`LINE_GROUP_ID`) แบบ atomic + set ในโปรเซสทันที (ไม่ทับค่าที่ผู้ใช้ตั้งไว้) |
| 2 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/core/config.py` | เพิ่ม `LINE_GROUP_ID`, `LINE_PUBLIC_WEBHOOK_URL`, `LINE_OTP_RELAY_ENABLED` |
| 3 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/otp_relay_readiness.py` | **ไฟล์ใหม่** — gate เดียว (single source of truth): `OtpRelayReadiness` + `otp_relay_readiness.check()` (LINE token/group/gateway) รองรับ `allow_kde_fallback` |
| 4 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/line_service.py` | `push_message()` → คืน `bool` + เลือก target `to_user_id` → `LINE_GROUP_ID` → `LINE_ADMIN_USER_ID` → broadcast · เพิ่ม `push_otp_request(ref, broker, timeout_seconds)` |
| 5 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/auth_driver.py` | gate KDE → `otp_relay_readiness` (LINE) · push คำขอ OTP เข้ากลุ่มเมื่อ `AWAITING_OTP` · **LINE-RCA-002**: `OTP_SESSION_LOG_PATTERN` (single source of truth) แทน regex เดิมที่ไม่ match ข้อความจริง |
| 6 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/liberator/driver.py` | poll OTP จาก LINE (event bus + `session_logs`) + push คำขอ OTP เข้ากลุ่ม (เดิม poll แค่ KDE) |
| 7 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/daily_readiness.py` | Step 1 → `otp_relay_readiness` · human confirm ผ่านข้อความในกลุ่ม LINE · HITL steps ใหม่ · docstring/flag parser |
| 8 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/start_homelab.py` | Stage 1 → `stage1_check_otp_relay()` (+ `ensure_gateway_running()` เปิด gateway ให้เอง) · `move_window_to_workspace()` (wmctrl) · flags `--keep-open`, `--workspace`, alias `--skip-relay` |
| 9 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_webhook_line.py` | +2 tests (verify ping, group capture) |
| 10 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_line_otp_group.py` | **ไฟล์ใหม่** — 4 tests (target resolution, `push_otp_request`) |
| 11 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_otp_relay_readiness.py` | **ไฟล์ใหม่** — 11 tests (readiness matrix + regex LINE-RCA-002) |
| 12 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_daily_readiness.py` | `_pin_bridge` → pin `otp_relay_readiness.check` + LINE spies · แทน test ของ KDE ด้วย LINE relay |
| 13 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-line-otp-group-relay.md` | **ไฟล์ใหม่** — handoff + task decomposition + รายงานนี้ |
| 14 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_line_otp_group.md` | **ไฟล์ใหม่** — LINE-RCA-001/002/003 + Zero-Contradiction checklist |
| 15 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_kdeconnect_bridge.md` | เพิ่มป้าย **DORMANT** (ไม่ลบเนื้อหาเดิม) |
| 16 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/directive/kdeconnect.md` | **กลับด้าน §2/§4** (เดิมสั่ง "ตัด LINE ออกจาก OTP") + superseded banner |
| 17 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/AGENTS.md` | entrypoint = `app.main:app`, `mcp_server` = legacy · เพิ่มหัวข้อ OTP relay LINE |
| 18 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/skills/daily-readiness/SKILL.md` | frontmatter/flow/gates/troubleshooting → LINE relay |
| 19 | `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_gateway_lifecycle.md` | **ไฟล์ใหม่** — GW-RCA-001 (ASGI shutdown artifact ตอน restart) + GW-RCA-002 [OPEN] (cloudflared ingress เปิดทุก path) + ขั้นตอน restart ที่พิสูจน์แล้ว |

### Summary
เปลี่ยนช่องทาง OTP relay จาก KDE Connect (D-Bus/GSConnect) → **LINE group `a14s homelab`**
โดย KDE ถูกทำให้ **dormant** (ไม่ลบ) ตาม Zero-Contradiction
- Gate เดียวที่ทุกฝ่ายใช้: `app/services/otp_relay_readiness.py`
- Flow: บอท push คำขอ OTP เข้ากลุ่ม → ผู้ใช้พิมพ์ 6 หลัก → webhook → `event_bus.publish_otp(LINE_CHAT)`
  + `SessionLog("LINE_OTP_RECEIVED")` → driver อ่าน (in-process event bus หรือ cross-process SQLite)

### Tests run + ผลลัพธ์

| คำสั่ง | ผล |
|--------|-----|
| `.venv/bin/python -m pytest tests/test_webhook_line.py -q` | **4 passed** (2 เดิม + 2 ใหม่) |
| `.venv/bin/python -m pytest tests/test_line_otp_group.py -q` | **4 passed** (ไฟล์ใหม่) |
| `.venv/bin/python -m pytest tests/test_otp_relay_readiness.py -q` | **11 passed** (ไฟล์ใหม่) |
| `.venv/bin/python -m pytest tests/test_daily_readiness.py -q` | **16 passed** (ปรับให้ตรง LINE gate) |
| `.venv/bin/python -m pytest tests/test_webhook_line.py tests/test_line_otp_group.py tests/test_otp_relay_readiness.py -q` | **18 passed** |
| `.venv/bin/python -m py_compile scripts/start_homelab.py …` (8 ไฟล์) | **COMPILE OK** |
| `.venv/bin/python scripts/start_homelab.py --help` | flag `--keep-open`, `--workspace`, `--skip-kde/--skip-relay` ปรากฏถูกต้อง |
| `curl -X POST https://line.a14s.dev/api/v1/webhook/line` (body ว่าง + signature จริง) | **HTTP 200** `{"status":"ok","note":"verify_ping"}` |
| `curl -X POST https://line.a14s.dev/api/v1/webhook/line` (signature ผิด) | **HTTP 400** (ถูกต้อง) |
| `curl -X POST https://line.a14s.dev/api/v1/webhook/line` (text event ไม่มี groupId) | **HTTP 200** `IGNORED` |
| `.venv/bin/python scripts/daily_readiness.py` (ตรวจ LIVE) | relay = **NOT ready** — เหลือเพียง `LINE_GROUP_ID` (ถูกต้องตามจริง; Anti-Mock) |
| `otp_relay_readiness.check()` (LIVE) | `ready=false`, `reason=LINE_GROUP_ID not set`, `line_token_configured=true`, `line_simulation_mode=false` |
| `GET http://127.0.0.1:8000/health` | **HTTP 200** `{"status":"healthy"}` |
| `GET https://api.line.me/v2/bot/info` | **HTTP 200** — bot `a14s homelab` / `@678clhio` (พิสูจน์ว่า token ใน `.env` ใช้ได้จริง) |

**สถานะ: 34/34 targeted tests ผ่าน** และ webhook E2E ผ่าน tunnel จริง

### Live verification (หลักฐาน)
- backend: `setsid nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` → `LISTEN 0.0.0.0:8000` (log: `/tmp/homelab_backend.log`)
- tunnel: `cloudflared` pid 3159 (named tunnel `trademan`) → `https://line.a14s.dev` → `:8000` (ของเดิม รันอยู่แล้ว)
- LINE Console **Verify จะผ่านแล้ว** (เดิม 400 จาก `json.loads("")`)

### สิ่งที่ผู้ใช้ต้องทำเอง (ทำครั้งเดียว)
1. ✅ **ทำแล้ว 2026-10-08 15:14** — LINE Console → Reissue token → อัปเดต `.env` (mtime 15:12:56) → **restart gateway แล้ว** (ดู § "Restart gateway" ด้านล่าง)
2. กด **Verify** ที่ Webhook URL `https://line.a14s.dev/api/v1/webhook/line` → ต้องขึ้น Success
3. **เชิญบอท `a14s homelab` (`@678clhio`) เข้ากลุ่ม LINE** แล้วพิมพ์ข้อความ 1 ครั้ง
   → `webhook_line.py` จะเขียน `LINE_GROUP_ID=C...` ลง `.env` ให้เอง (ไม่ต้อง restart)
4. รัน `.venv/bin/python scripts/daily_readiness.py` → ต้องได้ `✅ relay พร้อม (channel=line_group)`
5. (ทางเลือก) `--keep-open` ต้องมี `wmctrl` → `sudo apt install wmctrl` (ตอนนี้เครื่องยังไม่มี; โค้ดรายงานตามจริง ไม่หลอกว่า ✅)

### Restart gateway (2026-10-08 15:14) — ทำแล้ว + หลักฐาน

**เหตุผล:** ยืนยันว่าจำเป็นจริง — โปรเซสเก่าเริ่ม `14:34:10` แต่ `.env` ถูกแก้ `15:12:56`
→ token ในหน่วยความจำยังเป็นตัวเก่า

| ขั้น | คำสั่ง/การตรวจ | ผล |
|------|----------------|-----|
| pre-check | `ps -o lstart= -p 26694` vs `date -r .env` | 14:34:10 (ก่อน) < 15:12:56 (แก้) → **ต้อง restart** |
| pre-check | token ใหม่ยิง `GET https://api.line.me/v2/bot/info` | **HTTP 200** → `a14s homelab` / `@678clhio` |
| pre-check | token fingerprint (sha256 16 ตัว, **ไม่พิมพ์ค่า token**) | `f94a957fd9eb15b3` = ตรงกับ `.env` |
| stop | `kill -TERM 26694` (graceful) | **port 8000 FREE** ทันที · lifespan หยุด dispatcher/sentinel/orchestrator เรียบร้อย |
| start | `setsid nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` (cmdline เดิม, cwd เดิม) | **pid 35752** · `LISTEN 0.0.0.0:8000` |
| verify | `GET /health`, `GET /console` | **200** / **200** (`{"status":"healthy"}`) |
| verify | LINE Console Verify ping ผ่าน tunnel (HMAC จาก `.env` secret) | **200** `{"status":"ok","note":"verify_ping"}` → **พิสูจน์ว่า in-process secret == `.env`** |
| verify | bad signature | **400** (ถูกต้อง) |
| verify | log โปรเซสใหม่ — grep `OTP|login|2fa|sms|ASGI message` | **0** → ไม่มีการยิง SMS OTP / ไม่มี background login (Invariant 9) ✅ |
| verify | `otp_relay_readiness.check()` LIVE | `ready=False`, `reason=LINE_GROUP_ID not set`, `line_token_configured=True`, `line_simulation_mode=False`, `gateway_port=8000` |
| verify | SSE clients `100.123.34.50` (Tailscale) | **reconnect อัตโนมัติ** (`GET /sse` 200) → remote MCP client ไม่หลุดหาย |

**สรุป:** step 1 (reissue + restart) เสร็จแล้ว ✅ — เหลือแค่ **เชิญบอทเข้ากลุ่ม LINE** (ข้อ 3) ซึ่งเป็นด่านสุดท้ายของ relay

**หมายเหตุ:** restart มี stack trace 2 ชุดตอน shutdown (`RuntimeError: Expected ASGI message ...`)
→ **ไม่ใช่บั๊กของเราและไม่ใช่ของ webhook** — เป็น artifact ของ Starlette เมื่อสั่งปิดโปรเซสขณะมี SSE stream ค้าง
บันทึกต้นตอ + ขั้นตอน restart ที่ปลอดภัยแล้วใน `rca/shared/rca_gateway_lifecycle.md` **GW-RCA-001**
และเจอประเด็นความปลอดภัยใหม่ (cloudflared ingress เปิดทุก path → external scanner ยิง `GET /.env` → 404 = ยังไม่รั่ว)
บันทึกเป็น **GW-RCA-002 [OPEN]**

### รอบ 2 (2026-10-08 15:36) — Verify ผ่าน + บอทเข้ากลุ่มแล้ว แต่ยังไม่ capture `LINE_GROUP_ID`

ผู้ใช้แจ้ง: กด **Verify → success** ✅ และเชิญบอท `@678clhio` เข้ากลุ่มแล้ว ✅
แต่ตรวจแล้ว **ยังไม่มี `LINE_GROUP_ID`** → relay ยัง `ready=false` (รายงานตามจริง)

**สิ่งที่พบใน log (หลักฐาน)**

| บรรทัด | หลักฐาน |
|--------|---------|
| `147.92.149.170:0 - "POST /api/v1/webhook/line" 200 OK` | **LINE ส่งคำขอ Verify มาถึงจริง** (IP ของ LINE) → **ฝั่ง server ยืนยันว่า Verify ผ่าน** |
| `147.92.149.165:0 - "POST /api/v1/webhook/line" 200 OK` | (กดซ้ำ/retry) ผ่านเช่นกัน |
| **ไม่มี** `[LINE] source.groupId observed:` | → **ยังไม่มี event จากกลุ่มเข้ามาเลย** (ไม่ใช่ `join` และไม่ใช่ message) |
| `.env` ไม่มี `LINE_GROUP_ID` · `check()` → `ready=false` | ผลสอดคล้องกัน ไม่มีการหลอกข้อมูล |

**Root cause (LINE-RCA-004)**: payload ที่ LINE Console Verify ส่งจริงคือ `{"events":[]}`
→ โค้ดเดิมคืน 200 **โดยไม่ log อะไรเลย** → แยกไม่ออกว่า Verify ผ่านหรือมี event กลุ่มเข้ามา
(และ `join` event ของการเชิญบอทไม่ได้มาถึงระบบ)

**แก้แล้ว (ปิด observability gap + เพิ่มเทสต์)**

| ไฟล์ | การเปลี่ยนแปลง |
|------|----------------|
| `app/api/v1/endpoints/webhook_line.py` | + รับมือ `{"events":[]}` → ตอบ 200 `note=verify_ping` และ **log ให้เห็น** · + `logger.info("[LINE] Received N event(s): [types]")` (log แค่ type ไม่ log id/ข้อความ = privacy-safe) |
| `tests/test_webhook_line.py` | + `test_line_webhook_verify_ping_empty_events` (payload ทรงจริงของ Console) · + `test_line_webhook_join_event_captures_group_id` (เคสบอทถูกเชิญเข้ากลุ่ม → capture groupId + ต้องได้ 200) |

**Restart เพื่อโหลดโค้ดใหม่**: pid `35752` → **`38313`** (15:35:53) · `/health` 200
**พิสูจน์ว่าโค้ดใหม่ทำงาน**: ยิง `{"destination":"U_test","events":[]}` + signature จริง ผ่าน tunnel
→ `HTTP 200 {"note":"verify_ping"}` และ log ขึ้น
`[LINE] Webhook acknowledged with 0 events (LINE Console verification / keep-alive).` ✅

**Tests**: `pytest tests/test_webhook_line.py -v` → **6 passed** (เดิม 4 + ใหม่ 2)
· regression รวม 7 ไฟล์ → **63 passed**

**ขั้นถัดไป (ต้องทำที่มือถือ/Console)**

1. ⚠️ ตรวจ **Messaging API → Webhook settings → "Use webhook" = ON** (สำคัญ: ถ้าปิด LINE
   จะไม่ส่ง event จริงเลย แต่ปุ่ม Verify ยังผ่านได้ → อธิบายอาการนี้พอดี)
2. **ส่งข้อความ 1 ครั้งในกลุ่ม `a14s homelab`** (พิมพ์อะไรก็ได้ เช่น `hi`)
   → จะเห็น log `[LINE] Received 1 event(s): ['message']` + `[LINE] source.groupId observed: C...`
   → `.env` ได้ `LINE_GROUP_ID=C...` ทันที **ไม่ต้อง restart**
3. จากนั้นรัน `.venv/bin/python scripts/daily_readiness.py` → ต้องได้ `✅ relay พร้อม (channel=line_group)`

#### 🔎 ผลหลังผู้ใช้เปิด `Use webhook = ON` + ส่ง `Hi` (15:44–15:48) — เจอต้นตอจริง

**มี event เข้ามาจริงแล้ว** (ยืนยันว่า `Use webhook = ON` แก้ปัญหา "ไม่มี event" ได้):

```
2026-10-08 15:44:28,182 [INFO] webhook_line: [LINE] Received 1 event(s): ['message']
INFO:  147.92.149.165:0 - "POST /api/v1/webhook/line HTTP/1.1" 200 OK
```

**แต่ยังไม่มี `LINE_GROUP_ID`** และ **ไม่มี** `[LINE] source.groupId observed:` →
event นั้น **ไม่มี `source.groupId`** → ข้อความถูกพิมพ์ใน **แชท 1:1 กับบอท** (`source.type="user"`)
ไม่ใช่ในกลุ่ม (`source.type="group"`) — **ไม่ใช่บั๊กของโค้ด** แต่เป็นตำแหน่งที่พิมพ์

**เพิ่ม observability ปิดช่องว่างสุดท้าย** (`app/api/v1/endpoints/webhook_line.py`):
log เพิ่ม `source.type` → `[LINE] Received N event(s): [{'type': ..., 'source': ...}]`
(ไม่ log id/ข้อความ = privacy-safe) พิสูจน์สด 15:48 ด้วย event `type=follow` (ไม่มีผลข้างเคียง)
→ `[LINE] Received 1 event(s): [{'type': 'follow', 'source': 'user'}]` ✅

**ตารางวินิจฉัยจาก log**

| เห็นอะไรใน log | ความหมาย |
|---|---|
| `source: 'group'` + `source.groupId observed: C...` | ✅ สำเร็จ → `.env` ได้ `LINE_GROUP_ID` |
| `source: 'user'` | ❌ พิมพ์ในแชท **1:1** → ต้องพิมพ์ใน **กลุ่ม `a14s homelab`** |
| มีแต่ `200 OK` ไม่มี log `[LINE]` | payload `{"events":[]}` = Console Verify / keep-alive |
| ไม่มี request เข้ามาเลย | ❌ `Use webhook` ปิดอยู่ หรือ webhook URL ไม่ตรง |

**เทสต์เพิ่ม**: `test_line_webhook_1to1_message_does_not_capture_group_id`
(กันการ set `LINE_GROUP_ID` จากแชท 1:1 ซึ่งจะทำให้ OTP ไปลงผิดที่แบบเงียบ ๆ) → **7 passed**
**Restart**: pid `38313` → **`39923`** (15:47) · `/health` 200 · live probe ผ่าน

**คำขอถัดไป**: ส่งข้อความใน **กลุ่ม** `a14s homelab` (ไม่ใช่แชท 1:1 กับบอท)
→ ผมจะยืนยัน `source.groupId observed` + รัน `daily_readiness.py` ให้ทันที

#### ✅ ต้นตอจริงยืนยันแล้ว (15:52) — LINE-RCA-005: `Allow bot to join group chats` ปิดอยู่

ผู้ใช้ยืนยัน: **"บอทไม่ได้อยู่ในกลุ่ม"** → ตรงกับหลักฐาน log ที่ได้ (`source: 'user'` = 1:1 เท่านั้น)

**สาเหตุจากเอกสาร LINE (developers.line.biz/messaging-api/group-chats):**
> *"To be invited, go to LINE Developers Console > Messaging API tab of your channel and enable
> **Allow bot to join group chats**. **This setting is disabled by default.**"*
> *"At any time, **only one LINE Official Account can be in a group chat**."*

→ สวิตช์นี้ปิด (default) ⇒ **เชิญ OA `@678clhio` เข้ากลุ่มไม่ได้** ⇒ LINE ไม่ส่ง event กลุ่มเลย
⇒ `source.groupId` ไม่มีทางถูกจับ — **ไม่ใช่บั๊กของ webhook/parser/โค้ดใด ๆ ของเรา**

**ขั้นตอนปลดล็อก (ทำที่ LINE เป็นหลัก)**

| # | ทำอะไร | ที่ไหน |
|---|--------|--------|
| 1 | เปิด **`Allow bot to join group chats`** → **Edit → Enable** | LINE Developers Console → Messaging API channel → แท็บ **Messaging API** |
| 2 | เชิญ OA **`@678clhio`** เข้ากลุ่ม `a14s homelab` (เมนูกลุ่ม → Invite) | แอป LINE |
| 3 | ส่งข้อความ 1 ครั้งในกลุ่ม | แอป LINE → กลุ่ม |
| 4 | ตรวจ capture + readiness | ผมรัน `scripts/daily_readiness.py` ให้ |

> **หมายเหตุ:** 1 กลุ่มมี OA ได้แค่ 1 ตัว · LINE **Verify ผ่านได้แม้บอทไม่อยู่ในกลุ่มใดเลย** → Verify ไม่ใช่หลักฐานว่าออนบอร์ดดิ้งสำเร็จ
> **ทางเลือกสำรอง (ต้องอนุมัติ + งานใหม่):** push OTP เข้า **แชท 1:1** ของ operator แทนกลุ่ม
> (LINE push รับ `to` = userId ได้ แต่ gate `otp_relay_readiness` ตรวจ `LINE_GROUP_ID` โดยเจตนา
> เพื่อให้ OTP เห็นร่วมกันหลายคน → ถ้าเปลี่ยนต้องแก้ gate + เทสต์ + เอกสาร = นอก scope)

## รอบ 3 (2026-10-08) — Path B: OTP relay ใช้แชท 1:1 ได้ (ไม่ต้องมีกลุ่ม LINE)

**Trigger:** ผู้ใช้ยืนยัน *"บอทไม่ได้อยู่ในกลุ่ม"* → ต้นตอ = `Allow bot to join group chats`
(default Disabled) ⇒ เชิญ OA เข้ากลุ่มไม่ได้ (ดู `LINE-RCA-005`)
→ **ผู้ใช้อนุมัติ Path B**: ใช้ **แชท 1:1 กับ OA** ที่มีอยู่แล้วเป็นช่องทาง OTP แทนกลุ่ม

**Design (Zero-Contradiction):**

- OTP **capture** จาก 1:1 ใช้ได้อยู่แล้ว (`line_service._handle_text_message()` →
  `extract_otp_from_text()` ไม่ผูกกับ groupId) — ไม่ต้องแก้
- OTP **push target** → เพิ่มการ capture `source.userId` ของแชท 1:1 → `LINE_ADMIN_USER_ID`
  (fallback ที่ `push_message()`/`push_otp_request()` รองรับอยู่แล้ว — `line_service.py:1429/1508`)
- **Precedence:** `LINE_GROUP_ID` (channel `line_group`) ชนะ `LINE_ADMIN_USER_ID` (channel `line_direct`)
- **ห้าม** capture `source.userId` จาก event ของกลุ่ม (นั่นคือ userId ของ *สมาชิกที่พิมพ์* ไม่ใช่ operator chat)

### Steps / Task Decomposition (atomic units)

| # | Unit (atomic) | Expected outcome | วิธี Verify |
|---|---------------|------------------|-------------|
| 1 | `app/services/otp_relay_readiness.py` — เพิ่ม `CHANNEL_LINE_DIRECT`, ผ่อน gate ให้รับ `LINE_GROUP_ID` **หรือ** `LINE_ADMIN_USER_ID` | gate `ready=True` + `channel=line_direct` เมื่อมีแต่ userId | `pytest tests/test_otp_relay_readiness.py -q` (เพิ่มเทสต์ direct/precedence) |
| 2 | `app/api/v1/endpoints/webhook_line.py` — `_write_env_key()` + `_persist_user_id()` (เฉพาะ `source.type=="user"`) | event 1:1 → `LINE_ADMIN_USER_ID` เขียนลง `.env` · event กลุ่ม → **ไม่** เขียน | `pytest tests/test_webhook_line.py -q` (เพิ่ม/แก้เทสต์ 1:1) |
| 3 | เทสต์ใหม่/แก้เทสต์เดิมให้ตรงพฤติกรรมใหม่ | ทุก assertion ผ่าน ไม่มีเทสต์ที่ขัดกับโค้ด | `pytest tests/test_webhook_line.py tests/test_otp_relay_readiness.py -q` |
| 4 | อัปเดตเอกสาร/ข้อความ CLI ให้ตรง (Zero-Contradiction): `otp_relay_readiness` docstring, `daily_readiness.py`, `start_homelab.py`, `AGENTS.md`, `SKILL.md` | ไม่มีที่ไหนบอกว่า "ต้องมีกลุ่มเท่านั้น" | `grep -rn "เข้ากลุ่ม"` + อ่านไฟล์ที่แก้ |
| 5 | RCA `LINE-RCA-006` + handoff report | องค์ความรู้ครบสำหรับ loop ถัดไป | อ่านไฟล์ |
| 6 | **Live proof:** restart gateway → พิมพ์ข้อความ 1 ครั้งในแชท 1:1 → ตรวจ `.env` + log | `LINE_ADMIN_USER_ID` ถูก capture + `daily_readiness.py` → `channel=line_direct` | log gateway + `.env` + `scripts/daily_readiness.py` |

**Out of scope (รอบนี้):** ไม่แตะ logic order/tick size · ไม่แตะ `Allow bot to join group chats` (ฝั่ง LINE) ·
ไม่ลบโค้ดกลุ่ม LINE (ยังเป็น primary เมื่อมี groupId)

---

### Open questions / สิ่งที่ไม่แน่ใจ (นอก scope — ไม่ได้แก้)

1. **[BLOCKER เดียวที่เหลือ] ยังไม่มี `LINE_GROUP_ID`** → relay ยัง `ready=false`
   ผมไม่สามารถเชิญบอทเข้ากลุ่ม LINE แทนผู้ใช้ได้ (ต้องทำจากแอป LINE บนมือถือ)
   → ผู้ใช้ทำข้อ 3 ข้างบนแล้วรัน `daily_readiness.py` อีกครั้ง

2. **[ของเดิม / นอก scope] full test suite ค้าง** ที่ `tests/test_phase3_api.py::test_phase3_api_endpoints`
   - อาการ: ค้างไม่จบ (ไม่ fail, ไม่ timeout) — loop อยู่ใน `select()`, aiosqlite threads ว่าง, ไม่มี TCP connection
   - หลักฐานวินิจฉัย (`-o faulthandler_timeout=45`):
     `pytest_asyncio/plugin.py:905 in inner → base_events.py run_until_complete → selectors.py:468 select`
   - **พิสูจน์ว่าไม่ใช่ผลจากการแก้ของผม:** รันซ้ำด้วย
     `pytest tests/ -v --ignore=tests/test_line_otp_group.py --ignore=tests/test_otp_relay_readiness.py --ignore=tests/test_webhook_line.py --ignore=tests/test_daily_readiness.py`
     → ค้างที่ test เดิม **ตำแหน่งเดิม** (`test_phase3_ai_and_eod.py` ผ่านครบ แล้วค้างที่ `test_phase3_api.py::test_phase3_api_endpoints`)
   - และ test นั้น **ผ่านใน 2.75s เมื่อรันเดี่ยว** → เป็นอาการ test-isolation/ordering
     (น่าจะมี test ก่อนหน้าทิ้ง module-level `asyncio.Lock`/`Event`/singleton ที่ถูก acquire ใน event loop ที่ปิดไปแล้ว)
   - ยังทดสอบ: `pytest tests/test_phase2_auto_reconnect.py tests/test_phase3_ai_and_eod.py tests/test_phase3_api.py -q` → **9 passed** (จึงต้องมีไฟล์ก่อนหน้าอีกที่ทริกเกอร์)
   - **ข้อเสนอ (งานแยก):** ไล่หาไฟล์ที่ทริกเกอร์ด้วยการ bisect ระดับไฟล์ + เปลี่ยน singleton lock ให้ผูกกับ loop
     (`asyncio.Lock()` ที่สร้างตอน import เป็น anti-pattern ข้าม loop)

3. **[ต้องตัดสินใจ] `--keep-open` semantics** — ผมตีความเป็น
   "คงหน้าต่างไว้ + ย้ายหน้าต่าง `/console` (title `Investment Homelab - Operations & Capability Cockpit`) ไป workspace `--workspace` (default 2) ด้วย wmctrl เพื่อไม่บังหน้าต่าง login/OTP"
   ถ้าผู้ใช้ต้องการความหมายอื่น (เช่น ไม่ให้ orchestrator ปิด uvicorn ตอน Ctrl+C) บอกได้ แก้ไม่กี่บรรทัด

4. **[ต้องตัดสินใจ] process เก่า `python -m app.mcp.mcp_server` (pid 4315)** ยังรันอยู่ (5+ ชม.)
   ผมยังไม่ฆ่า เพราะไม่กระทบ LINE relay และการฆ่า process นอกเหนือจากที่ยืนยันชัดเจน
   → ถ้าต้องการให้เก็บกวาด บอกได้: `kill 4315`

5. **[สังเกต] `DIRECTIVE §5.2` ของ `directive/kdeconnect.md`** ยังมี mermaid diagram ที่วาดเส้นทาง KDE เป็นหลัก
   ผมติดป้าย superseded ที่หัวเอกสาร + กลับด้าน §2/§4 แล้ว แต่ไม่ได้วาด diagram ใหม่ (เสี่ยงแก้ผิดบริบท)

6. **[OPEN — แนะนำให้ทำ] จำกัด cloudflared ingress path** (ดู `rca/shared/rca_gateway_lifecycle.md` GW-RCA-002)
   ตอนนี้ `~/.cloudflared/config.yml` ผูก **ทั้ง hostname** `line.a14s.dev` → `:8000`
   → ทุก path เข้าถึงได้จากอินเทอร์เน็ต และพบ **external scanner** (`167.235.185.190`) ยิง `GET /.env`
   → ตอบ **404** (ไม่มี route เสิร์ฟไฟล์นี้) = **ยังไม่มีการรั่วไหล** แต่ควรจำกัด ingress ให้เหลือ
   `path: /api/v1/webhook/line` เท่านั้น — **ผมยังไม่แก้ เพราะกระทบพฤติกรรม tunnel และต้องยืนยันว่า
   ไม่มี client ระยะไกลที่พึ่ง tunnel สำหรับ path อื่น** (ที่เห็นใน log `/console` + `/sse` เข้าผ่าน
   localhost/Tailscale `100.88.217.33` ไม่ใช่ tunnel → น่าจะปลอดภัย แต่ขอให้ผู้ใช้ยืนยันก่อน)
7. **[OPEN — แนะนำให้ทำ] uvicorn `--host 0.0.0.0`** ทำให้ `:8000` เปิดรับจาก LAN ทั้งหมด
   (`192.168.1.47`) — ถ้าไม่จำเป็นให้ใช้ `--host 127.0.0.1` แล้วพึ่ง cloudflared/Tailscale อย่างเดียว
   (ผมไม่แก้เองเพราะเป็น decision ของผู้ใช้ และมี client Tailscale ที่ต้องเข้าถึง)

### Zero-Contradiction — ตรวจแล้วไม่มีเนื้อหาขัดแย้ง
`grep -rn 'is_device_reachable'` ในเส้นทาง gate → เหลือแต่ใน `kdeconnect_service` เอง,
`app/brokers/krungsri/cli.py`, `app/mcp/pillars/pillar1_session.py`, `scripts/preflight_check.py`,
`scripts/kdeconnect_cli.py`, `scripts/replay_kde_rca005.py` (ทั้งหมดเป็น KDE-specific / diagnostic — ไม่ใช่ gate ของ login)
→ **path ของ auth_driver / liberator_driver / daily_readiness / start_homelab ใช้ `otp_relay_readiness` ครบแล้ว**

---

## รอบ 4 (2026-10-08 16:40+) — ปิด false-GO + self-healing (LINE-RCA-007 / LINE-RCA-008)

### Steps / Task Decomposition (ทำครบทุก unit แล้ว)

| Unit | งาน (atomic) | Verify | ผล |
|---|---|---|---|
| 7 | `otp_relay_readiness._probe_target()` + fail-closed gate | unit test + live verdict | ✅ PASS |
| 8 | `webhook_line` lifecycle release (`leave`/`unfollow`) + `memberLeft` ignore | 5 webhook tests | ✅ PASS |
| 9 | ล้าง target ที่ตายใน `.env` + restart gateway | `/health` + gate verdict | ✅ PASS |
| 10 | บันทึก RCA-007/008 + handoff | grep เนื้อหา | ✅ PASS |
| 11 | live re-proof หลังผู้ใช้ทำ action ฝั่ง LINE | `daily_readiness.py` | ✅ PASS (16:44–16:46) |

### ปัญหาที่เจอ (ทำไมต้องมีรอบนี้)

`scripts/daily_readiness.py` ขึ้น **`✅ relay พร้อม`** แต่ push จริงล้มด้วย
`{"message":"Failed to send messages"}` → **false-GO** ⇒ Invariant 9 พัง (ยิง SMS OTP ทิ้ง)
เพราะ gate เดิมเช็คแค่ "`LINE_GROUP_ID` มีค่าไหม" ไม่ได้เช็คว่า **ส่งถึงจริงไหม**

### ต้นตอ (จาก log จริง `/tmp/homelab_backend.log`)

```
15:48:18  follow (user)   — แอด OA เป็นเพื่อน
16:11:18  join   (group)  — capture LINE_GROUP_ID=Ccd… ลง .env  ✅ (ตอนนั้นถูกต้อง)
16:12:27  memberLeft      — สมาชิกออก
16:12:27  leave  (group)  — บอทออก/ถูกนำออกจากกลุ่ม  ❌ (ค้างค่าไว้ = poisoned target)
```

- `GET /v2/bot/group/Ccd…/summary` → **404** ; `POST /v2/bot/message/push` → **Failed to send messages**
- โค้ดเดิมจับ `groupId` จาก **ทุก** event (รวม `leave`) และ **ไม่เคยเคลียร์** ค่า

### สิ่งที่แก้ (proven working solution)

1. `app/services/otp_relay_readiness.py` — `_probe_target(target_id, token)`:
   - `C…` → `GET /v2/bot/group/{id}/summary` · `R…` → `room/summary` · `U…` → `profile/{id}`
   - คืน `(False, "HTTP 404: …")` เมื่อไม่ 200 ; เน็ตหลุด/timeout = unreachable (ไม่ throw, ไม่ log token)
   - `check()` **probe ก่อนเปิด gate** และ **fail-closed**: ถ้า `LINE_GROUP_ID` ตั้งไว้แต่ deliver ไม่ได้
     → `ready=False` **ไม่ fallback ไป 1:1** (ตรงกับ precedence ของ `line_service.push_message`)
2. `app/api/v1/endpoints/webhook_line.py` — lifecycle release:
   - `GROUP_RELEASE_EVENTS={"leave"}` → `_release_group_id()` เคลียร์ `settings.LINE_GROUP_ID` + เขียน `.env` เป็น `LINE_GROUP_ID=` (atomic) + รีเซ็ต `_last_seen_group_id`
   - `USER_RELEASE_EVENTS={"unfollow"}` → `_release_user_id()` เคลียร์ `LINE_ADMIN_USER_ID`
   - `memberLeft` → `continue` (คนอื่นออก = ไม่จับ/ไม่เคลียร์)
3. `.env` — ล้าง `LINE_GROUP_ID=Ccd…` → `LINE_GROUP_ID=` (ค่าที่พิสูจน์แล้วว่า 404)
   ※ ไม่สำรองเป็นไฟล์อื่น เพราะผิดกฎห้ามคัดลอก credential ไปไฟล์อื่น
4. Restart gateway:
   `kill 45004 && nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/homelab_backend.log 2>&1 &`



### Files changed (รอบ 4 — absolute paths)

- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/otp_relay_readiness.py` (Unit 7)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/api/v1/endpoints/webhook_line.py` (Unit 8)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_otp_relay_readiness.py` (+3 เทสต์)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_webhook_line.py` (+5 เทสต์ lifecycle)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.env` (ล้าง `LINE_GROUP_ID` ที่ตายแล้ว — ค่า credential ไม่ถูกแตะ/ไม่ถูกพิมพ์)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_line_otp_group.md` (LINE-RCA-007, LINE-RCA-008, checklist)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-line-otp-group-relay.md` (ไฟล์นี้)

### Tests run + ผลลัพธ์ (รอบ 4)

```
.venv/bin/python -m pytest tests/test_webhook_line.py tests/test_otp_relay_readiness.py -q
→ 30 passed in 11.44s

.venv/bin/python -m pytest tests/ -q -k 'line or relay or webhook or readiness'
→ 59 passed, 225 deselected in 22.53s
```

### Live verification (รอบ 4 — หลักฐานจริง)

```
$ curl -s http://127.0.0.1:8000/health
{"status":"healthy"}                      ← gateway โหลดโค้ด Unit 8 แล้ว

$ ss -ltn | grep :8000
LISTEN 0 2048 0.0.0.0:8000 0.0.0.0:*

$ .venv/bin/python scripts/daily_readiness.py --no-login   (verdict หลังล้างค่า)
LINE_GROUP_ID  : ''
ADMIN_USER_ID  : None
READY / CHANNEL: False / none
REASON         : LINE_GROUP_ID / LINE_ADMIN_USER_ID not set — no OTP push target …
→ ⛔ relay DOWN — login ใหม่จะถูกยกเลิก (ห้ามยิง SMS OTP)      ← ซื่อสัตย์แล้ว (ไม่มี false-GO)
```

ก่อนแก้ (หลักฐาน false-GO เดิม): `ready=True` + `Push error response: {"message":"Failed to send messages"}`
หลังแก้: `ready=False` พร้อมเหตุผล 404 จริง → **gate กับความจริงตรงกันแล้ว (Zero-Contradiction)**

### Live re-proof (Unit 11) — ✅ พิสูจน์สดแล้ว (2026-10-08 16:44–16:46)

ผู้ใช้เลือก **Path B (แชท 1:1)** แล้วส่งข้อความจริง 1 ครั้ง → ระบบ self-heal เองทั้งหมด:

```
16:44:56 [LINE] Received 1 event(s): [{'type': 'message', 'source': 'user'}]
16:44:56 [LINE] source.userId observed (1:1 chat): U…            ← capture (masked)
16:44:56 [LINE] LINE_ADMIN_USER_ID captured into …/.env (OTP push target locked in).

$ awk -F= '/^LINE_(GROUP_ID|ADMIN_USER_ID)=/' .env
LINE_GROUP_ID      -> 0 chars  (EMPTY)   ← ค่า poisoned (404) ถูกปล่อยแล้ว
LINE_ADMIN_USER_ID -> 33 chars (SET)     ← probe /v2/bot/profile/{U…} = 200

$ .venv/bin/python scripts/daily_readiness.py --no-login
0. 🔌 Backend Gateway (uvicorn :8000): ✅ FastAPI Gateway is UP on port 8000.
1. 📱 OTP Relay: ✅ relay พร้อม (channel=line_direct) — 1:1 chat with the OA + gateway up
                ✅ ส่งข้อความยืนยันเข้าแชท LINE แล้ว
⛔ NO-GO — เฉพาะ session broker (SKIPPED เพราะ --no-login) ไม่เกี่ยวกับ relay
```

- บรรทัด "ส่งข้อความยืนยัน…แล้ว" มาจาก `push_message() is True` ซึ่งเป็นจริง **เฉพาะเมื่อ HTTP < 400**
  จาก `POST /v2/bot/message/push` (ก่อนแก้ได้ "ไม่สำเร็จ" + `Failed to send messages`) ⇒ **หลักฐานจริง ไม่ใช่ mock**
- เหลือ **human confirm**: ผู้ใช้เห็นข้อความ `✅ [a14s homelab] OTP relay พร้อม — เริ่มเตรียม session ได้` ในแชทแล้วหรือยัง
- หลังยืนยัน: รัน `.venv/bin/python scripts/daily_readiness.py` (ไม่ใส่ `--no-login`) เพื่อ re-login Krungsri ให้ครบ flow จริง

### Live re-proof ที่ทำได้ฝั่ง operator (ทางเลือก Path A — ถ้าอยากกลับไปใช้กลุ่ม)
เชิญ OA `@678clhio` เข้ากลุ่มใหม่ → event `join` → capture `LINE_GROUP_ID` ใหม่
(ค่าที่ล้างไปแล้วทำให้ re-capture ได้ แม้จะเป็นกลุ่มเดิม) — ถ้าย้ายไปใช้กลุ่มเมื่อไร ตัว `leave` จะปล่อยค่าให้อัตโนมัติเสมอ

### Open questions (รอบ 4)

1. **[ต้องตัดสินใจ] กลุ่มใหม่ที่เชิญบอทเข้า ขณะ `.env` ยังมีค่าเก่าอยู่** — `_persist_group_id` ยัง**ไม่ทับ** ค่าที่มีอยู่
   (guard "ห้ามทับของ operator") ⇒ ถ้าอนาคตมีค่า stale ที่ไม่เคยมี event `leave` ตามมา (เช่น บอทถูกถอดทั้งที่ webhook ปิดอยู่)
   จะต้องมีคนล้าง `.env` เอง 1 ครั้ง — ยัง**ไม่แก้**เพราะการทับอัตโนมัติเสี่ยงทำลายค่าที่ operator ตั้งใจตั้ง
   ทางเลือกที่ปลอดภัยกว่าถ้าต้องการ: ให้ `join` ทับได้เฉพาะเมื่อ probe ของค่าเดิมล้มเหลว (ต้องยอมให้ webhook ยิง HTTP ออกนอก)
2. **[สังเกต] `.env` เขียนแบบ atomic (`.tmp` + `os.replace`)** — ถ้ามีโปรเซสอื่นอ่าน `.env` พร้อมกันจะเห็นค่าเก่าจนกว่าจะ restart
   (ในทางปฏิบัติ webhook อัปเดต `settings` ในโปรเซสเดียวกันทันที จึงไม่มีผลกับ OTP push)
