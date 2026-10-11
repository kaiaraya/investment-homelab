---
name: daily-readiness
description: Daily-use readiness ritual for InvestmentHomelab — prepares the LINE
  group OTP relay ("a14s homelab") AND the broker sessions (Krungsri TradeMan,
  Liberator, Click2Win) in one command, then prints a GO / NO-GO verdict with an
  exit code (0 = ready to test other pillars, 1 = needs human-in-the-loop). Auto
  re-logs-in immediately when the relay is live (the 6-digit OTP is typed into the
  LINE group), and NEVER fires an SMS OTP while the relay is not ready (Invariant 9).
---

# Daily Readiness Skill (เตรียมความพร้อมรายวัน)

ใช้ skill นี้ **ทุกครั้งก่อนเริ่มทดสอบ pillar อื่น** (หรือหลัง reboot / restart backend /
redeploy tunnel) เพื่อให้แน่ใจว่า **"OTP relay (LINE group) + gateway :8000"** และ
**"session โบรกเกอร์"** พร้อมจริง

> **2026-10-08 — เปลี่ยนช่องทาง OTP:** จาก KDE Connect (D-Bus/GSConnect) → **LINE group `a14s homelab`**
> KDE Connect ยังอยู่ในโค้ดแต่เป็น **dormant** ไม่ใช่ gate อีกต่อไป — ดู `rca/shared/rca_line_otp_group.md`

## TL;DR — คำสั่งเดียว

```bash
.venv/bin/python scripts/daily_readiness.py
# exit 0 = GO (พร้อม)   |   exit 1 = NO-GO (ต้องช่วยด้วยมือ/HITL)
```

ตัวเลือก:

| Flag | ผล |
| :--- | :--- |
| `--json` | พิมพ์สรุปท้ายเป็น JSON (ใช้กับสคริปต์ต่อ) |
| `--no-login` | ตรวจอย่างเดียว (report-only) — ไม่เปิด browser / ไม่ยิง OTP |
| `--force-fresh` | บังคับ fresh login (purge cookies + ยิง OTP ใหม่) |
| `--no-ping` | ไม่ส่งข้อความยืนยันเข้าแชท LINE (กลุ่ม/1:1) |
| `--skip-liberator` | ข้าม Liberator (เตรียมแค่ Krungsri) |
| `--click2win` | แจ้งเตือนให้พิจารณา Click2Win (sandbox) ด้วย |

## When to use
- เปิดเครื่องครั้งแรกของวัน (ก่อนทดสอบ pillar 1–2)
- หลัง reboot NUC / รีสตาร์ท Chrome / `pkill chrome`
- หลังมือถือรีบูต หรือ MIUI/HyperOS อัปเดต (MIUI ชอบถอนสิทธิ์เอง — ดู checklist §Top)
- เมื่อ `preflight_check.py` หรือ MCP รายงาน session/session bridge ผิดปกติ

## Flow (Step 0 → Step 4)

```
Step 0  PRE-FLIGHT      → TCP probe uvicorn :8000 (รายงานผล; ไม่ auto-start)
                           (ถ้าต้องเปิด: ใช้ scripts/start_homelab.py — Stage 1 เปิดให้เอง)
Step 1  OTP RELAY       → app.services.otp_relay_readiness.check()  [Invariant 9 — LINE variant]
        ├─ false → แสดง reason + details แล้ว escalate เข้าแชท LINE + HITL steps
        │           (1) เปิด backend :8000  (2) ตรวจ tunnel  (3) พิมพ์ข้อความ 1 ครั้งในกลุ่ม หรือแชท 1:1  → NO-GO
        └─ true  → push ข้อความยืนยันเข้าแชท LINE (human confirm: เช็คในกลุ่ม/แชท 1:1)
Step 2  SESSION VERDICT → Krungsri : app.brokers.krungsri.session_health.session_file_info()
                          Liberator: app.brokers.liberator.session_health.session_health()
                          Click2Win: file presence only (sandbox ไม่มี JWT)
Step 3  AUTO RE-LOGIN   → ถ้าจำเป็น (และ bridge_ok == True เท่านั้น!)
                          Krungsri : auth_driver.login()   (reuse → verify → fresh + SMS OTP)
                          Liberator: liberator_driver.login()
        └─ bridge DOWN  → status=BRIDGE_DOWN, ยกเลิก login (ไม่ยิง OTP เปลือง/กัน lock)
Step 4  GO / NO-GO      → สรุป + เหตุผล + exit code (0=GO, 1=NO-GO)
```

## Safety gates (บังคับ — ฝังในโค้ดแล้ว)

| Rule | ฝังที่ | พฤติกรรมที่บังคับ |
| :--- | :--- | :--- |
| **Invariant 9** | `ensure_krungsri()` / `ensure_liberator()` | `bridge_ok` ต้องเป็น true ก่อนเรียก `login()` ทุกครั้ง; ถ้าไม่ → `status=BRIDGE_DOWN` และ **ไม่ยิง SMS OTP** |
| **Invariant 9 (LINE)** | `ensure_mobile_bridge()` → `otp_relay_readiness.check()` | relay ต้อง `ready` (LINE token จริง + `LINE_GROUP_ID` **หรือ** `LINE_ADMIN_USER_ID` (1:1, `LINE-RCA-006`) + gateway `:8000` listen **+ เป้าหมายนั้น probe แล้วต้องส่งถึงได้จริง** — 404 = ปิด (fail-closed, `LINE-RCA-007`)) · ห้ามยิง SMS OTP ถ้ายังไม่พร้อม |
| **LINE-RCA-010** | `app/services/otp_relay_registry.py` | relay persist = **primary DB** (`AsyncSessionLocal`) เสมอ — **ห้าม**ใช้ platform-aware `get_db()` (เดิม row ไปลง `investment_homelab_click2win.db` → driver timeout ทั้งที่ผู้ใช้พิมพ์ OTP แล้ว) · ACK ระบุโบรกเกอร์จาก marker `OTP_REQUESTED` (**latest-request-wins**, TTL 300s) ไม่ hardcode · driver กรองด้วย tag `(Broker: X)` (`broker_matches()`, untagged = ยอมรับ) |
| **Invariant 8 (dormant)** | `kdeconnect_service` | เดิมตัดสินด้วย D-Bus `isReachable` — **ห้ามใช้ `iconName`/`statusIconName`** (KDE-RCA-008 REVISED) · ตอนนี้เป็น fallback เท่านั้น |
| **Invariant 3** | `ensure_mobile_bridge()` | escalate ผ่าน LINE + HITL steps แล้วหยุด (ไม่วนไม่รู้จบ) |
| **Anti-Mock** | ทั้งไฟล์ | ไม่มีเลขบัญชี/ยอดเงิน/order id ปลอม; GO/NO-GO อิงผลตรวจจริง |
| **Broker Knowledge Isolation** | Step 2–3 | Krungsri ใช้ cookie-storage inspector; Liberator ใช้ JWT `exp`; Click2Win ไม่มี JWT → รายงาน presence เท่านั้น |
| **Zero-Contradiction** | ทั้งไฟล์ | ใช้ inspector/driver ตัวเดียวกับ production (single source of truth) ไม่มี logic ลอกเลียนที่เพี้ยนได้ |
| **stepwise-approval §5** | Step 1 + Step 3 | ping ให้ user ยืนยัน + login แบบ headed (`PLAYWRIGHT_HEADLESS=False`, `DISPLAY=:0`) ให้ user เห็น/กรอก OTP ได้ |

## Verdict logic (Anti-Mock)

| สถานะที่ตรวจได้ | ตีเป็น |
| :--- | :--- |
| `AUTHENTICATED` | ✅ พร้อม |
| `FAILED` / `ERROR` / `BRIDGE_DOWN` | ❌ ไม่พร้อม |
| `SKIPPED` + offline verdict ยังดี (Krungsri `needs_fresh_login=False`; Liberator `exists=true && expired=false`) | ✅ พร้อม (โหมด `--no-login`) |
| `SKIPPED` + offline verdict แย่ | ❌ ไม่พร้อม |

> ⚠️ การข้ามโดยเจตนา (`--no-login`) **ไม่นับเป็นความล้มเหลว** — ตัดสินจาก offline verdict แทน
> เพื่อไม่ให้รายงาน NO-GO ปลอม (Anti-Mock: verdict ต้องสะท้อนความจริง)

## Agent procedure (ทำตามทีละ step — loop engineering)

1. **Step 0 — Pre-flight (ไม่แก้ state)**
   ```bash
   .venv/bin/python scripts/preflight_check.py
   ```
   *Expected:* เห็นภาพรวม 7 จุด (backend, KDE bridge, Krungsri, Click2Win, Liberator, market, zombies)
   *หลักฐาน:* output ของ preflight

2. **Step 1 — OTP relay (LINE: group หรือ 1:1) + human confirm**
   ```bash
   .venv/bin/python scripts/daily_readiness.py --no-login
   ```
   *Expected:* `✅ relay พร้อม (channel=line_group)` (หรือ `channel=line_direct`) + `✅ ส่งข้อความยืนยันเข้ากลุ่ม LINE แล้ว`
   *Human confirm (บังคับ):* **ถามผู้ใช้ว่าเห็นข้อความในกลุ่ม "a14s homelab" หรือในแชท 1:1 กับ OA จริงไหม**
   - เห็น → ไป Step 2
   - ไม่เห็น / `❌ relay ไม่พร้อม: …` → ทำตาม HITL steps ที่สคริปต์พิมพ์ออกมา
     (1) เปิด backend `:8000` (2) ตรวจ tunnel (3) พิมพ์ข้อความ 1 ครั้งในกลุ่ม หรือในแชท 1:1 กับ OA แล้วรันซ้ำ
     (ห้ามเดาว่า "น่าจะได้" — Anti-Mock)

3. **Step 2 — Session verdict**
   อยู่ใน output ของ `daily_readiness.py` แล้ว (บรรทัด `verdict:` / `exists=… expired=…`)
   *เทียบกับ preflight* ให้ตรงกัน (ถ้าไม่ตรง = bug → บันทึก RCA)

4. **Step 3 — Auto re-login (gate ด้วย bridge)**
   ```bash
   .venv/bin/python scripts/daily_readiness.py        # ยิง OTP อัตโนมัติถ้าจำเป็น
   ```
   *Expected:* `✅ Krungsri TradeMan พร้อมใช้งาน` และ/หรือ `✅ Liberator WebTrade พร้อมใช้งาน`
   *กรณี bridge down:* ต้องเห็น `⛔ BRIDGE_DOWN — ยกเลิก auto login (ไม่ยิง SMS OTP; Invariant 9)`
   *หลักฐาน:* ข้อความ output + (ถ้าเป็นไปได้) screenshot หน้าจอ TradeMan ที่ login สำเร็จ

5. **Step 4 — GO / NO-GO + รายงาน**
   - `✅ GO` → แจ้งผู้ใช้ว่าปลดล็อก pillar ไหนได้แล้ว
   - `⛔ NO-GO` → ส่ง alert (`send_critical_alert` / `notify_admin_screen_help` ยิงให้แล้ว)
     แล้วรายงาน **root cause 3 จุด** (Session/Context, DOM/UI, Data Schema) ก่อนขอการตัดสินใจ

## Troubleshooting (map อาการ → runbook)

| อาการ | ทำอะไรต่อ |
| :--- | :--- |
| `relay ไม่พร้อม: LINE_GROUP_ID / LINE_ADMIN_USER_ID not set` | พิมพ์ข้อความ 1 ครั้งในกลุ่ม "a14s homelab" **หรือ** ในแชท 1:1 กับ OA `@678clhio` (auto-capture ลง `.env` ทันที) — `LINE-RCA-003` / `LINE-RCA-006` |
| บอทเชิญเข้ากลุ่มไม่ได้ (`Allow bot to join group chats` = Disabled) | เปิดสวิตช์ใน LINE Developers Console → Messaging API tab (default ปิด) — `LINE-RCA-005`; ทางลัดคือใช้แชท 1:1 (`channel=line_direct`) แทน |
| พิมพ์ข้อความแล้ว `LINE_GROUP_ID` ยังว่าง | เช็ค log: `source: 'user'` = พิมพ์ในแชท 1:1 → จะได้ `LINE_ADMIN_USER_ID` แทน · `source: 'group'` = ถูกต้อง |
| `relay ไม่พร้อม: LINE group push target not deliverable — … HTTP 404` | บอทไม่อยู่ในกลุ่มนั้นแล้ว/ค่ายังไม่ถูกเชิญ — `LINE-RCA-007` (gate **fail-closed** ตามที่ `push_message` จะยิงจริง) · ทางแก้: เชิญ OA `@678clhio` เข้ากลุ่มใหม่ (event `join` จะ capture ให้) **หรือ** ล้าง `LINE_GROUP_ID=` ให้ว่างเพื่อกลับไปใช้แชท 1:1 |
| ค่า `LINE_GROUP_ID`/`LINE_ADMIN_USER_ID` ค้างเป็นเป้าหมายตาย | ระบบเคลียร์เองเมื่อได้ event `leave` / `unfollow` (`LINE-RCA-008`) · ถ้าไม่มี event นั้น (webhook ปิดตอนบอทถูกถอด) ให้ล้าง `.env` เป็น `KEY=` เอง 1 ครั้ง |
| `relay ไม่พร้อม: Backend gateway is DOWN on :8000` | `scripts/start_homelab.py` (Stage 1 เปิดให้เอง) หรือ `uvicorn app.main:app --port 8000` |
| `relay ไม่พร้อม: LINE_SIMULATION_MODE=True` | ตั้ง `.env` → `LINE_SIMULATION_MODE=false` แล้ว restart backend |
| LINE Console กด **Verify** ไม่ผ่าน | ต้องได้ `200 {"note":"verify_ping"}` — ดู `LINE-RCA-001`; ตรวจ `LINE_CHANNEL_SECRET` ตรงกับ channel |
| พิมพ์ OTP ในกลุ่มแล้วไม่ถูกใช้ | `LINE-RCA-002` — ตรวจว่า `session_logs` มี `LINE_OTP_RECEIVED` และ regex `OTP_SESSION_LOG_PATTERN` ยังตรง |
| `isReachable = false` (KDE — dormant) | `kdeconnect_mobile_otp_checklist.md` A–F (มือถือ) แล้ว G (ฝั่ง NUC) — ดู `KDE-RCA-008` (ใช้เฉพาะเมื่อรื้อ KDE กลับมา) |
| `Krungsri … verdict=MISSING/STALE` | `learned_workflows/krungsri/krungsri_login_loop_checklist.md` |
| TradeMan session หลุดกลางทาง | `learned_workflows/krungsri/trademan_session_reconnect.md` |
| `Liberator … expired=True` | `learned_workflows/liberator/liberator_login_loop_checklist.md` |
| Port 8000 DOWN | **เป็น gate แล้ว** (LINE webhook เข้าที่นี่) → `scripts/start_homelab.py` Stage 1 หรือ `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| `--no-login` แล้วได้ NO-GO | ปกติ — report-only ตัดสินจาก offline verdict (session file) ไม่ใช่ live DOM |

## Zero-Contradiction notes (สำคัญ — ห้ามลบ)

- `scripts/start_homelab.py` **Stage 3 (Liberator) ไม่ทำ headed login** (anti-2FA-SMS policy)
  แต่ skill นี้ **ทำ headed login ให้ Liberator** ตาม user decision 2026-10-08
  → ทั้งสองไม่ขัดกัน: start_homelab เป็น boot orchestrator, daily-readiness เป็นพิธีกรรม
  เตรียมพร้อมที่มี human confirm + gate `isReachable` คั่นทุกครั้ง
- `scripts/preflight_check.py`, `scripts/daily_readiness.py`, `scripts/start_homelab.py` (Stage 1)
  และ `auth_driver` / `liberator_driver` ใช้ gate **ตัวเดียวกัน** คือ
  `app/services/otp_relay_readiness.py` → ห้ามแก้ logic ซ้ำสองที่
- **KDE Connect เป็น dormant** ตั้งแต่ 2026-10-08 — Invariant 8 (D-Bus `isReachable`) ยังจริง
  สำหรับ KDE แต่ไม่ใช่ gate ที่บล็อก login; จะรื้อกลับให้ส่ง
  `otp_relay_readiness.check(allow_kde_fallback=True)`
- ถ้า driver เปลี่ยน selector / ลำดับขั้นตอน → อัปเดต runbook ใน `learned_workflows/*.md` ทันที

## Tests (ต้องผ่านก่อนปิดงาน)

```bash
.venv/bin/python -m pytest tests/test_daily_readiness.py tests/test_otp_relay_readiness.py -q
```

ครอบคลุม: Invariant 9 gate (login ยกเลิกเมื่อ relay ไม่พร้อม), LINE relay step,
verdict matrix, exit-code mapping, Anti-Mock ของ Click2Win backend probe,
OTP relay readiness matrix, `OTP_SESSION_LOG_PATTERN` (LINE-RCA-002)

## Cross-references
- Rules: `.agents/rules/root_cause_and_escalation.md` (Invariant 3, 4, 8, 9),
  `.agents/rules/broker_pdca_rca.md`, `.agents/rules/loop_engineering.md`
- Skill: `.agents/skills/stepwise-approval/SKILL.md` (§5 hardware human confirm)
- Runner: `scripts/daily_readiness.py` · Tests: `tests/test_daily_readiness.py`,
  `tests/test_otp_relay_readiness.py`, `tests/test_line_otp_group.py`
- Gate: `app/services/otp_relay_readiness.py` · RCA: `rca/shared/rca_line_otp_group.md`
- Runbooks: `learned_workflows/krungsri/*`, `learned_workflows/liberator/*`,
  `learned_workflows/shared/kdeconnect_mobile_otp_checklist.md` (dormant KDE fallback)
- Handoff: `docs/handoff/TASK-daily-readiness-skill.md`, `docs/handoff/TASK-line-otp-group-relay.md`

