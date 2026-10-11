# TASK-otp-channel-authoritative: LINE = OTP channel หลัก (KDE dormant จริง) + `otp_source` ที่ซื่อสัตย์

- Created: 2026-10-08 by Cline (Act mode) — ต่อจาก `docs/handoff/TASK-line-otp-group-relay.md`
- Broker: Krungsri TradeMan + Liberator (แยกองค์ความรู้ต่อโบรกเกอร์ — Broker Knowledge Isolation)
- Status: ✅ DONE — D2 live-verified 2026-10-08 (Krungsri + Liberator `AUTHENTICATED` ผ่าน LINE 1:1 จริง; ดู §D2 Live Verification)

## Context (root cause — มีหลักฐานจาก DB จริง)

**Symptom:** re-login 2026-10-08 17:05–17:06 (`OTP_REQUIRED` Ref `SMEG` → `LOGIN_SUCCESS` ใน ~35s)
**ไม่มี** `LINE_OTP_RECEIVED` และ **ไม่มี** `KDECONNECT_OTP_RECEIVED` row ใน `session_logs` เลย
→ พิสูจน์ไม่ได้ว่า OTP มาจากช่องทางไหน (เสียเจตนารมณ์ "LINE เป็น channel หลัก")

**Root cause (อ่านโค้ดจริง):**
1. `app/browser/auth_driver.py` → `_wait_for_otp_multi_channel()` **Check-3** (L636–649)
   เรียก `kdeconnect_service.poll_active_notifications()` **ทุก 0.5 วินาทีแบบไม่ gate ตาม channel**
   → คืน `"kdeconnect_direct"` ชนะ race ก่อนที่ LINE/DB จะถูกอ่าน (และไม่เขียน DB row ใด ๆ)
2. `Check-2` (L612–634) query `event_type IN ("KDECONNECT_OTP_RECEIVED","LINE_OTP_RECEIVED")`
   **รวมทั้งสองช่องทางเสมอ** → ไม่สะท้อน channel ที่ gate อนุมัติไว้ (Zero-Contradiction)
3. `app/brokers/liberator/driver.py` `login()` **ไม่มี `otp_relay_readiness.check()` เลย**
   และ OTP loop (L373) poll KDE แบบไม่มีเงื่อนไข → **bug class เดียวกัน**
4. `LoginResult` ไม่มีฟิลด์ `otp_source` → ไม่มีทางตรวจย้อนหลังได้ว่าจับ OTP จาก LINE จริง

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/otp_relay_readiness.py` (เพิ่ม helper บริสุทธิ์ 3 ตัว)
- `app/schemas/auth.py` (`LoginResult.otp_source`)
- `app/browser/auth_driver.py` (gate + capture source)
- `app/brokers/liberator/driver.py` (gate + capture source)
- `tests/test_otp_channel_authoritative.py` (ไฟล์ใหม่)
- docs: `rca/shared/rca_line_otp_group.md`, `directive/kdeconnect.md`, `.agents/skills/daily-readiness/SKILL.md`, `AGENTS.md`, handoff นี้

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify | Status |
|---|----------------------------|------------------|--------|--------|
| A1 | `otp_relay_readiness`: เพิ่ม helper บริสุทธิ์ `channel_allows_kde()`, `channel_db_event_types()`, `channel_accepts_source()` | ฟังก์ชัน pure คืนค่าตาม channel (line_* → ไม่มี KDE) | `pytest tests/test_otp_channel_authoritative.py -q` → passed | ✅ |
| A2 | `LoginResult.otp_source: Optional[OTPSource] = None` | ฟิลด์ใหม่ backward-compatible | `pytest tests/test_type_safe_auth.py -q` → passed | ✅ |
| A3 | `auth_driver.login()`: เก็บ `readiness.channel` แล้วส่งเข้า `_wait_for_otp_multi_channel(channel=...)` | signature ใหม่ ไม่มี caller อื่นพัง | `pytest tests/test_browser_auto_reconnect.py -q` → passed | ✅ |
| A4 | `_wait_for_otp_multi_channel`: Check-2 gate event types ตาม channel (+ คืน source จาก event_type จริง); Check-3 ข้ามถ้า channel ≠ kde_connect | ขณะ `channel=line_*` **ไม่มีการเรียก** `poll_active_notifications()` | unit test: patch poll แล้ว assert not called → passed | ✅ |
| A5 | `LoginResult(..., otp_source=...)` ตอน success + `_log_event` ระบุ source | `otp_source` = `line_chat` (ไม่ใช่ kde) | unit test ✅ · live = D2 (⬜) | ✅ (unit) |
| B1 | Liberator `login()`: เพิ่ม `otp_relay_readiness.check()` ก่อน submit credential | relay ไม่พร้อม → `BRIDGE_DOWN` **ไม่ยิง SMS** | `pytest tests/test_liberator_session.py -q` → passed | ✅ |
| B2 | Liberator OTP loop: gate KDE poll ตาม channel + capture `otp_source` | ไม่ poll KDE ขณะ channel = line_* | unit test (mock) → passed | ✅ |
| C1 | เขียน `LINE-RCA-009` + Zero-Contradiction อัปเดตเอกสาร (§Scope ด้านบน) | เอกสารไม่ขัดกับโค้ดจริง | grep + อ่านเทียบโค้ด | ✅ |
| D1 | ผู้ใช้ un-pair KDE บนมือถือ → re-login ผ่าน `scripts/daily_readiness.py` | มี row `LINE_OTP_RECEIVED` + `otp_source=line_chat` | DB query + human confirm | ✅ **(ครอบคลุมโดย D2)** — LINE ใช้จริง + `KDECONNECT_OTP_RECEIVED` คงที่ 209 (ไม่มี KDE capture) |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python -m pytest tests/test_otp_channel_authoritative.py tests/test_type_safe_auth.py tests/test_browser_auto_reconnect.py tests/test_liberator_session.py tests/test_otp_relay_readiness.py -q`
- Subset เต็ม (อนุมัติแล้ว): `test_webhook_line.py test_line_otp_group.py test_daily_readiness.py test_auth_session_nondestructive.py test_krungsri_session_health.py test_session_drop_detection.py test_kdeconnect_service.py test_start_homelab_stages.py`

## Gate C/D — multi-broker attribution + DB pinning (`LINE-RCA-010`, 2026-10-08)

### RCA จริง (มีหลักฐานจาก DB)
- **Symptom:** daily_readiness รัน 19:47 → Liberator push `[LINE OTP REQUEST] broker=Liberator WebTrade ref=ANBA` →
  ผู้ใช้พิมพ์รหัส 6 หลักตอน 19:48:09 → reply 200 → แต่ Liberator `TIMEOUT (180s)` **และ** reply ขึ้น
  "กำลังยืนยันตัวตนกับ **Krungsri Securities**... (Ref: **N/A**)"
- **Root cause 1 (fatal — OTP ไม่ถึง driver):** `webhook_line.py:170` ใช้ `Depends(get_db)` ซึ่ง platform-aware
  → `TRADING_PLATFORM=CLICK2WIN` → เขียน `LINE_OTP_RECEIVED` ลง **sandbox DB**
  `investment_homelab_click2win.db` (id=26 `… 922412 (Ref: N/A)` @ 12:48:09 UTC) ขณะที่ driver ทุกตัวอ่าน
  **primary DB** (`investment_homelab.db`) ผ่าน `AsyncSessionLocal` → row มองไม่เห็น → timeout
- **Root cause 2 (attribution ผิด):** ACK hardcode "Krungsri Securities" + `ref` อ่านจาก `auth_driver.current_ref`
  เท่านั้น → OTP ของ Liberator ถูกป้ายเป็น Krungsri + `Ref: N/A`
- **Root cause 3 (ไม่มี multi-broker):** ไม่มี marker ว่าคำขอล่าสุดเป็นของโบรกเกอร์ใด → ทั้งสอง driver poll row เดียวกัน

### การตัดสินใจ (user, 2026-10-08)
- **latest-request-wins** — marker คำขอล่าสุดภายใน TTL (300s) เป็นตัวกำหนดโบรกเกอร์ (เรียบง่าย ตรงกับ daily_readiness ที่รันทีละตัว)

### Steps / Task Decomposition

| # | Atomic Step | Expected Outcome | Verify | Status |
|---|-------------|------------------|--------|--------|
| A1 | สร้าง `app/services/otp_relay_registry.py` — pure parsers/formatters + helpers ที่ **pin primary DB** (lazy import) | helper ใช้ได้, pure funcs deterministic | `.venv/bin/python -m pytest tests/test_otp_multibroker_attribution.py -q` → **18 passed** | ✅ |
| B1 | `OTPPayload.broker: Optional[str]` (backward-compatible) | ฟิลด์ใหม่ไม่ทำ test เดิมพัง | `pytest tests/test_type_safe_auth.py -q` → passed | ✅ |
| B2 | webhook OTP branch → `resolve_pending_request()` → broker-aware payload + ACK ที่ไม่ hardcode | ACK ใช้ label จริง; row ลง **primary DB** | unit test + sqlite query | ✅ |
| B3 | `line_service.push_otp_request()` เขียน marker `OTP_REQUESTED` (primary) ก่อน push + ใช้ `broker_label()` จาก registry | marker มี `broker=`/`ref=` | unit test | ✅ |
| C1 | Liberator `login()` Check-2: กรอง row ด้วย `(Broker: X)` (legacy ไม่มี tag = ยอมรับ) | row ของโบรกเกอร์อื่นถูก ignore | unit test + source guard | ✅ |
| C2 | `auth_driver._wait_for_otp_multi_channel()` Check-2: กรองแบบเดียวกัน | เหมือน C1 | unit test (`test_krungsri_driver_ignores_a_liberator_tagged_row`) | ✅ |
| D1 | Zero-Contradiction: `AGENTS.md`, `.agents/skills/daily-readiness/SKILL.md`, `rca/shared/rca_line_otp_group.md` (+LINE-RCA-010), `directive/kdeconnect.md`, handoff นี้ | docs ไม่ขัดกับโค้ดจริง | อ่านเทียบโค้ด (kdeconnect.md ไม่มีเนื้อหาขัด → ไม่แก้) | ✅ |
| D2 | live re-run Gate D — Liberator fresh login ผ่าน LINE 1:1 | มี `LINE_OTP_RECEIVED` (primary) + `otp_source=line_chat` + 2 brokers `AUTHENTICATED` | DB query + human confirm | ✅ **(verified live 2026-10-08 14:00–14:03 UTC — ดู §D2 Live Verification)** |

## D2 Live Verification — LINE เป็น OTP channel หลักจริง (2026-10-08 20:53–21:03 +07 / 13:53–14:03 UTC)

### สภาพแวดล้อมที่ทดสอบ (ยืนยันก่อนเริ่ม — Invariant 7)
- gateway: `app.main:app` (uvicorn `:8000`) — **restart ใหม่ 20:56:41 +07** เพื่อให้โค้ดล่าสุดมีผลจริง (ดู LINE-RCA-011)
- relay channel: **`line_direct`** (แชท 1:1 กับ OA `@678clhio`) เพราะ `LINE_GROUP_ID` ว่าง
  (บอทออกจากกลุ่ม → self-heal เคลียร์ค่า ตาม LINE-RCA-008) · `LINE_ADMIN_USER_ID` (33 ตัว) ผ่าน `_probe_target()` = 200
- primary DB: `investment_homelab.db` · sandbox: `investment_homelab_click2win.db`
- ก่อน D2: `LINE_OTP_RECEIVED` = **0** และ `OTP_REQUESTED` = **0** ใน primary (baseline สะอาด)

### หลักฐาน (อ่านจาก primary DB แบบ read-only; mask เลข OTP แล้ว)
| id | เวลา (UTC) | event_type | details |
|----|-----------|------------|---------|
| 1482 | 14:00:33 | `OTP_REQUESTED` | `broker=KRUNGSRI ref=USTT ttl=180s` |
| 1483 | 14:00:50 | `LINE_OTP_RECEIVED` | `Received OTP 6-digits from LINE: ****** (Ref: USTT) (Broker: KRUNGSRI)` |
| 1484 | 14:01:09 | `LOGIN_SUCCESS` | `Authenticated successfully. URL: https://trademan.in.th/Portfolio` |
| 1485 | 14:02:44 | `SESSION_RESTORED` | re-verify session ผ่าน DOM (reuse — **ไม่ยิง SMS ซ้ำ**) |
| 1486 | 14:02:51 | `OTP_REQUESTED` | `broker=LIBERATOR ref=VDLQ ttl=180s` |
| 1487 | 14:03:18 | `LINE_OTP_RECEIVED` | `Received OTP 6-digits from LINE: ****** (Ref: VDLQ) (Broker: LIBERATOR)` |

- Krungsri: `✅ Krungsri TradeMan พร้อมใช้งาน (session saved)` · `data/session_state.json`
  → `exists=True, cookie_count=60, reason=RECENT`
- Liberator: log `🎉 2FA OTP CAPTURED VIA line_chat!` → `✅ Liberator WebTrade พร้อมใช้งาน`
  · `data/liberator_session.json` → `exists=True, expired=False, remaining_seconds=+86,329`
- `scripts/daily_readiness.py --json` → **`verdict: GO`** (`krungsri=AUTHENTICATED`, `liberator=AUTHENTICATED`)

### Gate ที่ D2 พิสูจน์
- **DB pinning (LINE-RCA-010)** ✅ — row ลง `investment_homelab.db` (primary) เท่านั้น ·
  sandbox DB ไม่มี row ใหม่ (ยังมีแค่ #26/#31 เดิม) · `Ref` ตรงกับ marker (`USTT`/`VDLQ` — ไม่ใช่ `N/A`)
- **Broker attribution (LINE-RCA-010)** ✅ — `KRUNGSRI` = 2 captures / 3 requests · `LIBERATOR` = 1 / 1
  → ตัวกรอง `broker_matches()` ทำงานจริงปลายทาง
- **`otp_source` ที่ซื่อสัตย์** ✅ — `otp_source=line_chat` (Liberator log ยืนยันตรง ๆ) · ไม่ใช่ `kdeconnect_*`
- **LINE-RCA-009 (KDE dormant)** ✅ — `KDECONNECT_OTP_RECEIVED` = **209 เท่าเดิม** (row ใหม่สุด 13:39 = ก่อน D2)
  → ตลอด D2 ไม่มี capture ผ่าน KDE เลยแม้แต่ครั้งเดียว
- **Zero-OTP reuse ของ Krungsri** ✅ — รอบ Liberator ตรวจ session แล้ว `RECENT` → reuse ไม่ยิง SMS ซ้ำ (Invariant 9 ทำงาน)

### Edge case ที่พบระหว่างทดสอบ (ไม่ใช่บั๊กของ product)
- ขอ OTP สองครั้งห่างกัน ~3 นาที (ref `HGHS` → `LNZP`): รหัสจาก SMS ใบแรกถูกทำให้ใช้ไม่ได้เมื่อขอใบใหม่ →
  Krungsri ตอบ `[alert] รหัส OTP ไม่ถูกต้อง` (row `BROWSER_DIALOG` #1480)
  · **บทเรียน operator: พิมพ์รหัสจาก SMS ใบล่าสุดเท่านั้น** — retry ด้วยรหัสใหม่ (ref `USTT`) ผ่านทันทีใน 19s

### Incident ใหม่ที่ D2 เปิดโปง — แก้แล้วในรอบนี้
**LINE-RCA-011 — gateway ค้างรุ่นเก่า: โค้ดแก้แล้วแต่ยังไม่ถูกโหลด (stale process)**
- **อาการ:** รอบแรก (13:53 UTC) ผู้ใช้พิมพ์ OTP → row ไปลง **sandbox DB** + `Ref: N/A` (หน้าตาเหมือนบั๊ก LINE-RCA-010 ทุกประการ)
- **RCA:** uvicorn เริ่ม **19:45:03 +07** แต่ `app/services/line_service.py` (20:08:39) และ
  `app/services/otp_relay_registry.py` (20:11:00) ถูกแก้ **ทีหลัง** และ process รันโดยไม่มี `--reload`
  → Python โหลดโมดูลรุ่นเก่าค้างในหน่วยความจำ (แก้บนดิสก์ ≠ แก้ที่รันอยู่)
- **หลักฐานยืนยัน 2 ทาง:** (1) mtime ของโค้ดใหม่กว่าเวลา start ของ process · (2) พฤติกรรมตรงกับโค้ดเก่าเป๊ะ (sandbox + `Ref: N/A`)
- **วิธีแก้ที่พิสูจน์แล้ว:** restart gateway (`.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`)
  → รอบถัดไป row ลง primary + `Ref` ถูกต้องทันที
- **บทเรียน:** แก้โค้ดฝั่ง gateway **ต้อง restart เสมอ** ก่อนทดสอบ · ให้ `scripts/daily_readiness.py` เป็น Go/No-Go gate
  ที่ยืนยันเส้นทางจริงก่อนเริ่มงาน (ไม่เชื่อ "โค้ดเขียนแล้ว")

## Out of scope / ห้ามแตะ
- Order placement / tick size / price-volume validation
- ไม่ลบโค้ด KDE Connect (ต้องคงไว้เป็น dormant fallback ตาม Zero-Contradiction)
- ไม่แก้ `implementation_plan.md` (เป็นแผน Pillar 2 — คนละเรื่อง)

---

## Cline Report — Gate C/D (2026-10-08, Act mode)

### Files changed (path เต็มทุกไฟล์)

**ไฟล์ใหม่**
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/otp_relay_registry.py`
  — relay persistence SSOT: **pin primary DB** (lazy `from app.db.session import AsyncSessionLocal`),
  marker `OTP_REQUESTED`, `resolve_pending_request()` (latest-request-wins, TTL 300s),
  `record_otp_received()`, `broker_matches()`, `broker_label()`, pure parsers/formatters
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_otp_multibroker_attribution.py`
  — 18 tests (DB pinning · attribution · end-to-end webhook→driver · broker isolation)

**แก้ไข**
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/line_service.py`
  - import `otp_relay_registry`
  - OTP branch (`_handle_text_message` §2): resolve marker → `broker` + `ref` จากข้อมูลจริง,
    persist ลง **primary DB**, ACK **ไม่มี "Krungsri Securities" hardcode**, คืน `broker` ใน result
  - `push_otp_request()`: เขียน marker **ก่อน** push, ใช้ `broker_label()` จาก registry (ลบ dict ซ้ำ),
    ถ้อยคำ "ตอบใน**กลุ่มนี้/แชทนี้**" ตาม channel จริง
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/schemas/auth.py` — `OTPPayload.broker: Optional[str]`
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/auth_driver.py`
  — `driver_broker = "KRUNGSRI"`; Check-1 (queue) + Check-2 (DB) กรองด้วย `broker_matches()` / `parse_otp_broker()`
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/liberator/driver.py`
  — `driver_broker = "LIBERATOR"`; Check-1 + Check-2 กรองแบบเดียวกัน
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/AGENTS.md` — §OTP relay + LINE-RCA-010
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/.agents/skills/daily-readiness/SKILL.md` — safety gate แถว LINE-RCA-010
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_line_otp_group.md` — เพิ่ม `LINE-RCA-010` + Zero-Contradiction checklist
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-otp-channel-authoritative.md` — decomposition + report นี้

### Summary
1. **DB routing (fatal bug แก้แล้ว)** — relay ไม่ใช้ `Depends(get_db)` (platform-aware) อีกต่อไป;
   ทุกอย่างที่เกี่ยวกับ OTP relay ถูก pin ไปที่ `AsyncSessionLocal` (primary `investment_homelab.db`)
   ผ่าน registry ที่ import แบบ lazy → webhook เขียนที่เดียวกับที่ driver อ่าน
2. **Broker attribution** — `OTP_REQUESTED` marker (broker+ref) เขียนก่อน push ทุกครั้ง;
   ACK และ row `LINE_OTP_RECEIVED` derive จาก marker จริง → Liberator ได้ label `Liberator WebTrade` + `Ref: ANBA`
3. **Broker isolation** — row มี tag `(Broker: X)`; driver ทั้งคู่ปฏิเสธ tag ของอีกโบรกเกอร์,
   แต่ **untagged (legacy / KDE) ยังยอมรับ** (lenient — ไม่ทำ regression กับข้อมูลเก่า)
4. **latest-request-wins** — ตามที่ผู้ใช้ยืนยัน; TTL 300s > OTP wait 180s

### คำสั่งเทสต์ที่รัน + ผลลัพธ์
```bash
# 1) ชุดใหม่
.venv/bin/python -m pytest tests/test_otp_multibroker_attribution.py -q
#   → 18 passed in 7.86s

# 2) bundle (11 ไฟล์ — otp/line/liberator/session/homelab)
.venv/bin/python -m pytest tests/test_otp_multibroker_attribution.py tests/test_otp_channel_authoritative.py \
  tests/test_otp_relay_readiness.py tests/test_daily_readiness.py tests/test_liberator_session.py \
  tests/test_webhook_line.py tests/test_line_otp_group.py tests/test_type_safe_auth.py \
  tests/test_browser_auto_reconnect.py tests/test_krungsri_session_health.py tests/test_start_homelab_stages.py -q
#   → 106 passed in 44.77s

# 3) full suite — ดูผลด้านล่าง (§Full suite)
.venv/bin/python -m pytest tests/ -q
```
รอบแรกของ bundle มี 2 fail ซึ่งเป็น **bug ของเทสต์เอง ไม่ใช่ product code**
(เขียนเทสต์ก่อน Phase C แล้วใช้ tag LIBERATOR ทั้งที่ assert ว่า Krungsri driver อ่านได้ +
regex source-guard ไม่รองรับชื่อตัวแปร `row_broker` ของ auth_driver) → แก้ 2 จุด → 106 passed ✅

### Open questions / สิ่งที่ไม่แน่ใจ
1. **`TRADING_PLATFORM=CLICK2WIN` ใน `.env` ยังคงอยู่** — ผม**ไม่แก้** (นอก scope, และเป็นคำถามที่ยังไม่ยืนยันจากผู้ใช้)
   ตอนนี้ไม่เป็นอันตรายต่อ relay อีกเพราะ relay ถูก pin แล้ว แต่ยังทำให้ handler อื่นของ webhook
   (kill switch / mode / postback) ใช้ **sandbox session** — ถ้าไม่ตั้งใจ ควรเปลี่ยนเป็น `TRADEMAN`
2. `webhook_line.py` ยังใช้ `Depends(get_db)` — **เจตนา**: เฉพาะ *relay persistence* ถูก pin
   ส่วน handler อื่นคงพฤติกรรมเดิมไว้ (แตะน้อยที่สุด)
3. **D2 verified แล้ว (2026-10-08 14:00–14:03 UTC)** — Krungsri (ref `USTT`) และ Liberator (ref `VDLQ`)
   login สำเร็จผ่าน LINE 1:1 พร้อม `otp_source=line_chat`; หลักฐานเต็มอยู่ใน §D2 Live Verification
   (ระหว่างทดสอบเจอ 2 ประเด็นใหม่: gateway ค้างรุ่นเก่า → **LINE-RCA-011** และ log พิมพ์ OTP ดิบ → ดูข้อ 5)
5. **log พิมพ์ OTP ดิบ (ยังไม่แก้ — นอก scope ของ handoff นี้)**: `app/brokers/liberator/driver.py`
   (`Captured OTP Code : <6 หลัก>`) และ `app/browser/auth_driver.py:466`
   (`Received OTP '<รหัส>' from {source}`) เขียนรหัสจริงลง stdout/ไฟล์ log → ควร mask
   · ไฟล์ log ชั่วคราวที่ผมเก็บระหว่างทดสอบถูก mask + ลบแล้ว (`/tmp/d2_run_liberator.txt` → `…_scrubbed.txt`, ต้นฉบับลบแล้ว)
6. **`TRADING_PLATFORM=CLICK2WIN` ยังคงเดิม** — ยืนยันแล้วว่า **ไม่กระทบ** relay (pin primary DB แล้ว)
   แต่ handler อื่นของ webhook ยังใช้ sandbox session — ควรพิจารณาเปลี่ยนเป็น `TRADEMAN` (นอก scope)
7. **full suite ยังค้างเหมือนเดิม (reproduce ซ้ำ 2026-10-08 ปิดงาน D2)** — รันแบบ bounded `timeout 420`
   `.venv/bin/python -m pytest tests/ -q` → ค้างที่ **63 dots หลัง marker `[64%]`** (≈82–87%) ไม่ขยับเลย ~127 วินาที
   จน elapsed **5:19 → kill** ตาม `loop_engineering.md` §3 (ห้ามรอเงียบ)
   · **`grep -cE '^(FAILED|ERROR)'` = 0** และไม่มีบรรทัด `F`/`E` ก่อนจุดค้าง → ไม่ใช่เทสต์พัง แต่เป็น lock/hang
   · หลักฐาน stack เดิมอยู่ที่ `docs/handoff/TASK-verify-loop-hook.md` (SQLite `test_homelab.db` single-writer)
   · งาน D2 นี้เป็น **docs-only** จึงยืนยันด้วย targeted/report-only mode (`verify_changes.py` → exit 0) แทน;
     full-suite gate ยัง **out of scope** จนกว่าจะแก้ SQLite hang
8. 🔴 **ต้องแจ้งล่วงหน้า — session สดจาก D2 ถูกทำลายไประหว่างปิดงาน (`KSS-RCA-015` — OPEN, นอก scope)**:
   การรัน full suite ปิดงาน **ลบ `data/session_state.json` จริง** (`tests/test_browser_driver.py::test_session_logout_endpoint`
   ยิง `POST /api/v1/session/logout` เข้า app จริง โดยไม่ monkeypatch `settings.SESSION_STATE_PATH` →
   `session.py:103` `os.remove(...)`) ⇒ **session Krungsri สดที่เพิ่งได้จาก D2 (21:01, 60 cookies) หายไปแล้ว**
   → การทดสอบ pillar ถัดไปต้อง **login ใหม่ + ให้ผู้ใช้พิมพ์ OTP อีกครั้ง** (ผมไม่แก้เองเพราะอยู่นอก scope · ไม่ mock)
   · รายละเอียด RCA + ข้อเสนอ fix: `rca/krungsri/rca_krungsri_trademan.md` §KSS-RCA-015
4. `test_both_drivers_wire_the_shared_broker_filter` เป็น **source-level guard** (อ่านไฟล์แล้ว grep)
   — กัน drift ได้ แต่ไม่ใช่การรัน Liberator login จริง (Liberator OTP loop ฝังอยู่ใน `login()` แยกออกมายาก)
   การยืนยันจริงของฝั่ง Liberator คือ D2

