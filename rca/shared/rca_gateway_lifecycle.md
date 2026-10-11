# RCA — Gateway Lifecycle (start / restart / shutdown)

> RCA ของ **`app.main:app` (uvicorn gateway)** เอง — ไม่ผูกกับโบรกเกอร์ใด
> (โบรกเกอร์มี RCA แยกตาม `broker_pdca_rca.md` §1)
> เริ่มใช้: **2026-10-08** (เกิดจากการ restart gateway เพื่อโหลด LINE token ใหม่)

---

## GW-RCA-001 (2026-10-08) — `RuntimeError: Expected ASGI message 'http.response.body', but got 'http.response.start'` ตอน shutdown

**Symptom**

ตอน restart gateway (`kill -TERM <uvicorn-pid>`) จะเห็น stack trace 2 ชุดใน log:

```
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  ...
  File ".../uvicorn/protocols/http/httptools_impl.py", line 525, in send
    raise RuntimeError(f"Expected ASGI message 'http.response.body', but got '{message['type']}'.")
RuntimeError: Expected ASGI message 'http.response.body', but got 'http.response.start'.
INFO:     Waiting for application shutdown.
```

**Root Cause Analysis (3 จุด)**

1. **Session & Context**: ขณะนั้นมี **SSE stream ค้างอยู่ 2 เส้น** จาก peer Tailscale
   `100.123.34.50` (`GET /sse` 200 + ชุด `POST /messages/?session_id=...` 202)
   = remote MCP-over-SSE client (cockpit/agent ระยะไกล) กำลังเชื่อมอยู่
2. **DOM & UI Reality**: ไม่ใช่ปัญหา DOM/browser — เป็น **ASGI protocol state**
   เมื่อ uvicorn สั่ง shutdown จะ cancel task ของ request ที่ยาว (SSE) ที่ **response เริ่มไปแล้ว**
   แต่ Starlette `ExceptionMiddleware`/`ServerErrorMiddleware` พยายามตอบ 500
   → ส่ง `http.response.start` ซ้ำบน connection ที่ start ไปแล้ว → uvicorn raise
3. **Data Schema & Types**: ไม่เกี่ยวกับ schema — เป็น **ลำดับเหตุการณ์ (ordering)**
   ระหว่าง lifespan shutdown กับ in-flight long-lived response

**Edge Cases ที่พบ**

- เกิดเฉพาะเมื่อ **มี SSE client ต่ออยู่ตอน shutdown** (mcp-over-sse ที่ `/sse`)
- **ไม่กระทบข้อมูล/ผลลัพธ์**: request ที่มาก่อนหน้าตอบถูกต้องครบ (`200/400/200`) และ
  client ด้านนอก **reconnect อัตโนมัติ** เข้าโปรเซสใหม่ (`GET /sse` 200 อีกครั้ง)
- เกิด **2 ครั้ง = จำนวน SSE stream ที่ค้าง** (2 session) — ไม่ใช่เกิดจาก endpoint ใด endpoint หนึ่ง
- **ไม่ใช่ผลจาก LINE webhook** — พิสูจน์: webhook ในโปรเซสใหม่ (`pid 35752`) ยิง 200/400 ได้
  และ `grep 'ASGI message'` หลังบรรทัด `Started server process [35752]` ได้ **0**

**Proven Working Solution (ขั้นตอน restart ที่ปลอดภัย + พิสูจน์แล้ว 2026-10-08)**

```bash
cd /home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab

# 1) หา pid ที่ถือ port 8000
PID=$(ss -ltnp | grep ':8000' | grep -oP 'pid=\K[0-9]+' | head -1)

# 2) หยุดแบบ graceful (SIGTERM → รัน lifespan shutdown: dispatcher/sentinel/orchestrator หยุดเอง)
kill -TERM "$PID"
for i in $(seq 1 30); do ss -ltn | grep -q ':8000' || break; sleep 0.5; done

# 3) เริ่มใหม่ด้วย cmdline เดิม (cwd = repo root)
setsid nohup .venv/bin/python -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 >> /tmp/homelab_backend.log 2>&1 < /dev/null &

# 4) verify
sleep 8
curl -s http://127.0.0.1:8000/health    # ต้องได้ {"status":"healthy"}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/console  # 200
```

ผลลัพธ์ที่ได้: `port 8000 FREE` ทันที · โปรเซสใหม่ `LISTEN` · `/health` 200 · `/console` 200
· **ไม่มีการยิง OTP/login ใด ๆ ตอนบูต** (lifespan เปิดแค่ dispatcher/sentinel/orchestrator) ✅

**ข้อควรระวังที่ต้องตรวจทุกครั้งก่อน restart**

```bash
# .env ถูกแก้หลังจากโปรเซสเริ่มหรือไม่? ถ้า mtime > start time → token ในหน่วยความจำยังเป็นตัวเก่า
ps -o lstart= -p "$PID"      # เวลาเริ่มโปรเซส
date -r .env '+%F %T'        # เวลาที่ .env ถูกแก้
```

**User Feedback & Context**

ผู้ใช้ทำตามข้อ 1 (reissue LINE token ฝั่ง LINE Console) แล้วขอให้ restart gateway เพื่อโหลด token ใหม่

---

## GW-RCA-002 (2026-10-08) — [OPEN] cloudflared ingress เปิด *ทุก path* → external scanner ยิง `GET /.env`

**Symptom** (พบใน log ระหว่างตรวจหลัง restart)

```
INFO:     167.235.185.190:0 - "GET /.env HTTP/1.1" 404 Not Found
```

**Root Cause Analysis**

- `~/.cloudflared/config.yml` ปัจจุบันผูก **ทั้ง hostname** เข้า backend:
  ```yaml
  ingress:
    - hostname: line.a14s.dev
      service: http://localhost:8000
    - service: http_status:404
  ```
  → ทุก path ของ `line.a14s.dev` (ไม่ใช่แค่ webhook) ถูกส่งเข้า FastAPI
- port `:0` ใน log = `ProxyHeadersMiddleware` เขียน `scope["client"]` จาก `X-Forwarded-For`
  (cloudflared ไม่ส่ง `X-Forwarded-Port`) → ยืนยันว่า request มาจาก **อินเทอร์เน็ตผ่าน tunnel**

**การประเมินความเสี่ยง (ตรวจจริงแล้ว)**

- `GET /.env` → **404**: ไม่มี route และไม่มี static mount ที่เสิร์ฟไฟล์ในเรพอ
  → **ยังไม่มีการรั่วไหลของ credential** ✅
- แต่เป็นการเผยว่า endpoint ถูกสแกน และ path อื่นของ API (`/api/v1/*`, `/console`, `/messages/`)
  ก็เข้าถึงได้จากอินเทอร์เน็ตถ้ารู้ hostname

**Proven Working Solution — ยังไม่ได้ทำ (ต้องให้ผู้ใช้ตัดสินใจ เพราะเปลี่ยนพฤติกรรม tunnel)**

แนวทางที่เสนอ: จำกัด ingress ให้เหลือเฉพาะ webhook path

```yaml
ingress:
  - hostname: line.a14s.dev
    path: /api/v1/webhook/line
    service: http://localhost:8000
  - hostname: line.a14s.dev
    service: http_status:404
```

⚠️ ข้อควรระวังก่อนทำ: `/console` และ `/sse` (mcp-over-sse ที่ `100.123.34.50` ใช้อยู่)
ถูกเรียกผ่าน **Tailscale/127.0.0.1** ไม่ใช่ tunnel — จึงไม่ควรพัง แต่ **ต้องยืนยันกับผู้ใช้**
ว่าไม่มี client ระยะไกลที่พึ่ง tunnel สำหรับ path อื่น

**Edge Cases ที่พบ**

- อย่าใช้ `path` แบบ substring ผิด ๆ (เช่น `/api/v1` เฉย ๆ) เพราะจะเปิดกว้างกว่าที่ตั้งใจ
- ถ้าเพิ่ม ingress hostname อื่นในอนาคต ต้องปิดท้ายด้วย `service: http_status:404` เสมอ
- `LINE_PUBLIC_WEBHOOK_URL` ใน `.env` ต้องตรงกับ hostname+path ที่ประกาศใน ingress

**User Feedback & Context**: ยังไม่แจ้ง — บันทึกไว้เป็น open item และรายงานใน handoff

---

## GW-RCA-003 (2026-10-09) — [RESOLVED] Restart gateway = เบราว์เซอร์ (Playwright/Chromium) ตายทั้ง session ⇒ กู้ด้วย Zero-OTP

**Symptom**

หลังแก้โค้ด driver/endpoint แล้ว restart gateway (ตาม `LINE-RCA-011`) งานที่ต้องใช้เบราว์เซอร์ล้มทันที
ด้วย `No browser page available` / `Browser session not connected` แม้ `/health` จะ 200 และ gateway บูตปกติ

**Root Cause Analysis (3 จุด)**

1. **Process ownership**: Chromium (Playwright) ถูก spawn เป็น **child process ของ gateway** →
   `kill -TERM <gateway pid>` ทำให้ทั้ง process group ตายพร้อมกัน ⇒ in-memory `page`/`context`/cookies หายทั้งหมด
2. **ไฟล์ session ยังอยู่ (ดี) แต่ไม่มีใครโหลดกลับ**: `data/session_state.json` **ไม่ถูกลบ** (Invariant 8 ✅)
   ⇒ Zero-OTP ยังใช้ได้ แต่ต้อง **เรียก resume เอง** หลัง restart
3. **`scripts/start_homelab.py` Stage 2 ปิดเบราว์เซอร์ทิ้ง**: L341–355 เปิดเบราว์เซอร์เพื่อ verify `#dropDownAccountPort`
   แล้วเรียก `auth_driver.close()` ทุกเส้นทาง ⇒ หลังบูตด้วยสคริปต์นี้ gateway **ยังไม่มี page** (ต้อง login/resume เอง)

**Proven Working Solution (พิสูจน์สด 2026-10-09 15:22 → 15:24, ไม่เผา OTP)**

```bash
# 1) restart ตาม GW-RCA-001 (graceful SIGTERM → setsid nohup uvicorn app.main:app)
# 2) ยืนยันว่าโค้ดใหม่มีผลจริง (LINE-RCA-011)
ps -o lstart= -p "$(ss -ltnp | grep ':8000' | grep -oP 'pid=\K[0-9]+' | head -1)"  # ต้องใหม่กว่า mtime ของ source
# 3) กู้ session แบบ Zero-OTP (ไม่ยิง SMS OTP):
curl -s -X POST http://127.0.0.1:8000/api/v1/session/login \
     -H 'Content-Type: application/json' -d '{"force_fresh": false}'
# → {"resumed": true, "otp_ref": null, "status": "AUTHENTICATED"}
```

- `force_fresh:false` ⇒ โหลด storage state จาก `data/session_state.json` และ **ไม่ push คำขอ OTP**
- ถ้า **ไม่** ได้ `resumed:true` (ไฟล์หมดอายุจริง) จึงค่อยใช้เส้นทาง headed login + OTP ผ่าน LINE relay
  — และต้องผ่าน gate `otp_relay_readiness.check()` ก่อนเสมอ (Invariant 9)

**Edge Cases ที่พบ**

- **ห้ามลบ `data/session_state.json`** ระหว่างกู้ session (Invariant 8) — ไฟล์นี้คือบัตรผ่าน Zero-OTP
- การ restart ตัด **browser เท่านั้น** ไม่ได้ตัด SSE/LINE webhook (คนละเรื่องกับ GW-RCA-001)
- ถ้าไม่ resume หลัง restart แล้วไปเรียก driver ตรง ๆ จะได้ error ที่อ่านคล้าย "หน้าเว็บผิด" แต่จริง ๆ คือ "ไม่มี page"

**User Feedback & Context**: ลำดับ "restart → Zero-OTP resume" ผ่านจริง 1 รอบเต็มโดยไม่ต้องใช้ OTP
(ยืนยันว่าไม่ใช่ข้อสันนิษฐาน — มีหลักฐาน response `resumed:true`)

---

## Zero-Contradiction checklist (อัปเดตทุกครั้งที่แก้)

- [x] ขั้นตอน restart ด้านบน = คำสั่งที่ **รันจริงและผ่าน** (2026-10-08 15:14)
- [x] ระบุชัดว่า GW-RCA-001 เป็น **noise ตอน shutdown** ไม่ใช่ error ของ request
- [ ] GW-RCA-002 (จำกัด ingress path) — **รอผู้ใช้ตัดสินใจ** ยังไม่แก้ `~/.cloudflared/config.yml`
- [x] GW-RCA-003 (restart → browser ตาย → **ต้อง** `POST /api/v1/session/login {force_fresh:false}`) — พิสูจน์สด 2026-10-09 15:22–15:24
