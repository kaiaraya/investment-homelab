# RCA — LINE Group OTP Relay (shared channel)

> ไฟล์นี้เป็น RCA ของ **ช่องทาง OTP ที่ใช้ร่วมกันทุกโบรกเกอร์** (LINE group `a14s homelab`)
> ไม่ใช่ RCA ของโบรกเกอร์ใดโบรกเกอร์หนึ่ง — โบรกเกอร์ยังมี RCA แยกของตัวเอง
> (`rca/krungsri/`, `rca/liberator/`, `rca/click2win/`) ตาม `broker_pdca_rca.md` §1
>
> เริ่มใช้: **2026-10-08** (แทน `rca/shared/rca_kdeconnect_bridge.md` ซึ่งถูกทำเป็น dormant)

---

## LINE-RCA-001 (2026-10-08) — LINE Console "Verify" ได้ HTTP 400 (webhook ถูกมองว่าพัง)

**Symptom**
ใน LINE Developers Console กด **Verify** ที่ Webhook URL `https://line.a14s.dev/api/v1/webhook/line`
→ console ขึ้น error / ไม่ผ่านการตรวจสอบ

**Root Cause Analysis (3 จุด)**
1. **Session & Context**: tunnel ถูกต้อง (`cloudflared` → `:8000`) ไม่ใช่ปัญหา tunnel
2. **DOM & UI Reality**: ปุ่ม Verify ของ LINE ยิง `POST` ด้วย **body ว่าง** (`b""`) แต่มี
   `X-Line-Signature` ที่ถูกต้อง (HMAC ของสตริงว่าง)
3. **Data Schema & Types**: `webhook_line.py` เรียก `json.loads(body_bytes.decode())` บนสตริงว่าง
   → `JSONDecodeError` → `HTTPException(400)` → console ตีความว่า webhook ใช้งานไม่ได้
   (ทั้งที่ endpoint ทำงานถูกต้องสำหรับ event จริง)

**Edge Cases ที่พบ**
- `body_bytes.strip()` ต้องเป็นตัวเช็ค (ไม่ใช่ `len(body_bytes) == 0`) เพราะบาง proxy ส่ง whitespace มา
- ต้อง verify signature **ก่อน** คืน 200 เพื่อไม่เปิดช่องให้คนอื่นยิง endpoint เปล่า ๆ
- signature ของ body ว่าง = `base64(HMAC_SHA256(channel_secret, b""))` — verify ได้ตามปกติ

**Proven Working Solution**
```python
body_bytes = await request.body()

# 1) verify signature (ครอบ empty probe ด้วย)
if not verify_line_signature(body_bytes, x_line_signature):
    raise HTTPException(status_code=400, detail="Invalid LINE signature")

# 2) LINE Console verify ping — ตอบ 200 ก่อน parse
if not body_bytes.strip():
    logger.info("[LINE] Webhook verify ping received (empty body) — acknowledged 200.")
    return {"status": "ok", "processed": 0, "results": [], "note": "verify_ping"}
```
พิสูจน์สด: local + tunnel `https://line.a14s.dev` → `HTTP 200 {"status":"ok","note":"verify_ping"}`;
signature ผิด → `HTTP 400` (ถูกต้อง)

**User Feedback & Context**
ผู้ใช้ระบุว่า webhook เดิมยิงไม่ผ่านและต้องการให้ใช้ `app.main:app` (ตัวใหม่) เท่านั้น —
`python -m app.mcp.mcp_server` (ตัวเก่า) ถูกยกเลิกการใช้งานแล้ว

**Tests**: `tests/test_webhook_line.py::test_line_webhook_verify_ping_empty_body`

---

## LINE-RCA-002 (2026-10-08) — OTP ที่ส่งในกลุ่มไม่ถูกนำไปใช้ (cross-process path พังเงียบ)

**Symptom**
ผู้ใช้พิมพ์รหัส OTP 6 หลักตอบในกลุ่ม LINE แล้ว แต่ `auth_driver` ยังรอจน timeout
(180s) แล้ว `OTP_TIMEOUT` — เกิดเฉพาะเมื่อ login ถูกสั่งจาก **CLI** (`daily_readiness.py`)
ไม่เกิดเมื่อสั่งผ่าน REST API ในโปรเซสเดียวกัน

**Root Cause Analysis (3 จุด)**
1. **Session & Context Isolation**: webhook รันใน uvicorn (process A) แต่ CLI login รันใน
   process B → `event_bus.otp_queue` (in-memory) ใช้ข้ามโปรเซสไม่ได้ →
   ต้องอ่านผ่าน SQLite `session_logs` แทน ซึ่งเป็น fallback ที่มีอยู่แล้ว
2. **DOM & UI Reality**: ไม่เกี่ยวกับ DOM — เป็นเรื่อง IPC
3. **Data Schema & Types**: regex ที่อ่าน row ไม่ตรงกับข้อความที่ระบบเขียนจริง
   - เขียนจริง: `"Received OTP 6-digits from LINE: 849201 (Ref: BIPE)"`
   - regex เดิม: `r"Received (?:SMS )?OTP(?:\s*6-digits)?:\s*([0-9]{6})"` → ต้องการ `:`
     ต่อท้าย `6-digits` ทันที แต่ของจริงมี ` from LINE` คั่น → **ไม่ match** → เงียบ ๆ ไม่เจอ OTP

**Edge Cases ที่พบ**
- รูปแบบข้อความของแต่ละช่องทางไม่เหมือนกัน (`... from LINE:` vs `... OTP:`)
- `re.search` ต้องทน infix ได้ แต่ห้ามกว้างจนไปแมตช์ log อื่น (จำกัดด้วย `event_type`
  `IN ("LINE_OTP_RECEIVED","KDECONNECT_OTP_RECEIVED")` อยู่แล้ว)

**Proven Working Solution**
```python
# app/browser/auth_driver.py — SINGLE SOURCE OF TRUTH
OTP_SESSION_LOG_PATTERN = r"Received[^:]*OTP[^:]*:\s*([0-9]{6})"
```
ใช้ร่วมกันโดย `auth_driver._wait_for_otp_multi_channel()` และ
`liberator_driver` (§LINE group relay) — ไม่มีสำเนา regex ที่สอง

**User Feedback & Context**
โหมดใช้งานจริงคือสั่ง `daily_readiness.py` จาก terminal → เส้นทาง CLI ต้องได้
จึงต้องแก้ให้ครบ ไม่ใช่แก้เฉพาะ path ที่ทดสอบผ่าน API

**Tests**: `tests/test_otp_relay_readiness.py::test_otp_pattern_matches_line_session_log_row`
(+ `_kde_session_log_row`, `_ignores_non_otp_details`)

---

## LINE-RCA-003 (2026-10-08) — ต้องมี groupId ก่อนจึงจะ push หาเป้าหมายได้

**Symptom**
`push_message()` ทำงานแบบ **broadcast** แทนที่จะส่งเข้ากลุ่ม เพราะ `LINE_GROUP_ID` ว่าง
(`LINE_ADMIN_USER_ID` ก็ว่าง) — ข้อความกระจายไปยังผู้ติดตามบอททุกคน แทนที่จะเข้ากลุ่มที่ต้องการ

**Root Cause Analysis (3 จุด)**
1. **Session & Context**: LINE Messaging API ไม่มี endpoint ให้ "list groups" — ระบบไม่มีทาง
   รู้ groupId ล่วงหน้า ต้องรอ event จากกลุ่มเข้ามาก่อน
2. **DOM & UI Reality**: LINE Console ไม่แสดง groupId ของกลุ่มที่บอทอยู่
3. **Data Schema & Types**: event ที่มาจากกลุ่มมี `source.type == "group"` และมี
   `source.groupId` (ขึ้นต้นด้วย `C`) — โค้ดเดิมไม่อ่าน field นี้เลย

**Edge Cases ที่พบ**
- ต้องไม่เขียนทับ `LINE_GROUP_ID` ที่ผู้ใช้ตั้งเองไว้ (operator-set ต้องชนะเสมอ)
- ต้องอัปเดตค่าในโปรเซสที่กำลังรันทันที (ไม่ต้อง restart uvicorn)
- ถ้าเขียน `.env` ไม่ได้ (permission) ต้องไม่ทำให้ webhook ล้ม
- ข้อความจากกลุ่มถูก process เหมือนข้อความ 1:1 (ไม่มีการกรอง `source.type`) → OTP relay ทำงานได้เลย

**Proven Working Solution**
ทำ *zero-touch onboarding* ใน `webhook_line.py`: อ่าน `source.groupId` จากทุก event →
ถ้า `settings.LINE_GROUP_ID` ว่าง ให้ set ในโปรเซส + เขียนลง `.env` แบบ atomic

```python
for event in events:
    source = event.get("source") or {}
    if source.get("groupId"):
        _persist_group_id(source["groupId"])   # set in-process + .env (ถ้ายังว่าง)
```
และ `push_message()` เลือกเป้าหมายตามลำดับ:
`to_user_id` → `settings.LINE_GROUP_ID` → `settings.LINE_ADMIN_USER_ID` → broadcast

**ขั้นตอนของผู้ใช้ (ทำครั้งเดียว)**
1. เชิญบอท `a14s homelab` (`@678clhio`) เข้ากลุ่ม LINE
2. พิมพ์ข้อความใดก็ได้ 1 ครั้งในกลุ่ม
3. ตรวจ `.env` → จะมี `LINE_GROUP_ID=C...` เพิ่มมาเอง แล้วรัน
   `.venv/bin/python scripts/daily_readiness.py` → ต้องได้ `✅ relay พร้อม (channel=line_group)`

**User Feedback & Context**
ผู้ใช้เลือกเลิกใช้เมนู Service บนมือถือทั้งหมด (ไม่มี A/B/C/D) — ต้องการให้ LINE group
เป็นศูนย์กลางเดียวของ OTP

**Tests**: `tests/test_webhook_line.py::test_line_webhook_captures_group_id`,
`tests/test_line_otp_group.py::test_push_message_targets_group`,
`tests/test_otp_relay_readiness.py::test_gate_ready_with_line_group_and_gateway`

---

## LINE-RCA-004 (2026-10-08) — Verify ผ่านแล้วแต่ `LINE_GROUP_ID` ยังว่าง (แยกไม่ออกจาก log)

**Symptom**

ผู้ใช้กด **Verify** ที่ LINE Console → ขึ้น **success** และเชิญบอทเข้ากลุ่มแล้ว
แต่ `otp_relay_readiness.check()` ยังได้ `ready=false / LINE_GROUP_ID not set`
และ `.env` ยังไม่มี `LINE_GROUP_ID`

**Root Cause Analysis (3 จุด)**

1. **Session & Context**: ไม่ใช่ tunnel/signature — ตรวจ log พบ `POST /api/v1/webhook/line`
   → **200 OK 2 ครั้ง** จาก **IP ของ LINE เอง** (`147.92.149.170`, `147.92.149.165`)
   = คำขอ Verify ของ Console มาถึงจริงและผ่าน
2. **DOM & UI Reality (ของจริงคือ payload)**: payload ที่ Console Verify ส่งคือ
   `{"destination":"U...","events":[]}` — มี **events ว่าง** (ไม่ใช่ body ว่าง)
   โค้ดเดิม: `events=[]` → ลูป capture ไม่ทำอะไร → `process_webhook_events(db, [])`
   → คืน 200 **โดยไม่ log อะไรเลย** → ใน log จึงดูเหมือน "ไม่มีอะไรเข้ามา"
   ทำให้แยกไม่ออกระหว่าง "Verify ผ่าน" กับ "มี event กลุ่มเข้ามาแล้ว"
3. **Data Schema & Types**: ไม่มี event ที่มี `source.groupId` เข้ามาเลย
   (ไม่มี log `[LINE] source.groupId observed:`) → **`join` event ของการเชิญบอท
   ไม่ได้ถูกส่ง/บันทึก** เช่น อาจเกิดตอน webhook ยังตอบ 400 (LINE-RCA-001) หรือ
   ยังไม่ได้เปิดสวิตช์ **"Use webhook"** ใน Console

**Edge Cases ที่พบ**

- LINE Verify มี **2 รูปแบบ**: body ว่างเปล่า (LINE-RCA-001) และ `{"events":[]}` ← รูปแบบจริง
- `join` event (บอทถูกเชิญเข้ากลุ่ม) **มี `source.groupId`** → ต้องจับทันที ไม่ต้องรอข้อความแรก
- ต้องตอบ 200 กับ `join` ด้วย ไม่งั้น LINE จะ retry / ตีว่าติดลบ
- การ log **ห้าม log id/เนื้อความ** ของ event (privacy) → log แค่ `type` เท่านั้น

**Proven Working Solution**

```python
events = payload.get("events", [])

# 2b) Verify payload = {"events":[]} → ตอบ 200 + log ให้เห็น (เดิมเงียบสนิท)
if not events:
    logger.info("[LINE] Webhook acknowledged with 0 events (LINE Console verification / keep-alive).")
    return {"status": "ok", "processed": 0, "results": [], "note": "verify_ping"}

# observability: บอกว่า event อะไรเข้ามา (ไม่ log id/ข้อความ)
logger.info(f"[LINE] Received {len(events)} event(s): {[e.get('type') for e in events]}")

# 3) capture groupId จาก "ทุก" event (รวม join) ก่อนประมวลผล
for event in events:
    source = event.get("source") or {}
    if source.get("groupId"):
        _persist_group_id(source["groupId"])
```

พิสูจน์สด 2026-10-08 15:36 (restart → pid 38313):
ยิง `{"destination":"U_test","events":[]}` + signature จริง ผ่าน tunnel
→ `HTTP 200 {"note":"verify_ping"}` และ log ขึ้น
`[LINE] Webhook acknowledged with 0 events (LINE Console verification / keep-alive).` ✅

**Tests**: `tests/test_webhook_line.py::test_line_webhook_verify_ping_empty_events`,
`tests/test_webhook_line.py::test_line_webhook_join_event_captures_group_id`

**User Feedback & Context**

ผู้ใช้แจ้งว่า "กด Verify → success" และ "บอทเข้ากลุ่มแล้ว" แต่ตอนนั้นยังไม่มี event
จากกลุ่มเข้ามาเลย → ต้องมี **ข้อความ 1 ครั้งในกลุ่ม** (หรือ `join` event ที่ยังไม่ถูกส่ง)
จึงจะ capture groupId ได้ — พร้อมให้ตรวจสวิตช์ **"Use webhook" = ON** ใน Messaging API settings
ด้วย เพราะถ้าปิดอยู่ LINE จะไม่ส่ง event จริงเลย (แต่ Verify ยังผ่านได้)

### LINE-RCA-004 addendum (2026-10-08 15:44–15:48) — ต้นตอจริง: ข้อความถูกส่งใน **แชท 1:1** ไม่ใช่ในกลุ่ม

หลังเปิด `Use webhook = ON` + ผู้ใช้ส่ง `Hi` → มี event เข้ามาจริงแล้ว:

```
2026-10-08 15:44:28,182 [INFO] webhook_line: [LINE] Received 1 event(s): ['message']
INFO:  147.92.149.165:0 - "POST /api/v1/webhook/line HTTP/1.1" 200 OK
```

แต่ **`.env` ยังไม่มี `LINE_GROUP_ID`** และ **ไม่มี log `[LINE] source.groupId observed:`**
→ วิเคราะห์ได้ว่า event นั้น **ไม่มี `source.groupId`** = ข้อความถูกพิมพ์ใน **แชท 1:1 กับบอท**
(`source.type="user"`) ไม่ใช่ในกลุ่ม (`source.type="group"`)

**แก้เพิ่ม (observability ปิดช่องว่างสุดท้าย):** เพิ่ม `source.type` เข้า log

```python
summary = [{"type": e.get("type"), "source": (e.get("source") or {}).get("type")} for e in events]
logger.info(f"[LINE] Received {len(events)} event(s): {summary}")
```

พิสูจน์สด 15:48 (pid 39923) ด้วย event ที่ไม่มีผลข้างเคียง (`type=follow` → handler ไม่ประมวลผล):
`[LINE] Received 1 event(s): [{'type': 'follow', 'source': 'user'}]` ✅

**อ่านผลยังไง (กฎวินิจฉัย):**

| log ที่เห็น | แปลว่า |
|-------------|--------|
| `[{'type': 'message', 'source': 'group'}]` + `source.groupId observed: C...` | ✅ ถูกต้อง → capture สำเร็จ |
| `[{'type': 'message', 'source': 'user'}]` | ❌ พิมพ์ใน **แชท 1:1** กับบอท → ต้องไปพิมพ์ใน**กลุ่ม** |
| ไม่มี log `[LINE]` เลย (มีแต่ 200 OK) | payload `{"events":[]}` = Console Verify/keep-alive |
| ไม่มี request เข้ามาเลย | ❌ `Use webhook` ปิด อยู่ หรือ webhook URL ไม่ตรง |

**Tests เพิ่ม**: `test_line_webhook_1to1_message_does_not_capture_group_id`
(1:1 ต้อง **ไม่** set `LINE_GROUP_ID` — กัน OTP ไปลงผิดที่แบบเงียบ ๆ) → **7 passed**
**Restart**: pid `38313` → **`39923`** (15:47) · `/health` 200

---

## LINE-RCA-005 (2026-10-08) — เชิญบอทเข้ากลุ่มไม่ได้ เพราะ `Allow bot to join group chats` ปิดอยู่ (LINE default)

**Symptom**

ผู้ใช้เข้าใจว่าบอทเข้ากลุ่มแล้ว แต่เมื่อตรวจสอบจริง **บอทไม่ได้อยู่ในกลุ่ม**
→ LINE ไม่ส่ง event จากกลุ่ม (`source.groupId`) มาให้เลยตลอดทั้ง session
→ `LINE_GROUP_ID` ยังว่าง → `otp_relay_readiness.check()` = `ready=false`

**Root Cause Analysis (3 จุด)**

1. **Session & Context**: webhook/tunnel/token ทำงานครบแล้ว (Verify ผ่าน, event 1:1 เข้าถึงจริง)
   → ตัดปัจจัยด้าน session/tunnel ออกได้ทั้งหมด
2. **DOM & UI Reality (ของจริงคือสถานะฝั่ง LINE)**: บอท **ไม่ได้เป็นสมาชิกของกลุ่ม**
   → LINE Platform **ไม่สร้าง** event ที่มี `source.groupId` ให้ (ทั้ง `join` และ `message`)
   พิสูจน์ด้วย log: `[LINE] Received 1 event(s): [{'type': 'message', 'source': 'user'}]`
   = event ที่เข้ามาเป็น **1:1** (`source.type="user"`) ไม่ใช่กลุ่ม (`group`) และไม่มี `join` event เลย
3. **Data Schema & Types / Platform constraint**: เอกสาร LINE ระบุชัด —
   > *"To be invited, go to LINE Developers Console > Messaging API tab of your channel and
   > enable **Allow bot to join group chats**. **This setting is disabled by default.**"*
   > *"At any time, **only one LINE Official Account can be in a group chat**."*

   → **ต้นตอแท้จริง**: สวิตช์นี้ปิด (ค่า default) ทำให้ OA `@678clhio` **ถูกเชิญเข้ากลุ่มไม่ได้**
   อาการจึงดูเหมือน "webhook พัง" ทั้งที่เป็นข้อจำกัดของแพลตฟอร์ม

**Edge Cases ที่พบ**

- `Allow bot to join group chats` = **disabled by default** → ต้องเปิด *ก่อน* เชิญ (เปิดทีหลังก็ใช้ได้)
- 1 กลุ่มมี OA ได้ **แค่ตัวเดียว** → ถ้ามี OA อื่นอยู่แล้ว เชิญตัวเราเพิ่มจะไม่สำเร็จ
- บอทไม่อยู่ในกลุ่ม = **ไม่มี event กลุ่มส่งมาเลย** (ไม่ใช่ "ส่งมาแล้ว parse ไม่ได้") → อย่าไปแก้ parser
- LINE Verify ผ่านได้ **แม้บอทไม่อยู่ในกลุ่มใด ๆ** → Verify ไม่ใช่หลักฐานว่าออนบอร์ดดิ้งสำเร็จ
- `source.type` ใน log คือตัวชี้ขาด: `user` = 1:1 · `group` = กลุ่ม · `room` = multi-person

**Proven Working Solution (ขั้นตอนที่ต้องทำ — ฝั่งผู้ใช้/Console)**

1. LINE Developers Console → channel (Messaging API) → แท็บ **Messaging API**
   → หัวข้อ group chats → **`Allow bot to join group chats`** → กด **Edit → Enable**
2. เปิดแอป LINE → เข้ากลุ่ม **`a14s homelab`** → เมนูกลุ่ม (☰ / ชื่อกลุ่ม) → **Invite (เชิญ)**
   → ค้นหา OA **`@678clhio`** (a14s homelab) → เชิญเข้ากลุ่ม
   - ถ้าค้นไม่เจอ ให้เพิ่ม OA เป็นเพื่อนก่อน แล้วเชิญจากรายชื่อเพื่อน
   - ถ้าเชิญไม่ได้ ให้ตรวจว่ากลุ่มมี OA อื่นอยู่แล้วหรือไม่ (ได้แค่ 1 ตัว)
3. ส่งข้อความ 1 ครั้งในกลุ่ม → LINE จะส่ง event `join` + `message` พร้อม `source.groupId`
   → ระบบจะ log `[LINE] source.groupId observed: C...` และเขียน `LINE_GROUP_ID` ลง `.env` ให้เอง (**ไม่ต้อง restart**)
4. ยืนยัน: `.venv/bin/python scripts/daily_readiness.py` → ต้องได้ `✅ relay พร้อม (channel=line_group)`

**ผลข้างเคียงถ้าต้องการ 1:1 แทนกลุ่ม** — ✅ **ดำเนินการแล้ว (ไม่ต้องอนุมัติเพิ่ม): ดู `LINE-RCA-006`**

ผู้ใช้ยืนยัน *"บอทไม่ได้อยู่ในกลุ่ม"* และอนุมัติ **Path B** ⇒ ใช้แชท 1:1 (`channel=line_direct`)
เป็นช่องทาง OTP แทนกลุ่มไปก่อน (implementation + เทสต์ + เอกสาร อยู่ใน `LINE-RCA-006`)
ถ้าวันหลังเปิด `Allow bot to join group chats` + เชิญ OA เข้ากลุ่มสำเร็จ
`LINE_GROUP_ID` จะกลับมามี precedence เหนือทันทีโดยไม่ต้องแก้โค้ดซ้ำ

**⚠️ Clarification (จากคำถามผู้ใช้ 2026-10-08 15:58) — "เพิ่มเพื่อน OA" ≠ "บอทอยู่ในกลุ่ม"**

ผู้ใช้รายงาน: *"add OA `@678clhio` แล้ว และมีสมาชิก 1 คน คือผม — ต้อง add bot ยังไง"*
→ สิ่งที่ทำคือ **เพิ่มเพื่อน OA = ได้แชท 1:1** (หน้า member list ของแชทเดี่ยวจะโชว์แค่ผู้ใช้เอง)
→ **บอทยังไม่ได้เป็นสมาชิกของ "กลุ่ม" ใด ๆ** จึงไม่มี event `source.type="group"` เลย → ถูกต้องตาม RCA นี้

**เงื่อนไขที่ต้องมีครบก่อน OA จะอยู่ในกลุ่มได้ (LINE บังคับ)**

| # | เงื่อนไข | หมายเหตุ |
|---|----------|----------|
| 1 | LINE Developers Console → แท็บ Messaging API → `Allow bot to join group chats` = **Enabled** | **default = Disabled → เชิญไม่สำเร็จ/ไม่เจอ OA ในช่องค้นหา** |
| 2 | มี **กลุ่ม LINE** จริง (ต้องมีเพื่อนมนุษย์ ≥1 คน — LINE ไม่ให้สร้างกลุ่มที่มีแค่ตัวเอง) | แชท 1:1 กับ OA ไม่นับเป็นกลุ่ม |
| 3 | เชิญ OA เข้ากลุ่มจากเมนูกลุ่ม → **Invite** → ค้น `@678clhio` | 1 กลุ่มมี OA ได้แค่ **1 ตัว** |
| 4 | ส่งข้อความ 1 ครั้งในกลุ่ม | LINE จะส่ง `join` + `message` พร้อม `source.groupId` |

**ทางเลือก B (ใช้แชท 1:1 เป็น push target) — ✅ IMPLEMENTED 2026-10-08 → `LINE-RCA-006`**

- `app/services/line_service.py:1429` → `user_id = to_user_id or settings.LINE_GROUP_ID or settings.LINE_ADMIN_USER_ID`
- `app/services/line_service.py:1508` → `target = settings.LINE_GROUP_ID or settings.LINE_ADMIN_USER_ID`
- LINE push API รับ `to` = userId **หรือ** groupId **หรือ** roomId ได้ทั้งสามแบบ
- 2 จุดที่เคยขาด **แก้แล้ว**: (1) `webhook_line.py` auto-capture `source.userId` ของแชท 1:1
  → `LINE_ADMIN_USER_ID` (เฉพาะ `source.type=="user"`) และ (2) `otp_relay_readiness` ผ่อน gate
  ให้ผ่านด้วย `LINE_GROUP_ID` **หรือ** `LINE_ADMIN_USER_ID` (channel `line_direct`)
- precedence ยังเป็นของกลุ่มเสมอ: มี groupId เมื่อไหร่ `channel` กลับเป็น `line_group` ทันที

**สถานะค่าจริงตอนนี้ (ตรวจแล้ว, ไม่เปิดเผยค่า):** `LINE_GROUP_ID=EMPTY` ·
`LINE_ADMIN_USER_ID=EMPTY (auto-capture ได้ทันทีเมื่อพิมพ์ในแชท 1:1)`
· `LINE_SIMULATION_MODE=False` · `LINE_PUBLIC_WEBHOOK_URL=https://line.a14s.dev/api/v1/webhook/line`

**User Feedback & Context**

ผู้ใช้ยืนยันเองว่า **"บอทไม่ได้อยู่ในกลุ่ม"** หลังผมรายงานว่า event ที่เข้ามาเป็น source=user
→ ยืนยันว่า RCA ถูกต้อง และยืนยันคุณค่าของการเพิ่ม log `source.type` (ถ้าไม่มี log นี้จะเดาผิด)
— บทเรียน: **"ผู้ใช้บอกว่าทำแล้ว" ไม่เท่ากับ "สถานะจริงเป็นเช่นนั้น" → ต้องมีหลักฐานจาก log เสมอ (Anti-Mock)**

---

## LINE-RCA-006 (2026-10-08) — OTP relay ใช้ **แชท 1:1** ได้ (Path B) หลังยืนยันว่าบอทไม่ได้อยู่ในกลุ่ม

**Incident ID & Date:** `LINE-RCA-006 (2026-10-08)`

**Symptom**

- ผู้ใช้ยืนยัน *"บอทไม่ได้อยู่ในกลุ่มครับ"* → เงื่อนไขของ `LINE-RCA-005` ยังไม่ครบ (สวิตช์ group chats ปิด)
- webhook รับ event เป็น `source: user` (แชท 1:1) เท่านั้น → ไม่มี `groupId` ให้จับ
- `LINE_GROUP_ID` + `LINE_ADMIN_USER_ID` ว่างทั้งคู่ → `otp_relay_readiness.check()` = `ready=false`
  → `daily_readiness.py` = **NO-GO** และ **ห้ามยิง SMS OTP** (Invariant 9) ⇒ Krungsri / Liberator re-login ไม่ได้เลย
- **แต่** OTP ที่พิมพ์ในแชท 1:1 *มาถึงระบบแล้ว*: `line_service._handle_text_message()` →
  `extract_otp_from_text()` **ไม่ผูกกับ groupId** → `event_bus.publish_otp(OTPSource.LINE_CHAT)`
  ⇒ อาการคือ "ระบบใช้ OTP ได้ แต่ gate ไม่ยอมเปิด" (gate เข้มกว่าความจริง)

**Root Cause Analysis (3 จุด)**

1. **Session & Context**: session / tunnel / webhook / token ทำงานครบ (LINE Verify ผ่าน, event 1:1 เข้าถึงจริง)
   → ตัดปัจจัย session/cookie ออกได้
2. **DOM & UI Reality (สถานะจริงฝั่ง LINE platform)**: OA ถูกเพิ่มเป็น **เพื่อน** (1:1 chat) เท่านั้น
   และ **เชิญเข้ากลุ่มไม่ได้** จนกว่าจะเปิด `Allow bot to join group chats` (LINE-RCA-005)
   ⇒ ถ้ายังยึด gate เดิม (`LINE_GROUP_ID` เท่านั้น) ระบบจะ **NO-GO ตลอดกาล** ทั้งที่ช่องทาง 1:1 ใช้ได้จริง
3. **Data Schema & Types (จุดเจาะจง)**: event ของแชท 1:1 ส่ง
   `source = {"type": "user", "userId": "U..."}` และ **ไม่มี** `groupId`
   ⇒ โค้ดเดิม capture เฉพาะ `source["groupId"]` → **ข้อมูลมีอยู่ แต่ไม่มีใครเก็บ**
   ⇒ และแม้เก็บได้ ก็ยังติด gate ที่บังคับ `LINE_GROUP_ID` → ต้องแก้ **2 จุดพร้อมกัน** ไม่ใช่จุดเดียว

**Edge Cases ที่พบ**

- event ของ **กลุ่ม** ก็มี `source.userId` (ของสมาชิกที่พิมพ์) → `elif source["type"] == "user"` บังคับ
  ไม่ให้เก็บ userId จากกลุ่ม (ไม่งั้น OTP จะถูก push ไปแชทส่วนตัวของสมาชิกคนอื่น)
- `source.type` เป็นตัวชี้ขาด: `user` = 1:1 · `group` = กลุ่ม · `room` = multi-person
- `LINE_GROUP_ID` ต้องมี **precedence** เหนือ `LINE_ADMIN_USER_ID` เสมอ (1:1 ห้ามแย่งช่องทางกลุ่ม)
- ค่าที่ operator ตั้งใน `.env` **ห้าม**ถูกเขียนทับด้วยค่า auto-capture
- เขียน `.env` ต้อง atomic (`.tmp` + `os.replace`) และ **ห้าม** ทำให้ webhook ตอบไม่ 200 ถ้าเขียนไฟล์พัง
- channel `line_direct` **ไม่ผ่อน** Invariant 9 — gateway `:8000` ต้อง listen เหมือนเดิม
- LINE push API รับ `to` = userId / groupId / roomId ⇒ `line_service.push_message()` ไม่ต้องแก้

**Proven Working Solution**

1. `app/api/v1/endpoints/webhook_line.py`
   - แยกตัวเขียน `.env` เป็น `_write_env_key(key, value)` (atomic, never-fail — ใช้ร่วมทั้ง 2 key)
   - เพิ่ม `_persist_user_id(user_id)` + `_last_seen_user_id` — เรียก **เฉพาะ** `source.type == "user"`
   - loop capture:
     ```python
     source = event.get("source") or {}
     if source.get("groupId"):
         _persist_group_id(source["groupId"])
     elif source.get("type") == "user" and source.get("userId"):
         _persist_user_id(source["userId"])
     ```
2. `app/services/otp_relay_readiness.py`
   - เพิ่ม `CHANNEL_LINE_DIRECT = "line_direct"`
   - `target_id = LINE_GROUP_ID or LINE_ADMIN_USER_ID`; gate ผ่านเมื่อ `target_id` มีค่า (+ token + simulation + gateway)
   - `channel = line_group` ถ้ามี groupId, ไม่งั้น `line_direct`
   - เพิ่ม `details`: `line_direct_id_configured` / `line_direct_id` / `line_target_kind`
3. **ไม่ต้อง restart gateway** — `settings` ถูกอัปเดตในโปรเซสเดียวกับ webhook ทันที

**Live steps (ผู้ใช้ทำครั้งเดียว ~30 วินาที)**

1. เปิดแชท 1:1 กับ OA `@678clhio` (a14s homelab) → พิมพ์ข้อความใดก็ได้ (เช่น `hi`)
2. ดู log gateway: `[LINE] source.userId observed (1:1 chat): U...`
   + `[LINE] LINE_ADMIN_USER_ID captured into .../.env (OTP push target locked in).`
3. ยืนยัน: `.venv/bin/python scripts/daily_readiness.py` → `✅ relay พร้อม (channel=line_direct)`

**หลักฐานการทดสอบ (2026-10-08)**

- `.venv/bin/python -m pytest tests/test_webhook_line.py tests/test_otp_relay_readiness.py -q` → **22 passed**
- regression (`tests/` ที่แตะ LINE/relay/webhook/daily_readiness ทั้งหมด) → **92 passed**

**User Feedback & Context**

- ผู้ใช้แจ้ง *"บอทไม่ได้อยู่ในกลุ่ม ครับ"* → ยืนยัน RCA-005 และ **อนุมัติ Path B** (ใช้ 1:1 แทนกลุ่ม)
- บทเรียนที่ต้องคงไว้: **"ผู้ใช้บอกว่าทำแล้ว" ≠ "สถานะจริงเป็นเช่นนั้น"** → ต้องมีหลักฐานจาก log เสมอ (Anti-Mock)
- และบทเรียนที่ 2: เมื่อ *ความจริงของแพลตฟอร์ม* (1:1 ใช้ได้) **กว้างกว่า** ที่ gate บังคับ → gate ต้องผ่อนให้ตรงความจริง
  ไม่ใช่ปล่อยให้ระบบ NO-GO ตลอดกาลแล้วรอผู้ใช้ไปแก้ฝั่ง LINE

---

## LINE-RCA-007 (2026-10-08) — gate ขึ้น `ready=true` ทั้งที่ push ส่งไม่ได้ (false-GO) → OTP ตายเงียบ

**Incident ID & Date**: LINE-RCA-007 (2026-10-08 16:11–16:40)

**Symptom**
- `scripts/daily_readiness.py` รายงาน **`✅ relay พร้อม`** แต่บรรทัดถัดมาคือ
  `⚠️ ส่งข้อความยืนยันไม่สำเร็จ` และ log `line_service.push_message` เป็น
  `[LINE API] Push error response: {"message":"Failed to send messages"}`
- พร้อมกันนั้น login Krungsri จะ **ยิง SMS OTP ทิ้ง** แล้วค้างรอ OTP ที่ไม่มีทางมาถึง

**Root Cause Analysis (RCA)**
1. **`LINE_GROUP_ID` ที่มีค่า = ไม่ได้แปลว่า "ส่งถึง"** — `.env` มี format ถูกต้อง
   (`C` + hex 32 ตัว = 33 chars) แต่ LINE API ตอบ:
   - `GET /v2/bot/group/{id}/summary` → **404 `{"message":"Not found"}`**
   - `POST /v2/bot/message/push` → **`{"message":"Failed to send messages"}`**
2. **ไทม์ไลน์จริงจาก `/tmp/homelab_backend.log` (หลักฐานชี้ขาด)**

   | เวลา | event | ผล |
   |---|---|---|
   | 15:48:18 | `follow` (user) | ผู้ใช้แอด OA เป็นเพื่อน |
   | 15:51:02 | `message` (user) | ส่งข้อความในแชท 1:1 (โค้ดขณะนั้นยังไม่มี `_persist_user_id`) |
   | 16:11:18 | **`join` (group)** | บอทถูกเชิญเข้ากลุ่ม → capture `LINE_GROUP_ID=Ccd…` ลง `.env` ✅ |
   | **16:12:27** | **`leave` (group)** | **บอทออก/ถูกนำออกจากกลุ่ม** (ก่อนหน้า 0.1 วิ มี `memberLeft`) |

   ⇒ ค่าใน `.env` **ไม่ผิดตอนที่เขียนลง** — มันกลายเป็น "เป้าหมายตาย" หลังจากบอทออกจากกลุ่ม
3. **gate เดิมเช็คแค่ "มีค่าไหม"** (`target_id = group or direct`) ⇒ `ready=true` ตลอดไป
   ทั้งที่ปลายทาง 404 = **false-GO** ซึ่งทำลาย Invariant 9 (ห้ามยิง SMS OTP ถ้า relay ไม่พร้อม)

**Edge Cases ที่พบ**
- group "มี id + บอทออกแล้ว" ≠ group "มี id + บอทอยู่" → แยกได้ด้วย API probe เท่านั้น
- ถ้า fallback ไป 1:1 เมื่อกลุ่มเสีย → **ยังเป็น false-GO อีกทาง** เพราะ
  `line_service.push_message()` ยังยิงเข้า `LINE_GROUP_ID` ก่อนเสมอ (precedence ต่างจาก gate)
  ⇒ gate ต้อง **fail-closed** ให้ตรงกับ target ที่ driver ใช้จริง (Zero-Contradiction)
- probe ต้องไม่ throw (เน็ตหลุด/timeout = unreachable) และห้ามพ่น token ลง log

**Proven Working Solution 1 — LINE deliverability probe (fail-closed)**

```python
# app/services/otp_relay_readiness.py
async def _probe_target(target_id: str, token: str, timeout: float = 6.0) -> tuple[bool, str]:
    if not target_id:
        return False, "target not set"
    if target_id.startswith("C"):      # groupId
        url = f"https://api.line.me/v2/bot/group/{target_id}/summary"
    elif target_id.startswith("R"):    # roomId
        url = f"https://api.line.me/v2/bot/room/{target_id}/summary"
    else:                              # userId (1:1)
        url = f"https://api.line.me/v2/bot/profile/{target_id}"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        return (True, "reachable") if resp.status_code == 200 else (False, f"HTTP {resp.status_code}: {resp.text[:90]}")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
```

ใน `check()` — probe **ก่อน** เปิด gate และ **ไม่ fallback** เมื่อกลุ่มที่ตั้งไว้ส่งไม่ได้:

```python
if group_id:
    reachable, probe_detail = await _probe_target(group_id, token)
    details["line_group_reachable"] = reachable
    details["line_group_probe"] = probe_detail
    if reachable:
        return OtpRelayReadiness(ready=True, channel=CHANNEL_LINE_GROUP, ...)
    reason = f"LINE group push target not deliverable — group {group_id[:3]}… {probe_detail} (…)"
elif direct_id:
    reachable, probe_detail = await _probe_target(direct_id, token)
    ...
```

**หลักฐานสด (2026-10-08)** — verdict เปลี่ยนจาก "โกหก" เป็น "จริง":

```
READY   : False
CHANNEL : none
REASON  : LINE group push target not deliverable — group Ccd… HTTP 404: {"message":"Not found"}
DETAILS : ... "line_group_reachable": false, "gateway_up": true,
          "line_group_probe": "HTTP 404: {\"message\":\"Not found\"}"
```

`scripts/daily_readiness.py --no-login` → **`⛔ relay DOWN — login ใหม่จะถูกยกเลิก (ห้ามยิง SMS OTP)`** ✅

---

## LINE-RCA-008 (2026-10-08) — target ตายถาวรเพราะไม่มี lifecycle release (`leave` / `unfollow`)

**Incident ID & Date**: LINE-RCA-008 (2026-10-08 16:12:27 เป็นต้นมา)

**Symptom**
- `.env` ค้าง `LINE_GROUP_ID=Ccd…` ของกลุ่มที่บอทออกไปแล้ว → ทุก push ล้มเหลว (`Failed to send messages`)
- และเพราะ write-guard คือ "เขียนเฉพาะเมื่อยังว่าง" → **ไม่มีทาง self-heal** แม้บอทจะเข้าใหม่

**Root Cause Analysis (RCA)**
1. ลูปเดิมเรียก `_persist_group_id(source["groupId"])` **กับทุก event ที่มี groupId**
   → event `leave` / `memberLeft` ก็ถูกจับด้วย (ถ้า `.env` ว่างตอนนั้น จะล็อกเป้าหมายที่เพิ่งออกไปทันที)
2. ไม่มีโค้ด **เคลียร์** ค่าเลย → `LINE_GROUP_ID` เก่าค้าง = poisoned target ถาวร
3. `_last_seen_group_id` ไม่ถูกรีเซ็ต ⇒ เข้า/ออก/เข้ากลุ่มเดิมซ้ำ ๆ จะไม่ถูก capture อีก

**Edge Cases ที่พบ**
- `memberLeft` = *สมาชิกคนอื่น* ออก (ไม่เกี่ยวกับ OA) → ห้าม capture **และ**ห้าม release
- release เฉพาะเมื่อ id ที่แจ้ง **ตรงกับค่าที่เราตั้งอยู่** (operator ตั้งกลุ่มอื่นไว้ = ห้ามแตะ)
- `unfollow` = ผู้ใช้บล็อก OA → แชท 1:1 หายจริง → ต้อง release `LINE_ADMIN_USER_ID` ด้วย
- ห้ามสำรอง `.env` เป็นไฟล์อื่นเพื่อ "กันพลาด" (ผิดกฎห้ามคัดลอก credential) → ล้างเป็น `KEY=` แทน

**Proven Working Solution 2 — lifecycle release (self-healing)**

```python
# app/api/v1/endpoints/webhook_line.py
GROUP_RELEASE_EVENTS = {"leave"}      # OA ออก/ถูกนำออกจากกลุ่ม
USER_RELEASE_EVENTS = {"unfollow"}    # ผู้ใช้บล็อก OA

def _release_group_id(group_id: str) -> None:
    global _last_seen_group_id
    if not group_id or settings.LINE_GROUP_ID != group_id:
        return
    settings.LINE_GROUP_ID = None
    _last_seen_group_id = None           # ให้ re-join กลุ่มเดิมถูก capture ใหม่ได้
    _write_env_key("LINE_GROUP_ID", "")  # เขียน KEY= (ว่าง) แบบ atomic

# ในลูป event:
if event_type in GROUP_RELEASE_EVENTS and group_id:
    _release_group_id(group_id)
elif event_type in USER_RELEASE_EVENTS and source.get("type") == "user" and user_id:
    _release_user_id(user_id)
elif event_type == "memberleft":
    continue                             # คนอื่นออก ไม่เกี่ยวกับ OA
elif group_id:
    _persist_group_id(group_id)
elif source.get("type") == "user" and user_id:
    _persist_user_id(user_id)
```

**Live steps ที่ทำไปแล้ว (2026-10-08)**

1. ล้างค่าเก่าใน `.env` → `LINE_GROUP_ID=` (ค่าที่พิสูจน์แล้วว่า 404)
2. รีสตาร์ท gateway: `kill <pid>` แล้ว
   `nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/homelab_backend.log 2>&1 &`
   → `/health` = `{"status":"healthy"}` ✅
3. หลังล้าง: gate = `ready=False / channel=none` reason *"LINE_GROUP_ID / LINE_ADMIN_USER_ID not set"* (ซื่อสัตย์ ✅)
4. ให้ผู้ใช้ส่งข้อความ 1:1 กับ OA (`@678clhio`) 1 ครั้ง → **ทำแล้ว 16:44:56** ✅

**ผลลัพธ์หลัง self-healing (live proof 2026-10-08 16:44–16:46)**

```
16:44:56 [LINE] Received 1 event(s): [{'type': 'message', 'source': 'user'}]
16:44:56 [LINE] source.userId observed (1:1 chat): U…
16:44:56 [LINE] LINE_ADMIN_USER_ID captured into …/.env (OTP push target locked in).

$ awk … .env
LINE_GROUP_ID     -> 0 chars (EMPTY)     ← ค่า poisoned ถูกปล่อยไปแล้ว
LINE_ADMIN_USER_ID-> 33 chars (SET)      ← target ใหม่ที่ probe ผ่าน

$ .venv/bin/python scripts/daily_readiness.py --no-login
✅ FastAPI Gateway is UP on port 8000.
✅ relay พร้อม (channel=line_direct) — 1:1 chat with the OA + gateway up
✅ ส่งข้อความยืนยันเข้าแชท LINE แล้ว
```

- `line_service.push_message()` คืน `True` **เฉพาะเมื่อ LINE API ตอบ HTTP < 400** (`resp.status_code >= 400` → log error + คืน False)
  ⇒ บรรทัด "ส่งข้อความยืนยัน…แล้ว" = หลักฐานการส่งจริงจาก API ไม่ใช่ mock (เทียบกับก่อนแก้ที่ขึ้น "ไม่สำเร็จ" + `Failed to send messages`)
- `push_message` resolve target เป็น `LINE_GROUP_ID or LINE_ADMIN_USER_ID` → เมื่อกลุ่มว่างจึงยิง 1:1 **ตรงกับที่ gate ตัดสิน** (Zero-Contradiction)
- เหลือ human confirm ฝั่งผู้ใช้ว่าเห็นข้อความ `✅ [a14s homelab] OTP relay พร้อม …` ในแชทจริง

**หลักฐานการทดสอบ (2026-10-08)**

- `tests/test_otp_relay_readiness.py` (+3 เทสต์ใหม่: probe endpoint mapping C/R/U, 404 → NO-GO, fail-closed แม้มี 1:1)
  และ `tests/test_webhook_line.py` (+5 เทสต์ lifecycle: leave เคลียร์ / leave กลุ่มอื่นไม่แตะ / memberLeft ไม่จับ-ไม่เคลียร์ /
  unfollow เคลียร์ / re-join หลัง leave ถูก capture ซ้ำ) → **30 passed**
- regression (`-k 'line or relay or webhook or readiness'`) → **59 passed**

**User Feedback & Context**

- เป้าหมายผู้ใช้: *"ทำให้ OTP relay ทำงานได้โดยไม่ต้องให้บอทอยู่ในกลุ่ม"* → Path B (1:1) คือคำตอบ
  และ RCA นี้คือเหตุผลว่าทำไม "1:1 ต้องชนะได้อย่างปลอดภัย" ไม่ใช่แค่เพิ่ม fallback เปล่า ๆ
- บทเรียน: **ข้อมูลที่เคยถูกต้อง อาจกลายเป็นเท็จได้ตามเวลา** → ทุก "เป้าหมายปลายทาง" ต้องมี
  **liveness check** และต้องมี **lifecycle event** ที่ถอนสิทธิ์ได้ (ไม่ใช่ set-once)

---

## LINE-RCA-010 (2026-10-08) — OTP ของ Liberator ถูกป้ายเป็น Krungsri + `Ref: N/A` **และ row ไปลง DB ผิดลูก (OTP ไม่ถึง driver)**

**Symptom**
รัน `scripts/daily_readiness.py` (19:47) → push `[LINE OTP REQUEST] broker=Liberator WebTrade ref=ANBA`
→ ผู้ใช้พิมพ์รหัส 6 หลักตอบในแชท 1:1 เวลา 19:48:09 → webhook ตอบ 200 **แต่**:
1. `liberator_driver.login()` ยังรอจน `TIMEOUT (180s)` — OTP ไม่ถึง driver เลย
2. reply ขึ้น *"กำลังยืนยันตัวตนกับ **Krungsri Securities**... (Ref: **N/A**)"*

**Root Cause Analysis (3 จุด)**
1. **Session & Context**: relay/gateway ปกติ (`channel=line_direct`, push สำเร็จ) — ไม่ใช่ปัญหา session
2. **DOM & UI Reality**: ไม่เกี่ยวกับ DOM — เกิดที่ชั้น persistence/routing
3. **Data Schema & Types — ต้นตอจริง 3 ข้อ**
   - **(fatal) DB ผิดลูก** — `webhook_line.py` ใช้ `Depends(get_db)` และ
     `get_db(platform=None)` → `get_session_factory(None)` อ่าน `settings.TRADING_PLATFORM`
     ซึ่งใน `.env` = `CLICK2WIN` → ได้ `AsyncSessionClick2Win` → เขียน `LINE_OTP_RECEIVED` ลง
     **`investment_homelab_click2win.db`** ขณะที่ **driver ทุกตัวอ่าน `AsyncSessionLocal`
     (primary `investment_homelab.db`)** → มองไม่เห็น row → timeout
     หลักฐาน: row กำพร้าใน sandbox DB `id=26 LINE_OTP_RECEIVED` `"…922412 (Ref: N/A)"` @ 12:48:09 UTC
   - **(attribution) hardcode โบรกเกอร์** — ACK ใน `line_service._handle_text_message` ฝังข้อความ
     "Krungsri Securities" และ `ref_code = otp_extract.ref or auth_driver.current_ref`
     ซึ่ง `auth_driver.current_ref` เป็นของ **Krungsri เท่านั้น** → ref `ANBA` ของ Liberator ถูกทิ้ง → `N/A`
   - **(multi-broker) ไม่มี marker** — ไม่มีข้อมูลว่าคำขอล่าสุดเป็นของโบรกเกอร์ใด
     ⇒ ทั้งสอง driver poll `LINE_OTP_RECEIVED` ก้อนเดียวกัน = cross-consumption ได้

**Edge Cases ที่พบ**
- `TRADING_PLATFORM` มีผลกับ **webhook** ด้วย ทั้งที่ช่องทาง LINE เป็น "ช่องทางของกลาง" (broker-agnostic)
  → **ห้ามใช้ platform-aware session กับ relay เด็ดขาด**
- `event_bus` เป็น **in-process** — driver ที่รันคนละโปรเซส (CLI / `daily_readiness.py`) เห็นได้แค่ **DB path**
- row เก่าที่ไม่มี tag `(Broker: X)` (legacy / KDE) ต้องยังใช้ได้ → ตัวกรองต้อง **lenient** ไม่ใช่ fail-closed
- marker ต้องมี **TTL** ไม่เช่นนั้น OTP ที่พิมพ์ช้า ๆ จะไปผูกกับคำขอเก่า (ใช้ 300s > 180s ของ OTP wait)

**Proven Working Solution**
- โมดูลใหม่ `app/services/otp_relay_registry.py` = single source of truth ของ relay persistence
  - **pin primary DB** ผ่าน lazy import `from app.db.session import AsyncSessionLocal` (ไม่ผ่าน `get_db()`)
  - `record_request(broker, ref, ttl)` → marker `OTP_REQUESTED` (broker+ref) **ก่อน** push
  - `resolve_pending_request(ttl=300)` → **latest-request-wins**
  - `record_otp_received(otp, ref, broker)` → row `LINE_OTP_RECEIVED` + tag `(Broker: X)`
  - `broker_matches(expected, actual)` → untagged = ยอมรับ, tag ต่างโบรกเกอร์ = ปฏิเสธ
- `line_service.push_otp_request()` → เรียก `record_request()` ก่อน `push_message()` และใช้ `broker_label()`
  จาก registry (ลบ dict `broker_labels` ที่ซ้ำออก — Zero-Contradiction) + ถ้อยคำ "ตอบในกลุ่มนี้/แชทนี้" ตาม channel จริง
- ACK อ่าน `resolve_pending_request()` → ระบุชื่อโบรกเกอร์จริง (**ไม่มี hardcode**) และไม่ขึ้น `N/A` เมื่อ marker มี ref
- ทั้ง `auth_driver` (KRUNGSRI) และ `liberator/driver.py` (LIBERATOR) กรอง row:
  `if not broker_matches(driver_broker, row_broker): ignore` — ทั้ง Check-1 (in-process queue) และ Check-2 (DB)
- `OTPPayload` เพิ่มฟิลด์ `broker: Optional[str]` (backward-compatible) + `details` ของ row
  ยังเข้า `OTP_SESSION_LOG_PATTERN` เดิม (ต่อท้าย tag เท่านั้น จึงไม่พัง channel-gated wait)

**หลักฐานการทดสอบ (2026-10-08)**
- `tests/test_otp_multibroker_attribution.py` (ใหม่, **18 passed**) — DB pinning, round-trip marker,
  latest-request-wins, TTL stale, ACK ของ Liberator **ไม่มีคำว่า "Krungsri"** + ref `ANBA`,
  **webhook write → channel-gated driver wait อ่านได้จริง** (เดิม timeout), cross-broker refusal
  ทั้งสองทิศ, และ Zero-Contradiction guard ว่า driver ทั้งคู่ต่อตัวกรองตัวเดียวกัน
- bundle (11 ไฟล์: otp/line/liberator/session/homelab) → **106 passed**
- คำสั่ง: `.venv/bin/python -m pytest tests/test_otp_multibroker_attribution.py -q`

**User Feedback & Context**
- ผู้ใช้ยืนยันแนวทาง **latest-request-wins** (ไม่ต้องมี UI ให้เลือกโบรกเกอร์) เพราะ `daily_readiness.py`
  รันทีละโบรกเกอร์อยู่แล้ว — คำขอล่าสุดคือคำขอที่ถูกต้อง
- บทเรียน: **(1)** "ช่องทางของกลาง" (relay) ห้ามผูกกับ platform/session ของโบรกเกอร์ใดโบรกเกอร์หนึ่ง
  **(2)** ข้อความ ACK ต้อง derive จากข้อมูลจริง (marker) ไม่ใช่ค่าคงที่ในโค้ด

---

## LINE-RCA-011 (2026-10-08) — แก้โค้ดแล้วแต่ relay ยังใช้โค้ดเก่า (stale gateway process)

**Incident ID & Date**: LINE-RCA-011 (2026-10-08 20:53 +07 ตอนรัน D2 live verification)

**Symptom**: หลัง "แก้" LINE-RCA-010 เสร็จ (โค้ดบนดิสก์แก้แล้ว + unit tests ผ่าน) การทดสอบ D2 รอบแรก
ผู้ใช้พิมพ์ OTP 6 หลักในแชท LINE 1:1 → reply 200 → แต่ row `LINE_OTP_RECEIVED` **ไปลง sandbox DB**
(`investment_homelab_click2win.db` id=31) พร้อม `(Ref: N/A)` และไม่มี `(Broker: …)` — **อาการเหมือนบั๊กเดิมทุกประการ**
แม้โค้ดที่ควรจะแก้จะถูกเขียนไปแล้วก็ตาม

**Root Cause Analysis (RCA)**:
- `otp_relay_registry.py` (pin primary DB) และ `line_service.py` (marker + broker attribution) ถูกสร้าง/แก้เวลา
  **20:08:39** และ **20:11:00** (+07) แต่ process gateway (`uvicorn app.main:app`, pid 32713) **เริ่มตอน 19:45:03** (+07)
- uvicorn รัน **โดยไม่มี `--reload`** → Python โหลดโมดูลเข้า memory ครั้งเดียวตอน import
  ⇒ โค้ดที่รันอยู่เป็น **รุ่นก่อนแก้** ตลอด (แก้บนดิสก์ ≠ แก้ที่รันอยู่)
- ฝั่งผู้เรียก (driver ในโปรเซส `daily_readiness.py`) เป็นโปรเซสใหม่ → ฝั่งนั้นใหม่ แต่ฝั่ง webhook (gateway) เก่า
  ⇒ "โค้ดครึ่งเดียวใหม่" = อาการหลอกที่ดูเหมือนบั๊กเดิมกลับมา

**Edge Cases ที่พบ**:
- **ครึ่งเดียวใหม่**: driver (โปรเซสใหม่) อ่าน primary แต่ gateway (โปรเซสเก่า) เขียน sandbox → ต้องเช็ค **ทุกโปรเซสที่ร่วมวง**
  ไม่ใช่แค่ไฟล์โค้ด
- mtime ของ `.pyc` ไม่ใช่หลักฐานของโค้ดที่รันอยู่ (ถูก compile ใหม่ได้จากโปรเซสอื่น/เทสต์) — ต้องใช้
  **เวลา start ของ process เทียบกับ mtime ของ source**
- `TRADING_PLATFORM=CLICK2WIN` ใน `.env` ยังคงเป็นตัวขยายผล (platform-aware `get_db()` → sandbox)
  — เป็นเหตุให้อาการเด่นชัด ไม่ใช่ต้นตอ

**Proven Working Solution**:
```bash
# 1) ตรวจว่า process เก่ากว่าโค้ดหรือไม่ (2 หลักฐานอิสระ)
ps -o pid,lstart,etime,cmd -p <uvicorn_pid>
stat -c '%y  %n' app/services/line_service.py app/services/otp_relay_registry.py

# 2) restart gateway ให้โหลดโค้ดล่าสุด
kill <uvicorn_pid>
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/gateway.log 2>&1 &

# 3) ยืนยันด้วยเส้นทางจริง (ไม่ใช่การเดา) — D2 บน primary DB
sqlite3 investment_homelab.db \
  "SELECT id,event_type,created_at,details FROM session_logs WHERE event_type IN
   ('OTP_REQUESTED','LINE_OTP_RECEIVED','LOGIN_SUCCESS') ORDER BY id DESC LIMIT 5;"
```
ผลหลัง restart: `LINE_OTP_RECEIVED … (Ref: USTT) (Broker: KRUNGSRI)` → `LOGIN_SUCCESS` @ `trademan.in.th/Portfolio`
และ `(Ref: VDLQ) (Broker: LIBERATOR)` ตามลำดับ (ดู handoff `TASK-otp-channel-authoritative.md` §D2 Live Verification)

**User Feedback & Context**:
- ผู้ใช้สั่งรัน D2 จริง (ไม่ mock) — การทดสอบจริงคือสิ่งที่เปิดโปง stale process ที่ unit test จับไม่ได้
- บทเรียน: **"โค้ดเขียนแล้ว + test ผ่าน" ≠ "ระบบที่รันอยู่แก้แล้ว"** → ต้อง restart แล้วยืนยันด้วยหลักฐานจาก DB จริง
  · Go/No-Go gate ที่เชื่อถือได้คือ `scripts/daily_readiness.py` (แตะเส้นทางจริง) ไม่ใช่ความเชื่อจาก diff

---


## Zero-Contradiction checklist (อัปเดตทุกครั้งที่แก้)
- [x] **restart gateway หลังแก้โค้ดทุกครั้ง (LINE-RCA-011)** — `uvicorn app.main:app` รันโดยไม่ใช้ `--reload`;
  **แก้บนดิสก์ ≠ แก้ที่รันอยู่** → ต้อง restart แล้วยืนยันด้วย row จริงใน primary DB ก่อนเริ่มทดสอบ
- [x] `app/services/otp_relay_registry.py` **(ใหม่ — LINE-RCA-010)** — persist relay ลง **primary DB เท่านั้น**
  (`AsyncSessionLocal` ไม่ผ่าน platform-aware `get_db()`) · marker `OTP_REQUESTED` (broker+ref, **latest-request-wins**,
  TTL 300s) · row `LINE_OTP_RECEIVED` + tag `(Broker: X)` · `broker_matches()` สำหรับตัวกรองรายโบรกเกอร์
- [x] `app/services/line_service.py` — `push_otp_request()` เขียน marker **ก่อน** push + ใช้ `broker_label()` จาก registry
  **+ ACK ของ OTP ใช้ broker/ref จาก marker (ไม่มี "Krungsri Securities" hardcode)**
- [x] `app/browser/auth_driver.py` + `app/brokers/liberator/driver.py` — กรอง `LINE_OTP_RECEIVED` ด้วย tag โบรกเกอร์
  (Check-1 queue + Check-2 DB) · untagged (legacy/KDE) = ยอมรับ
- [x] `app/api/v1/endpoints/webhook_line.py` — empty-body verify ping + groupId capture
  **+ `userId` (1:1) capture → `LINE_ADMIN_USER_ID` (LINE-RCA-006)**
  **+ lifecycle release: `leave` → เคลียร์ `LINE_GROUP_ID` · `unfollow` → เคลียร์ `LINE_ADMIN_USER_ID` · `memberLeft` = ไม่จับ/ไม่เคลียร์ (LINE-RCA-008)**
- [x] `app/services/otp_relay_readiness.py` — **gate เดียว** ที่ทุกฝ่ายเรียกใช้ **(+ channel `line_direct`, precedence กลุ่ม > 1:1)**
  **+ `_probe_target()` liveness probe (C→`group/summary`, R→`room/summary`, U→`profile`) และ fail-closed เมื่อกลุ่มที่ตั้งไว้ 404 (LINE-RCA-007)**
- [x] `tests/test_webhook_line.py` + `tests/test_otp_relay_readiness.py` — เทสต์ 1:1 / precedence / ไม่เก็บ userId จากกลุ่ม / ไม่ทับค่าที่ operator ตั้ง
  **+ lifecycle (`leave`/`unfollow`/`memberLeft`/re-join) + probe mapping + 404 → NO-GO**

**รายการเดิม (ตรวจซ้ำแล้วยังจริง — 2026-10-08)**
- [x] `app/core/config.py` — `LINE_GROUP_ID`, `LINE_PUBLIC_WEBHOOK_URL`, `LINE_OTP_RELAY_ENABLED`
- [x] `app/services/line_service.py` — group target + `push_otp_request()`
- [x] `app/services/otp_relay_readiness.py` — **gate เดียว** ที่ทุกฝ่ายเรียกใช้
- [x] `app/browser/auth_driver.py` — gate KDE → LINE + push OTP request + regex fix
- [x] `app/brokers/liberator/driver.py` — poll LINE group (event bus + DB) + push OTP request
- [x] `scripts/daily_readiness.py` — bridge check → LINE relay
- [x] `scripts/start_homelab.py` — Stage 1 → LINE relay (+ ensure gateway) + `--keep-open`
- [x] `directive/kdeconnect.md` — §2/§4 กลับด้าน + superseded banner
- [x] `AGENTS.md`, `.agents/skills/daily-readiness/SKILL.md` — อัปเดตถ้อยคำ
- [x] `rca/shared/rca_kdeconnect_bridge.md` — เพิ่มป้าย dormant
