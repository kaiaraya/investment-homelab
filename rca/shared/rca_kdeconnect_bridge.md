# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: KDE Connect Hardware Bridge (Shared)

> [!WARNING]
> **DORMANT (2026-10-08) — ไม่ใช่ช่องทาง OTP หลักอีกต่อไป**
> OTP relay ย้ายไป **LINE group `a14s homelab`** แล้ว (ดู `rca/shared/rca_line_otp_group.md`)
> ไฟล์นี้ยังคงไว้เป็นความรู้เรื่อง D-Bus / GSConnect / MIUI checklist และเป็น fallback
> ที่ยังเรียกใช้ได้ (`otp_relay_readiness.check(allow_kde_fallback=True)`)
> **โค้ด `kdeconnect_service` ไม่ได้ถูกลบ** — แต่ไม่ใช่ gate ที่บล็อกการ login อีกต่อไป
> (Zero-Contradiction: ทุก RCA/KDE-RCA-xxx ด้านล่างยังถูกต้องตามข้อเท็จจริงเดิม)
**Component:** `app/services/kdeconnect_service.py` + `scripts/start_homelab.py`
**Scope:** สะพานเชื่อมฮาร์ดแวร์มือถือ (SMS OTP interception + HITL escalation) ที่ **ใช้ร่วมกันทั้ง Krungsri TradeMan และ Liberator WebTrade**
**Last Updated:** 2026-10-07
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose)
ไฟล์นี้เป็น SSOT ขององค์ความรู้เฉพาะทางด้าน **Hardware Bridge (KDE Connect / GSM SMS Relay)** ซึ่งเป็น Dependency ร่วม
(ไม่ผูกกับโบรกเกอร์ใดโบรกเกอร์หนึ่ง) การแก้ไขในชั้นนี้มีผลกับทุกโบรกเกอร์ จึงต้องแยกองค์ความรู้ออกจากไฟล์ RCA รายโบรกเกอร์
เพื่อรักษาหลัก **Broker Knowledge Isolation**

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :---: | :---: | :--- | :--- | :---: |
| 2026-10-05 | `KDE-RCA-001` | `kdeconnect_service.is_device_reachable()` ถูกเรียกแล้วเกิด `AttributeError` ทุกครั้ง (ถูกกลืนด้วย try/except) ทำให้ Session Health / Connect All รายงานว่า Hardware Bridge ขาดการเชื่อมต่อเสมอ | บรรทัด `async def is_device_reachable(...)` ถูกตัดหายไป ทำให้ logic ตรวจ reachability ไปติดอยู่แบบ orphan ใน `refresh_devices()` (และทำให้ `refresh_devices` คืนค่า bool ผิดจาก signature `-> None`) | 🟢 RESOLVED |
| 2026-10-05 | `KDE-RCA-002` | Startup gate รายงาน "Hardware Bridge ONLINE" (🟢) ทั้งที่ช่องทาง SMS OTP ยังไม่พร้อม (false-positive readiness) | `_probe_live()` ตรวจแค่ Tailscale TCP 1716 + D-Bus `isReachable` แต่ไม่ตรวจจริงว่า notification plugin ถูก expose บน D-Bus (คือช่องทางที่ poll OTP จริง) | 🟢 RESOLVED |
| 2026-10-05 | `KDE-RCA-003` | Startup gate อาจรายงาน "Hardware Bridge DOWN" (🔴) ทั้งที่ช่องทาง SMS OTP ใช้งานได้ (false-negative readiness) เมื่อผู้ใช้อยู่บ้านแต่ปิด Tailscale แล้วเชื่อมผ่าน **Home Wi-Fi** แทน | `_probe_live()` ตรวจ transport ด้วยการ TCP probe **เฉพาะ IP ของ Tailscale** (`100.119.166.62:1716`) แต่โทรศัพท์เข้าถึง NUC ได้ 2 เส้นทาง (Home Wi-Fi LAN `192.168.1.x` + Tailscale `100.x`) และ KDE Connect สลับเส้นทางเองได้ → ถ้า Wi-Fi ทำงานแต่ Tailscale ปิด จะถูกตัดสินเป็น DOWN ผิด | 🟢 RESOLVED |
| 2026-10-05 | `KDE-RCA-004` | บนมือถือเห็นเครื่อง NUC ซ้ำ 2 รายการ ("NUC-Intel" และ "Nuc-Intel" ต่างตัวพิมพ์) และ `kdeconnect-cli -l` บน NUC รายงาน 2 อุปกรณ์ โดยมี ghost `92bf…` ที่ `isPaired=false` | มี KDE Connect **2 implementation รันพร้อมกัน** (`kdeconnectd` PID 1957 + GSConnect GNOME-extension daemon PID 2341) ต่างคนต่างประกาศ NUC identity บนเครือข่าย → มือถือได้ duplicate announcement | 🟢 RESOLVED (ไม่กระทบ automation — ghost ถูกตัดที่ `-a` + มี blacklist ในโค้ด) |
| 2026-10-06 | `KDE-RCA-005` | 2FA SMS OTP มาถึง NUC ช้า **~7m39s** (Android Doze + GSConnect relay) และถูก **ทิ้งเงียบ** ทั้งที่มาถึงจริง → login S2 ล้มเหลว (poll เจอ 0 payload) | 3 ชั้น: **D2 (ตัวการจริง)** `poll_active_notifications` ตัด record ด้วย `now - rec.time > 300_000` แต่ `rec.time` = **เวลาที่มือถือสร้าง SMS** ไม่ใช่ arrival time → OTP ที่เพิ่งมาถึง (phone-clock อายุ 2,961s) ถูกมองเป็น "stale"; **D1** journal scan ใช้ `--since '-3 minutes'` คงที่ → packet ที่มาถึง 16:01:29 (นอกหน้าต่าง 15:53:45–15:56:45) มองไม่เห็น + live D-Bus ชี้ kdeconnectd ซึ่งไม่ได้รับ payload เมื่อ GSConnect ถือ LAN link; **D3** LAN path flap ระหว่าง Doze | 🟢 RESOLVED + **LIVE-CONFIRMED** (real-data replay PASS → **Live S2 retest PASS** 2026-10-06 16:58; fresh Ref `ZHXZ` captured ~3s) |
| 2026-10-06 | `KDE-RCA-006` | หลังรัน Live S2 สำเร็จ (มี OTP สด `ZHXZ` ใน journal) unit test `test_kdeconnect_poll_active_notifications_from_cache` กลับ **FAIL** (`assert 682729 == 918234`) — suite ไม่ hermetic | เทสต์ mock แค่ `os.path.expanduser` (ชี้ cache ไป tmp) แต่ **ปล่อยให้ `journalctl` จริงรัน** → เมื่อมี OTP สดใน journal โค้ดเดิน Path A (journal) ก่อนถึง Path B (cache) จึงคืน OTP จริงในเครื่องแทน fixture (ก่อนหน้านี้ผ่านเพราะ OTP ใน journal เก่าเกิน grace จนถูก age-guard ตัด) | 🟢 RESOLVED (เพิ่ม `patch("asyncio.create_subprocess_exec", return_value=_proc(b""))` ให้ hermetic → 15 passed) |
| 2026-10-07 | `KDE-RCA-008` | Krungsri login ค้าง `AWAITING_OTP` 180s — SMS OTP มาถึงมือถือแล้วแต่ไม่ถูกดึง → เสี่ยง account lock | **3 ชั้น:** (ก) **ตัวการหลัก — GSConnect (ช่องทาง OTP ที่ใช้ได้จริง) หลุด pairing:** `paired=false` → `device.js` ปิด plugin ทั้งหมด (`_loadPlugin` L1048 `if (this.paired …)`) + ทิ้ง packet ขาเข้า (`handlePacket` L440-441 `if (!this.paired) return this.unpair()`) + ทิ้ง packet ขาออก (`sendPacket` L464) ⇒ SMS plugin ไม่ทำงาน → cache `~/.cache/gsconnect/incoming_notifications.jsonl` หยุดเขียน (ค้างที่ 2026-10-06 23:45) — **ไม่ใช่ปัญหาเวอร์ชัน**; (ข) **readiness gate อ่าน property ผิด** (`iconName`/`statusIconName` ไม่น่าเชื่อถือ); (ค) `kdeconnectd 23.08.5` ทิ้ง `kdeconnect.notification.request` (คนละ daemon — ไม่ใช่ช่องทางที่ดัก OTP จริง) | 🟢 **RESOLVED + LIVE-CONFIRMED (2026-10-07 11:29)** — เปิด GSConnect extension กลับ (`Enabled=Yes`) + **re-pair** (ผู้ใช้กด Accept บนมือถือ; ต้องมี beacon ยิง pair request เพราะหน้าต่างหมดอายุใน 30s) → `paired=true`, `certificate-pem` เขียนแล้ว, plugin โหลด → **548 × `kdeconnect.sms.messages`** → cache โต 28,103 → 28,647 (mtime สด); **AUTO-CAPTURE LIVE-PROVEN 2026-10-07 12:47** (Liberator Ref `LNQY`, relay ~1s) |
| 2026-10-08 | `KDE-RCA-009` | เอกสาร & สคริปต์เทรดจริงอ้าง **device id ของมือถือผิด** — `directive/kdeconnect.md` §6.2/§7 เคยใช้ `556f3369…` (self-id ของ NUC) และ `scripts/krungsri/execute_live_sawad_sell.py` L221 ใช้ `a0149021_f4f1_…` (รูปแบบ underscore) เป็น target `--ping-msg` → ping/alert **ไม่ถึงมือถือ** โดยไม่ error (silent false-success) | นำ **NUC self-id** (`556f3369d5474626971e0aa088abc699` ใน `~/.config/kdeconnect/`) และ id ปลอมไปใช้เป็น id ของโทรศัพท์; id จริง = `9507a3fd53f848da9135ebe6253db18a` (source of truth `app/core/config.py KDECONNECT_DEVICE_ID`) | 🟢 RESOLVED (2026-10-08) — แก้เอกสารเป็น `9507a3fd…` ครบ (§4.1/§6.2×2/§7) + source-of-truth comment; **ลบ** ping block ที่ hard-code id ปลอมออกจากสคริปต์เทรด |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `KDE-RCA-001`: Orphaned `is_device_reachable()` Method
* **วันและเวลา:** 2026-10-05
* **อาการ (Symptom):**
  `hasattr(kdeconnect_service, 'is_device_reachable')` = `False` แต่มี Caller 5 จุดเรียกใช้ (pillar1 session health, CLI, Connect All)
  ทุกจุดถูกห่อด้วย `try/except` จึง fail แบบเงียบ และรายงาน "hardware bridge down" ตลอด
* **การสืบหาต้นตอ (Root Cause Analysis):**
  บรรทัด signature ของเมธอด `async def is_device_reachable(self) -> bool:` หายไป ทำให้บล็อกโค้ดตรวจ D-Bus
  (ที่ต่อท้ายด้วย `return True/False`) ไปต่อกันอยู่ในเมธอด `refresh_devices()` โดยไม่มี `def` คั่น
  → `refresh_devices()` (declared `-> None`) จริง ๆ แล้ว return ค่า bool และ `is_device_reachable` ไม่มีอยู่จริง
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - ต้องแยก `refresh_devices()` (side-effect เท่านั้น) ออกจาก `is_device_reachable()` (return bool)
  - Caller ทุกจุดใช้ `try/except` กลืน error → bug แบบนี้จะซ่อนได้นาน ต้องมี Unit Test กัน regression
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  คืน signature `async def is_device_reachable(self) -> bool:` กลับเข้าไปก่อนบล็อก D-Bus (ดู
  [app/services/kdeconnect_service.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/kdeconnect_service.py))
  และเพิ่ม Unit Test ใน [tests/test_kdeconnect_service.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_kdeconnect_service.py)

---

### 📌 Incident `KDE-RCA-002`: Fabricated Reachability + Missing OTP-Bridge Probe at Startup
* **วันและเวลา:** 2026-10-05
* **อาการ (Symptom):**
  Startup ผ่าน Stage 1 (Hardware Bridge ONLINE) แต่ OTP SMS interception ใช้งานไม่ได้จริง
* **การสืบหาต้นตอ (Root Cause Analysis):**
  1. ท้ายเมธอด reachability เดิมมี fallback `dev = await self.get_reachable_device_id(); return dev is not None`
     ซึ่ง `get_reachable_device_id()` คืน `self.device_id` แบบไม่มีเงื่อนไข → ทำให้รายงาน reachable แม้มือถือไม่ต่อ (**fabricated reachability** ผิด Invariant 8)
  2. `_probe_live()` ใน [scripts/start_homelab.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/start_homelab.py)
     ตรวจแค่ TCP 1716 + `isReachable` ไม่ได้ตรวจ `statusIconName` และไม่ได้ตรวจว่า notification plugin เปิดอยู่ (คือช่องทางรับ OTP จริง)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - `kdeconnect-cli -l` เป็น cache เก่า → **ห้ามใช้ตัดสิน readiness** (Invariant 8)
  - `isReachable == true` แต่ `statusIconName == smartphonedisconnected` → ถือว่าไม่พร้อม
  - gdbus อาจไม่มีให้ใช้ → ต้องคืน `False` ไม่ใช่ fabricate
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  - `is_device_reachable()`: ตรวจ D-Bus `isReachable` + `statusIconName` (reject `smartphonedisconnected`) และเปลี่ยน fallback สุดท้ายเป็น `return False` (ห้าม fabricate)
  - `stage1 _probe_live()`: เพิ่ม probe ที่ 3 = Introspect object path `.../notifications` และต้องพบ `activeNotifications` จึงถือว่า SMS/OTP bridge พร้อม
  - Startup banner (Fix 4): ใช้ตัวแปร `STARTUP_STATUS` และแสดง "🟡 HOMELAB READY WITH DEGRADED SERVICES" แทน "ALL SYSTEMS GO" เมื่อ Liberator (หรือ stage ใด) ไม่พร้อม
* **เทสต์ที่พิสูจน์ (Regression Tests):** `tests/test_kdeconnect_service.py::test_is_device_reachable_*`

---

### 📌 Incident `KDE-RCA-003`: Dual-Transport Blind Spot — Tailscale-IP-Only Probe False-Negatives on Home Wi-Fi
* **วันและเวลา:** 2026-10-05
* **อาการ (Symptom):**
  Guided physical edge-case test (ปิด Tailscale + force-stop KDE Connect บนมือถือ) ผ่านตามคาด (Step 4 → DOWN ✅)
  แต่เมื่อตรวจ **ตาราง socket จริง** ระหว่าง re-probe (Step 8) พบว่าโทรศัพท์เชื่อมด้วย **Home Wi-Fi** (`192.168.1.54:1716`)
  ไม่ใช่ Tailscale → ชี้ให้เห็นว่า Gate ตรวจ transport ผิดมิติ: ถ้าผู้ใช้ "อยู่บ้าน + ปิด Tailscale แต่เปิด Wi-Fi"
  ระบบจะรายงาน Hardware Bridge **DOWN** (🔴) ทั้งที่ช่องทาง SMS OTP ยังทำงานปกติ → **false-negative hard-block**
* **การสืบหาต้นตอ (Root Cause Analysis):**
  `_probe_live()` ใน [scripts/start_homelab.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/start_homelab.py)
  เช็ค transport ด้วย `check_tcp_port(phone_ip, 1716)` โดย `phone_ip` = `KDECONNECT_PHONE_IP` = **Tailscale IP** เท่านั้น
  แต่โทรศัพท์เข้าถึง NUC ได้ 2 transport (Home Wi-Fi LAN `192.168.1.x` และ Tailscale `100.x`) และ KDE Connect
  **เลือกเส้นทางที่ทำงานอยู่เส้นเดียวและสลับเองได้** (สังเกตจริง: Step 8 = Wi-Fi, อีกไม่กี่นาทีต่อมา = Tailscale)
  แม้ `get_network_routes()` จะรองรับทั้งสองเส้นทางอยู่แล้ว แต่ **startup gate ไม่ได้เรียกใช้**
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - KDE Connect เลือก 1 transport ที่ active ต่อครั้ง และสลับ Wi-Fi ⇄ Tailscale ได้กลางเซสชัน
  - ปิด Tailscale ทำให้ TCP path `:1716` ปิด แต่ kdeconnectd ยังรายงาน `isReachable=true` / `smartphoneconnected` จาก link เดิม (Step 4)
    → **D-Bus อย่างเดียว = false-positive** และ **Tailscale-IP อย่างเดียว = false-negative** จึงต้องใช้ **hard TCP transport check** ร่วมเสมอ
  - gsconnect แบบ same-host (local == remote IP) ต้องถูก exclude ไม่ให้นับเป็น LAN transport
  - `kdeconnect-cli -l` เป็น cache เก่า (Step 4: รายงาน "paired and reachable" ขณะที่ของจริงล่ม) → ห้ามใช้ตัดสิน (Invariant 8)
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  - เพิ่มฟังก์ชัน module-level `check_kde_live_transport(phone_ip, port) -> tuple[bool, str]`:
    1. TCP probe ไปยัง **Tailscale IP** → ถ้าติด คืน `(True, "Tailscale (<ip>:1716)")`
    2. ไม่ติด → parse `ss -tn` หา socket สถานะ `ESTAB` ที่พอร์ต `1716` ไปยัง peer วง **LAN** (`192.168.` / `10.`)
       โดยข้าม loopback และ same-host self-connection → คืน `(True, "Home Wi-Fi (<ip>:1716)")`
    3. ไม่พบทั้งสอง → `(False, "no live transport")` (ไม่ fabricate — Anti-Mock Guardrail)
  - `_probe_live()` เปลี่ยนเป็น `transport_ok, last_transport = check_kde_live_transport(...)` และ
    `ready = transport_ok AND dbus_connected AND notifications_ready`
  - `_push_troubleshooting()` รายงาน transport state จริง (ทั้ง Wi-Fi/Tailscale) แทนการอ้าง IP เดียว
  - **เทสต์ที่พิสูจน์ (Regression Tests):** [tests/test_start_homelab_transport.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_start_homelab_transport.py)
    (5 เคส: Tailscale path / Wi-Fi fallback เมื่อ Tailscale ล่ม / self-connection ถูก ignore / TS-socket ไม่ถูกนับเป็น LAN / all-down)
    → **5 passed in 1.87s**
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้ตั้งคำถามสำคัญว่า *"มือถือต่อได้ทั้ง 4G และ Wi-Fi — พิจารณาครบทั้งสองหรือยัง?"* → เป็นแรงขับของเหตุการณ์นี้
  - ผู้ใช้กำหนดว่า **การทดสอบต้องมีหลักฐาน (Evidence) ก่อนไปขั้นถัดไป** เพราะเป็นช่องทาง OTP ที่สำคัญ
  - ผู้ใช้กำหนดให้ **ping ตรวจสอบมอถือ** ก่อนดำเนินการต่อ (ยืนยันสะพานเชื่อมจริง)
  - หลักฐานที่เก็บได้: live probe → `(True, 'Tailscale (100.119.166.62:1716)')`; synthetic Wi-Fi fallback → `(True, 'Home Wi-Fi (192.168.1.54:1716)')`

---

### 📌 Incident `KDE-RCA-004`: Duplicate "NUC-Intel / Nuc-Intel" Self-Identity (kdeconnectd + GSConnect coexist)
* **วันและเวลา:** 2026-10-05
* **อาการ (Symptom):**
  ระหว่างทำ live KDE ping test (Step 8) บนลิสต์อุปกรณ์ของมือถือ Mi 10T เห็นเครื่อง NUC โผล่ **2 รายการ**
  ("NUC-Intel" และ "Nuc-Intel" ต่างตัวพิมพ์) → ผู้ใช้ตั้งคำถามว่า *"มือนับเป็น 2 อันจะมีปัญหาไหม?"*
  เมื่อตรวจฝั่ง NUC: `kdeconnect-cli -l` รายงาน **2 อุปกรณ์** =
  `92bf51aaea244830b7ed6a9af0115556` (name=`NUC-Intel`, type=`desktop`, **isPaired=false**, isReachable=true, icon=`laptopdisconnected`)
  และ `9507a3fd53f848da9135ebe6253db18a` (Mi 10T, paired+reachable)
* **การสืบหาต้นตอ (Root Cause Analysis):**
  มี KDE Connect **2 implementation ทำงานพร้อมกันบน NUC เดียวกัน**:
  1. `kdeconnectd` → `/usr/lib/x86_64-linux-gnu/libexec/kdeconnectd` (PID 1957)
  2. GSConnect (GNOME Shell extension) → `gjs -m ~/.local/share/gnome-shell/extensions/gsconnect@andyholmes.github.io/service/daemon.js` (PID 2341)
  ทั้งสอง daemon ประกาศ identity ของ NUC บนเครือข่ายเหมือนกัน (คนละ hostname casing) → มือถือได้รับ announcement ซ้ำ
  จึงแสดง NUC 2 รายการ. ยืนยันจาก config: `~/.config/kdeconnect/` มี self-id `556f3369d5474626971e0aa088abc699`
  (เดิม `directive/kdeconnect.md` §6.2/§7 นำ self-id นี้ไปใส่ผิดว่าเป็น device id ของมือถือ — แก้เป็น `9507a3fd…` แล้ว 2026-10-08) + `9507a3fd…`; ส่วน `92bf…` คือ NUC identity ที่ **GSConnect** ประกาศ (ไม่มี pairing)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - ghost `92bf…` เป็น **isPaired=false** → ถูกตัดออกจาก `kdeconnect-cli -a --id-only` (ซึ่ง list เฉพาะ paired+reachable) → **ไม่กระทบ code path หลัก**
  - โค้ดมี **hard-coded blacklist อยู่แล้ว 2 จุด** กัน ghost นี้: `get_reachable_device_id()` (L54) และ `is_device_reachable()` (L171):
    `dev != "92bf51aaea244830b7ed6a9af0115556" and "nuc" not in dev.lower()`
  - `scripts/start_homelab.py:286` ping ด้วย `-d <target_id>` **ระบุ ID ชัดเจน** → ยิงเฉพาะ Mi 10T ไม่โดน ghost
  - ความเสี่ยงจริงอยู่ที่ **UX**: มือถือโชว์ซ้ำ + เป็นไปได้ว่า notification เดียวกันอาจถูก relay 2 ครั้ง (OTP เป็น first-wins จึงไม่ทำให้พัง แต่ noisy)
  - latent risk: ถ้าอนาคตมีโค้ดไปตัดสินใจเลือกอุปกรณ์จาก `kdeconnect-cli -l` (cache) แทน `-a --id-only` → เสี่ยงหยิบ ghost ที่ unpaired
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  - **ยืนยันว่าไม่กระทบ automation** ด้วย live evidence:
    - D-Bus property query: ghost `isPaired=false` vs Mi 10T `isPaired=true`
    - `kdeconnect-cli -a --id-only` → คืน **ตัวเดียว** `9507a3fd53f848da9135ebe6253db18a` (ghost unpaired ถูกตัดทิ้ง)
    - live ping: `isReachable=true` → `kdeconnect-cli -d 9507a3fd… --ping-msg "…"` → `ping_rc=0` → ผู้ใช้ยืนยัน **เห็น ping บนมือถือ** ✅
  - **แนวทางแก้ UX (ไม่บังคับสำหรับงานนี้):** ปิด implementation ตัวใดตัวหนึ่ง เช่น disable GNOME extension **GSConnect**
    (ถ้าใช้ `kdeconnectd` เป็น canonical) หรือหยุด `kdeconnectd` (ถ้าใช้ GSConnect) เพื่อไม่ให้ NUC ประกาศซ้ำ 2 ครั้ง
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้ตั้งคำถามระหว่าง live test: *"KDEConnect ขึ้น NUC-Intel, Nuc-Intel เหมือนขึ้น 2 อันจะมีปัญหาไหม?"*
  - ข้อสรุปที่ตอบกลับ: **ไม่กระทบ automation** (ghost unpaired + ถูก blacklist + ping ระบุ ID) แต่เป็น UX/duplicate-notification nuisance;
    การจะปิดตัวหนึ่งเพื่อลบตัวซ้ำเป็น **การตัดสินใจของผู้ใช้** ไม่ใช่ข้อบังคับ
  - ผู้ใช้ยังคงยึดหลัก **ต้องทำ interaction จริง + มีหลักฐานก่อนไปขั้นถัดไป** (ตรงกับ `stepwise-approval` §5)

---

### 📌 Incident `KDE-RCA-005`: Late / Doze-Delayed SMS OTP Silently Discarded (Phone-Clock vs Arrival-Time)

* **วันและเวลา:** 2026-10-06 (Live S2 login test)
* **อาการ (Symptom):**
  Login Krungsri S2: driver เฝ้า OTP 180s (`OTP_TIMEOUT_SECONDS`) จน **Timeout** ทั้งที่ SMS OTP ส่งมาจริง
  หลังหมดเวลา ~4 นาที มี payload ตกลง NUC จริง แต่ poll ไม่เคยเห็น
  SMS จริง: `Your OTP is 749455 (Ref : VJKR)` — มือถือ**สร้าง**เมื่อ `15:53:50.765` (epoch ms `1791276830765`)
  แต่**มาถึง** NUC (GSConnect → user journal + `~/.cache/gsconnect/incoming_notifications.jsonl`) เมื่อ `16:01:29`
  → ช้า **~7 นาที 39 วินาที** (หน้าต่าง poll คือ 15:53:45–15:56:45 → อยู่นอกหน้าต่างทั้งหมด)
* **การสืบหาต้นตอ (Root Cause Analysis):** ล้มเหลว 3 ชั้น (D1 / D2 / D3)
  - **D2 (ตัวการจริง) — phone-clock vs arrival-time:** `poll_active_notifications` กรองด้วย
    `if msg_date and (current_time_ms - msg_date > 300_000): continue` (journal Path A) และ
    `if rec_time and (current_time_ms - rec_time > 300_000): continue` (GSConnect cache)
    โดย `msg_date` / `rec_time` = **เวลาที่มือถือสร้าง SMS** ไม่ใช่เวลาที่มาถึง NUC
    → OTP ที่ "เพิ่งมาถึง" แต่ phone-clock แก่ **2,961 วินาที** ถูกตัดสินเป็น "stale" แล้วทิ้งทันที
  - **D1 — channel / window:** journal scan ใช้ `--since '-3 minutes'` คงที่ → packet ที่มาถึง 16:01:29 มองไม่เห็น
    และ live D-Bus probe ชี้ `org.kde.kdeconnect` (kdeconnectd/Tailscale) ซึ่งไม่ได้รับ payload เมื่อ GSConnect เป็นเจ้าของ LAN link
  - **D3 — Android Doze / link flap:** ในหน้าต่างทดสอบ journal พบ 4× `kdeconnect.identity` แต่ **0 payload packet** (LAN path สะดุดขณะจอดับ)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - **ขยาย timeout ไม่ช่วย** — SMS ระบุเองว่า "expired within 5 mins" แต่ relay ใช้ 7 นาที 39 วินาที → OTP หมดอายุก่อนถึงมือ (ต้องลด latency ไม่ใช่ขยาย window)
  - **ขยาย grace เป็น 600s ก็ยังไม่พอ** — พิสูจน์แล้ว `phone_clock_age_s = 2961` (> 600) ⇒ **ต้องมี definitive Ref Code bypass** จึงจะรอด
  - GSConnect มี**แค่** D-Bus property `Connected` / `Paired` / `IconName` / `Type` — **ไม่มี** notifications interface (ยืนยันด้วย `gdbus introspect`) จึงใช้อ่าน payload ไม่ได้ ใช้ได้แค่เป็น liveness ของ LAN link
  - `~/.cache/gsconnect/incoming_notifications.jsonl` ใหญ่ ~8 MB และโค้ดอ่านแค่ `lines[-30:]` — OTP แก่ 8 นาทีอยู่ห่างปลายไฟล์ ~728 บรรทัด ⇒ cache lookback อาจไม่ครอบ grace ทั้งหมด (journal เป็น primary ที่เชื่อถือได้ — 743 `kdeconnect.sms.messages` ใน 50 นาที)
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  - `kdeconnect_service.poll_active_notifications(expected_ref=None, since_ms=None)`:
    * `ref_is_definitive` = `expected_ref` ตรงกับ `extract_res.ref` → **ยอมรับทันที ข้าม age guard**
    * grace ตั้งค่าได้: `settings.OTP_STALENESS_GRACE_SECONDS` (default 600) — ใช้เมื่อไม่สามารถระบุ Ref ได้เท่านั้น
    * journal: `--since f"@{since_ms//1000 - 5}"` ผูกกับเวลาที่**ขอ OTP** (arrival-time semantics) แทน `-3 minutes` คงที่
  - `is_device_reachable()`: เพิ่ม **parallel-link probe** `_gsconnect_connected()` (GSConnect D-Bus `Connected`) → reachable ถ้า **ตัวใดตัวหนึ่ง** ยืนยัน (kdeconnectd `isReachable` **หรือ** GSConnect `Connected`); probe ล้ม = False (Anti-Mock)
  - `auth_driver.login()`: ส่ง `since_ms=int(wait_start_time.timestamp() * 1000)` เข้า poll
  - **หลักฐาน Proof-by-Artifact:** replay OTP จริงผ่านโค้ดที่แก้แล้วด้วย `scripts/replay_kde_rca005.py` →
    `RESULT otp=749455 ref=VJKR source=OTPSource.KDE_CONNECT sender=KSS-OTP` (elapsed **0.16s**), live probes `kdeconnectd reachable: True` + `gsconnect connected: True` → **VERDICT: PASS**
  - **Before/After เชิงตัวเลข:** `now - sms_date = 2,961,191 ms`; guard เดิม `> 300_000` ⇒ **ทิ้ง** (True); grace ใหม่ 600s ⇒ **ยังไม่พอ** (False) ⇒ ยืนยันว่า *Ref Code bypass* คือกลไกที่แก้จริง
  - Unit tests: `tests/test_kdeconnect_service.py` — **15 passed**
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้เลือกขอบเขตงาน **option 1** = แก้ U2 (arrival-time staleness) + U3 (journal ผูกกับเวลาขอ OTP) + U4 (เพิ่ม GSConnect เป็น link คู่ขนาน) แล้วค่อย retest
  - หลักการที่ผู้ใช้ย้ำ: **SMS ที่ส่งมาแล้วถูก "ทิ้งเงียบ" เป็นความผิดพลาดที่ยอมรับไม่ได้** และต้องมีหลักฐานจริงก่อนปิดงาน

* **✅ Live S2 Re-Test Confirmation (2026-10-06 16:58 — real login + real SMS):**
  - คำสั่ง: `.venv/bin/python -m app.brokers.krungsri.cli login --force-fresh --otp-timeout 300` (headed, `DISPLAY=:0`)
  - เป็น OTP **รอบใหม่** (ไม่ใช่ VJKR ของเดิม): `Ref ZHXZ` / code `682729`
  - Timeline: 16:58:26 ส่ง credentials → **16:58:32** ระบบขอ OTP (Ref `ZHXZ`) → **16:58:35** `Journal: Matched expected Ref Code 'ZHXZ' from SMS!` + `Direct KDE Connect capture in driver: 68****` → 16:58:35 ส่ง OTP → 16:58:40 post-login verified (CreditBalance) → **16:58:51** `#dropDownAccountPort visible! SSO session verified` (`trademan.in.th/Portfolio`) → save session
  - **Capture latency ≈ 3 วินาที** (Ref announced 16:58:32 → captured 16:58:35) เทียบกับเหตุการณ์เดิม 7m39s
  - เส้นทางเป็น **KDE Connect 100%** — CLI stdin เป็น EOF (non-TTY) จึงไม่ได้ใช้ช่องทาง manual/terminal เลย กลไก ref-match ทำงานได้ด้วยตัวเอง
  - Artifact: `data/session_state.json` เขียนใหม่ (27,879 bytes, 60 cookies, mtime 16:58:51) — ยืนยัน S3 Zero-OTP persistence ไปในตัว
  - **Verdict: PASS** (end-to-end บนข้อมูลโบรกเกอร์จริง ไม่มี mock) — ⚠️ ข้อเท็จจริงตรงไปตรงมา: รอบนี้ "เร็ว" เพราะผู้ใช้นั่งเฝ้ามือถืออยู่ (Doze ถูกระงับ) กลไก Ref-bypass ยังคงเป็น safety net ของกรณีมาช้า; **U6 (Doze/battery whitelist) ยังเป็นตัวแก้ latency ที่แท้จริง**

---

### 📌 Incident `KDE-RCA-006`: Non-Hermetic Unit Test Read the Live Journal (Test-Isolation Regression)

* **วันและเวลา:** 2026-10-06 (พบทันทีหลัง Live S2 retest PASS)
* **อาการ (Symptom):**
  `pytest tests/test_kdeconnect_service.py` ลดจาก **15 passed** → **14 passed, 1 failed**:
  `test_kdeconnect_poll_active_notifications_from_cache` ได้ OTP `682729` (Ref `ZHXZ` = OTP จริงจาก Live S2) แทน fixture `918234`
* **การสืบหาต้นตอ (Root Cause Analysis):**
  เทสต์ mock เฉพาะ `os.path.expanduser` (ชี้ cache → `tmp_path`) แต่ **ไม่ได้ mock `asyncio.create_subprocess_exec`**
  → `poll_active_notifications()` ยังรัน `journalctl` จริง (Path A มาก่อน cache) เมื่อ journal มี OTP สดที่เพิ่งมาถึงจริง
  โค้ดจึงคืนค่านั้นก่อนตกไปอ่าน cache (เทสต์ผ่านมาก่อนหน้านี้เพราะ OTP ใน journal เก่าเกิน grace → ถูก age-guard ตัด → ตกไปอ่าน cache)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - เทสต์ที่พึ่งพา **state ของเครื่องจริง** (journal ระบบ / cache ผู้ใช้) จะเปราะ: ผ่าน/ไม่ผ่านขึ้นกับว่ามี SMS สดหลงเหลือในระบบหรือไม่
  - เป็น **test-isolation bug** ไม่ใช่ bug ของ production code — แต่ทำให้สัญญาณ regression ใน `tests/` เชื่อถือไม่ได้
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  เพิ่ม `patch("asyncio.create_subprocess_exec", return_value=_proc(b""))` (ให้ journalctl คืนค่าว่าง) → โค้ดตกไปอ่าน cache ที่ mock → คืน `918234` ตาม fixture
  ใช้รูปแบบเดียวกับเทสต์พี่น้อง (`test_poll_journal_window_anchored_to_otp_request`, `test_poll_rejects_stale...`)
  **หลักฐาน:** `.venv/bin/python -m pytest tests/test_kdeconnect_service.py -q` → **15 passed** (deterministic)
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  ทุกเทสต์ใน `tests/test_kdeconnect_service.py` ต้อง **hermetic** — ห้ามอ่าน journal/cache ของเครื่องจริง (Anti-Mock + `loop_engineering` §3 verification)

---

### 📌 Incident `KDE-RCA-007`: Stale MCP Process (No D-Bus Session Bus) Reports the Phone OFFLINE (False-Negative)

> **สถานะ: ✅ RESOLVED (2026-10-06) — remediation: ถอด MCP `homelab-trading-gateway` ออกทั้งหมด; เทรดผ่าน REST `/api/v1/*` / SSE `/sse` (uvicorn, env ครบ) แทน**

* **รหัสเหตุการณ์และวันที่ (Incident ID & Date):** `KDE-RCA-007` (2026-10-06, พบระหว่าง Pillar-1 acceptance run `start_homelab.sh`)
* **อาการที่พบ (Symptom):**
  เรียก MCP tool `session_get_health` (ผ่าน `homelab-trading-gateway`) แล้วได้
  `kdeconnect.status = "OFFLINE"`, `reachable = false` **พร้อมกัน** กับ
  `network_routes.active_route = "TAILSCALE"`, `tailscale = "ACTIVE"`, `remote_ip = "100.119.166.62:1716"`
  → ข้อมูลใน payload เดียวกันขัดกันเอง (Zero-Contradiction)
  ขณะที่ของจริงโทรศัพท์ออนไลน์: `gdbus isReachable = <true>`, `statusIconName = smartphoneconnected`,
  Tailscale TCP `OPEN`, มี socket `ESTAB ... 100.119.166.62:1716`
* **การสืบหาต้นตอ (Root Cause Analysis - RCA):**
  MCP server เป็น **process ที่รันยาว** (`app.mcp.server` PID **19686** เริ่ม 15:17:06;
  `app.mcp.mcp_server` PID **4056** เริ่ม ~15:16) และ **env ของทั้งสองไม่มี `DBUS_SESSION_BUS_ADDRESS`**
  (`tr '\0' '\n' < /proc/19686/environ | grep -i dbus` → ไม่มีอะไรเลย)
  → ทุก `gdbus call --session` ภายใน process นั้นล้มเหลว → `is_device_reachable()` ตกไป `_gsconnect_connected()`
  (D-Bus เหมือนกัน → ล้ม) แล้วตกไป fallback สุดท้าย → คืน `False` (ถูกต้องตาม Anti-Mock: ไม่ fabricate)
  แต่ `get_network_routes()` ใช้ socket/`ss` (ไม่พึ่ง D-Bus) → ยังเจอ TAILSCALE ACTIVE → เกิด payload ขัดกัน
  **ตัวพิสูจน์:** gateway ที่เพิ่งสตาร์ตใหม่ (uvicorn PID **49915** — มี `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`
  สืบทอดมาจาก shell) → `GET /api/v1/session/health` คืน `kdeconnect.status="ONLINE"`, `reachable=true` ✅
  และ standalone `.venv/bin/python -c "... is_device_reachable()"` (มี session bus) → `True`
  ⇒ **ฟังก์ชันถูก; ตัวแปรคือ environment ของ process**
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - process ที่รันยาวและถูกสตาร์ตโดยไม่สืบทอด session-bus env (เช่น IDE/daemon) จะรายงาน KDE OFFIBLINE เท็จถาวร
    แม้ฮาร์ดแวร์พร้อม — เป็น **operational false-negative** ไม่ใช่ฮาร์ดแวร์เสีย
  - `is_device_reachable()` + `get_network_routes()` ใช้ **แหล่งข้อมูลคนละชั้น** (D-Bus vs socket) →
    payload รวมกันจะ self-contradict ได้เมื่อชั้นหนึ่งพัง
  - `start_homelab.py` Stage 1 ใช้ gdbus ตรง ๆ และสืบทอด env จาก shell → **ไม่กระทบ** (นี่คือเหตุที่ Stage 1 ผ่าน)
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  ยังไม่มีโค้ดแก้ (DIAGNOSED เท่านั้น). **แนวทาง remediation ที่เสนอ (ต้องมี handoff + test แยก):**
  - Operational: restart MCP servers (`python -m app.mcp.server` / `python -m app.mcp.mcp_server`)
    ให้สืบทอด `DBUS_SESSION_BUS_ADDRESS` (และ `DISPLAY`) จาก session ของผู้ใช้
  - Optional hardening: ให้ `is_device_reachable()` แจ้ง/fallback อย่างซื่อตรงเมื่อไม่พบ session bus
    (เช่น คืน `None` = "unknown" หรือใช้ route-probe เป็น fallback) — **ห้าม fabricate True**
  **หลักฐาน:** `/proc/<pid>/environ` ของ 19686/4056 ไม่มี DBUS; เทียบกับ 49915 ที่มี; curl สองปลายทางให้ผลตรงข้ามกัน
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  ผู้ใช้ตั้งเป้า Pillar-1 acceptance = `start_homelab.sh` ครบ 4 stage เขียว (ทำสำเร็จ).
  ข้อสังเกตนี้ต้อง **ไม่ถูกตีความว่า Stage 1 ล้มเหลว** — Stage 1 ผ่านจริง; ให้ตามแก้ที่ process env ของ MCP

---

### 🟢 Resolution Note — `KDE-RCA-007` (RESOLVED 2026-10-06)

* **การตัดสินใจ:** ถอด MCP `homelab-trading-gateway` (stdio `app.mcp.server` ผ่าน `scripts/mcp_launch.sh`) ออก **ทุกจุด**:
  `~/.cline/data/settings/cline_mcp_settings.json`, `docs/cline/cline_mcp_settings.json`,
  `mcp_config.json` (`homelab-trading-gateway`, `-tailscale`, `-stdio`), `.cursor/mcp.json`
* **เหตุผล (ยืนยันซ้ำใน Gate D):** stdio MCP process สืบทอด env แบบ sanitized จาก IDE → ขาด
  `DBUS_SESSION_BUS_ADDRESS`/`XDG_RUNTIME_DIR` → `gdbus call --session` ล้ม (KDE รายงาน OFFLINE เท็จ + OTP ไม่ถูกจับ)
  อาการปลายทาง: SMS OTP เข้ามาแล้ว (Krungsri ส่งจริง) แต่ browser ไม่แลนดิ้งหน้า post-login เพราะ OTP ไม่ถูก submit
* **ผลลัพธ์:** หลังแก้ config + IDE reconnect → `pgrep -af 'app.mcp.server'` ไม่เหลือ stdio gateway;
  `playwright-homelab` (`app.mcp.mcp_server`) ยังทำงาน; module `app.mcp.server` **ยังอยู่** เป็น backend ของ uvicorn `/sse` + REST `/api/v1/*` (ไม่ได้ลบ)
* **แนวทางที่ยืนยัน:** การเทรด/เซสชันในอนาคตใช้ **uvicorn REST** (env ครบ + log เห็น) หรือ SSE gateway ที่ uvicorn mount
  — ห้ามพึ่ง stdio MCP ที่มี env ขาด session bus
* **Self-healing fix (2026-10-06):** patch `scripts/mcp_launch.sh` ให้ re-inject `XDG_RUNTIME_DIR`
  (+ `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/<uid>/bus`) และ `WAYLAND_DISPLAY` จาก live per-user runtime dir
  — รูปแบบเดียวกับ XAUTHORITY cookie ที่มีอยู่แล้ว เพื่อไม่ให้ stdio MCP ที่อาจถูกเรียกใช้อีกกลับมาขาด session bus แบบเงียบ ๆ
  **หลักฐาน:** จำลอง env แบบ sanitized `env -i HOME=… PATH=/usr/bin:/bin bash scripts/mcp_launch.sh -c '…'` →
  ได้ `XDG_RUNTIME_DIR=/run/user/1000`, `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`, `DISPLAY=:0`,
  `XAUTHORITY=/run/user/1000/.mutter-Xwaylandauth.*`, `WAYLAND_DISPLAY=wayland-0`
  (process `app.mcp.mcp_server` ที่เกิดใหม่ pid **80239** มี env ครบโดยไม่ต้องตั้งมือ)
* **Live end-to-end confirmation (Gate D, 2026-10-06 23:45):** `POST /api/v1/session/login-broker {platform:"KRUNGSRI",force_fresh:true}`
  บน uvicorn → `AUTHENTICATED` (OTP auto-captured ผ่าน KDE Connect, ref `UGJM`, ~<20s) →
  `data/session_state.json` เขียนสำเร็จ 27,881 B ⇒ ยืนยันว่า path ที่ env ครบทำงานได้จริงตั้งแต่ login ถึงอ่านพอร์ต
---

### 📌 Incident `KDE-RCA-008`: OTP Readiness Gate (wrong D-Bus property) + SMS-relay version mismatch

> **REVISED 2026-10-07 (second pass):** the original write-up attributed the whole
> failure to the wrong D-Bus property (`iconName`). Live re-testing proved **two distinct
> root causes**; this section is corrected to match the shipped code (Zero-Contradiction).

* **วันและเวลา:** 2026-10-07 ~09:12–09:17 น. + re-verify 10:31–10:41 (ICT)
* **อาการ (Symptom):**
  - `session_login_broker(KRUNGSRI, force_fresh=true)` → login ค้าง `AWAITING_OTP` (Ref `DBCT`, 180s) ทั้งที่ SMS OTP ส่งถึงมือถือแล้ว
  - `kdeconnect-cli -l` ยังรายงาน "paired and reachable" + `preflight` พิมพ์ "✅ Socket connected" → ระบบคิดว่าบริดจ์พร้อม
  - แต่ `kdeconnect-cli --list-notifications` ว่าง + D-Bus `activeNotifications` = `[]` → OTP ไม่ถูกดึง → เสี่ยง account lock หาก retry ซ้ำ
  - **ยืนยันซ้ำ (2026-10-07 10:41):** `isReachable = (true,)` แต่ `iconName = ('smartphonedisconnected',)` → readiness gate ที่พึ่ง `iconName` ให้ **false-negative** (มองว่าบริดจ์หลุดทั้งที่เชื่อมต่ออยู่)
* **การสืบหาต้นตอ (Root Cause Analysis — 3 จุด):**
  1. **Session & Context Isolation (ต้นตอจริงของ "ค้าง AWAITING_OTP"):** มือถือ ↔ NUC ใช้ **แอป KDE Connect คนละเวอร์ชัน** — NUC ใช้ `kdeconnect 23.08.5-0ubuntu5` (รุ่นเดียวใน Ubuntu noble repo) ขณะที่แอปบนมือถือเป็นรุ่นใหม่กว่า → NUC log:
     `Oct 07 10:16:11 NUC-Intel org.kde.kdeconnect[26008]: discarding unsupported packet "kdeconnect.notification.request" for "Mi 10T"`
     ⇒ แพ็กเก็ต notification/SMS จากมือถือถูก **ทิ้ง** → ไม่มี `kdeconnect.sms.messages` → OTP ไม่เคยถูก relay
  2. **DOM & UI Reality (→ D-Bus reality):** property ที่ใช้ตัดสิน readiness ไม่น่าเชื่อถือ — ทั้ง `statusIconName` และ `iconName` ให้ค่าผิด; ตัวที่ **เชื่อได้** คือ real-time `isReachable` (ยืนยันสด: `isReachable=true` + `kdeconnect-cli -a` เห็น device + ping ผ่าน แต่ `iconName='smartphonedisconnected'`) → โค้ดที่พึ่ง `iconName` ให้ได้ทั้ง false-positive และ false-negative
  3. **Data Schema & Types:** `preflight_check.py` (เดิม) เช็คแค่ `deviceNames` (paired) + TCP 1716 (port ยังเปิดแม้แอปหลุด) → false-positive readiness; TCP open ไม่ได้แปลว่า notification bridge ทำงาน

* **Edge Cases ที่พบ (Edge Cases Identified):**
  - `iconName='smartphonedisconnected'` ขณะ `isReachable=true` → **false-negative** ที่ block login ผิด ๆ (พิสูจน์สด 2026-10-07) → ห้ามใช้ `iconName` ตัดสิน readiness
  - `statusIconName` คืน `smartphoneconnected` ตลอด → กับดัก false-positive (เหตุผลเดิมของ RCA นี้)
  - `isReachable=true` + TCP open ยัง **ไม่การันตี** ว่า SMS relay ทำงาน — ถ้าแอปสองฝั่งคนละเวอร์ชัน แพ็กเก็ตจะถูก discard (จุดที่ 1)
  - `kdeconnect-cli -l` / `--list-notifications` = cache / ว่างได้ → ห้ามใช้ตัดสิน readiness (Invariant 8)
  - Trigger SMS OTP ทั้งที่ bridge down = เปลือง OTP + เสี่ยง account lock → ต้อง gate ก่อน
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  1. `is_device_reachable()`: ใช้ **`isReachable == true`** เป็นสัญญาณหลัก (ละทิ้ง `iconName`/`statusIconName` ทั้งคู่) + คง GSConnect parallel-link fallback
  2. `scripts/start_homelab.py` stage1: เช็ค `isReachable` เดี่ยว ๆ (ตัด iconName ออก) — single source of truth กับ driver
  3. `scripts/preflight_check.py`: query `isReachable` real-time (แทน `deviceNames`/`iconName`) → แสดง "❌ Socket OPEN but D-Bus isReachable = false" ตามจริง
  4. **Gate (Invariant 9):** `auth_driver.login()` เรียก `is_device_reachable()` ก่อน trigger SMS; ถ้า down → `LoginResult(status=BRIDGE_DOWN)` โดยไม่ส่ง SMS + เพิ่ม `AuthStatus.BRIDGE_DOWN`
  5. Regression tests: `tests/test_kdeconnect_service.py::test_is_device_reachable_*`
* **~~ยังแก้ไม่หาย (Open — ต้องอัปเกรดฝั่ง NUC)~~ — ❌ REFUTED / SUPERSEDED (2026-10-07 12:47):**
  - ~~readiness gate แก้... แต่ **SMS relay ยังพัง** เพราะ version mismatch~~ → **ผิด: ไม่ใช่ version mismatch.** relay (GSConnect SMS plugin) ทำงานจริง; ต้นเหตุคือ **GSConnect หลุด pairing** (ดู FINAL RESOLUTION ด้านล่าง)
  - ~~อัปเกรด `kdeconnect` บน NUC~~ → **ไม่จำเป็น** — auto-capture พิสูจน์สด 2026-10-07 12:47 (Liberator Ref `LNQY`, ~1s)
  - ~~OTP ต้องกรอก manual~~ → manual (`/console`, `POST /api/v1/session/submit-otp`) เป็นเพียง **fallback**; auto-relay ใช้ได้ตามปกติ
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้ระบุว่าเจอปัญหาลักษณะนี้บ่อย และกังวล account lock → ขอให้ใช้ code gate (Hook-style) ป้องกันซ้ำ ไม่ใช่แค่เขียน rule
  - ลำดับที่เลือก: ลง gate ก่อน แล้วค่อย re-login (ปลอดภัยสุด)
  - (2026-10-07) ผู้ใช้ยืนยันให้เดินหน้า re-verify หลักฐาน Pillar-2 หลัง fresh login


### 🟢 FINAL RESOLUTION — `KDE-RCA-008` (RESOLVED + LIVE-CONFIRMED 2026-10-07 11:29)

> **THIRD PASS (2026-10-07, correcting the second pass):** the second pass concluded the SMS relay
> was broken by a `kdeconnect` version mismatch and that the only fix was a NUC-side upgrade (manual
> OTP in the meantime). Live re-testing **disproved** that: the working OTP relay is **GSConnect's
> SMS plugin writing the cache**, and it had simply **lost its pairing**. Re-pairing restored capture
> instantly — **no `kdeconnect` upgrade is required.**

* **Corrected root cause (the real chain):**
  1. GSConnect's per-device flag `paired` was **`false`** (and `certificate-pem` empty), verified live:
     `GSETTINGS_SCHEMA_DIR=<ext>/schemas gsettings get org.gnome.Shell.Extensions.GSConnect.Device:/org/gnome/shell/extensions/gsconnect/device/9507a3fd…/ paired` → `false`.
  2. In `service/device.js`, plugins are **gated on pairing**:
     - `_loadPlugin()` L1048 `if (this.paired && !this._plugins.has(name))` → **no plugins load when unpaired**
     - `handlePacket()` L440-441 `if (!this.paired) return this.unpair();` → **incoming `kdeconnect.sms.messages` dropped**
     - `sendPacket()` L464 `if (!this.paired && packet.type !== 'kdeconnect.pair') return;` → **outgoing requests dropped**
  3. ⇒ the SMS plugin never ran and `_handleMessages()` (`service/plugins/sms.js` L305-324) never appended
     ⇒ `~/.cache/gsconnect/incoming_notifications.jsonl` **froze at 2026-10-06 23:45** (last line
     `292611 (Ref: UGJM)`); the homelab layer-4 fallback then found nothing.
  4. The UI extension being `Enabled: No` and the machine being **off between 2026-10-06 23:45 and the
     2026-10-07 08:41 boot** were contributing facts, but the gating defect was the loss of **pairing**.
* **Proof the phone genuinely treats the link as unpaired (not a stale flag):** setting `paired=true`
  then restarting `gsconnect.service` **self-reverted to `false`** — the daemon re-derives pairing from
  the phone's identity packet ⇒ the phone reports the GSConnect link as unpaired.
* **Proven working solution (live):**
  1. Re-enable the extension: `gnome-extensions enable gsconnect@andyholmes.github.io` → `Enabled: Yes / ACTIVE`.
  2. Re-pair (phone-side **Accept**). `pair()` (L947) arms a **30 s** `_outgoingPairRequest` window, so a
     short **pairing beacon** kept a fresh `kdeconnect.pair` request alive (`~/.local/bin/gsconnect -d 9507a3fd… --pair`,
     every 20 s) until the user tapped Accept.
  3. On confirmation: `gsconnect -a` → `Mi 10T  true  true` (connected + paired); `certificate-pem` populated
     (609 chars); plugins load (`_loadPlugins`); SMS plugin `connected()` → `_requestConversations()`.
  4. **Evidence:** daemon journal showed **548 × `kdeconnect.sms.messages`**; cache grew **28,103 → 28,647**
     with a fresh mtime (`2026-10-07 11:29:14`). `poll_active_notifications()` still returns `None` when no
     *fresh* OTP exists (Anti-Mock) — the relay itself is proven working.
* **⚠️ TRAP (cross-ref `KDE-RCA-004`):** do **not** disable/stop GSConnect (extension or `gsconnect.service`)
  or unpair it as "cosmetic duplicate-device cleanup". GSConnect is the **functioning OTP relay** (it owns the
  SMS cache). The two "NUC-Intel" entries on the phone are the expected twin daemons (`kdeconnectd` + GSConnect).
* **Answer — "can I have only 1 device that works?":** not for free. `kdeconnectd` and GSConnect advertise the
  same `NUC-Intel` identity over different transports (Tailscale vs LAN). Removing `kdeconnectd` to leave only
  GSConnect is possible, **but** `scripts/preflight_check.py` (L105) and `scripts/start_homelab.py` (L166) query
  `org.kde.kdeconnect.device.isReachable` **directly**, so removing `kdeconnectd` would break the readiness gate
  unless they are switched to `is_device_reachable()` (already GSConnect-fallback aware) or GSConnect's
  `Connected`. That is a scoped code change, not a config toggle. **Recommended interim:** keep **both** daemons
  (the duplicate is cosmetic) — GSConnect performs the OTP capture.
* **User Feedback & Context (2026-10-07):**
  - ผู้ใช้ต้องการให้ "KDE อ่าน SMS จากมือถือ" ได้จริง (ไม่ใช่แค่ทดสอบครั้งเดียว) และถามถึงการเหลือ NUC-Intel แค่ 1 รายการ
  - ผู้ใช้ยอมกด Accept pairing บนมือถือเพื่อให้ GSConnect กลับมาทำงาน

### ✅ LIVE END-TO-END AUTO-CAPTURE PROOF — `KDE-RCA-008` (2026-10-07 12:47)

> **FOURTH PASS (2026-10-07 12:47):** the relay is now proven **end-to-end on a real broker login with ZERO manual
> entry.** A fresh Liberator WebTrade login triggered a real 2FA SMS and the auto-poller captured it in ~1s.

* **What ran:** `LiberatorDriver.login(force_fresh=True)` (standalone, non-interactive), gated by Invariant 9
  `is_device_reachable() == True` before any SMS was fired.
* **Timeline (driver + daemon logs):**
  - `12:46:56` submit login → `12:46:59` page shows `(RefCode: LNQY)`
  - `12:47:00` **journal match** `kdeconnect.sms.messages → "Liberator OTPCode: 693130 (RefCode: LNQY)"`
    ⇒ `poll_active_notifications()` returned the OTP **automatically** (`OTPSource.KDE_CONNECT`)
  - `12:47:04` OTP submitted → `12:47:09` **AUTHENTICATED** (`/Market`), 11 cookies → `data/liberator_session.json`
    (new JWT exp `2026-10-08T05:47Z`, ~24h, `expired=False`)
* **Independent witness:** a separate read-only probe calling the *same* `poll_active_notifications()` printed
  `[12:47:02] *** CAPTURED *** OTP=693130 ref=LNQY source=OTPSource.KDE_CONNECT sender=Liberator`.
* **Cache proof:** `~/.cache/gsconnect/incoming_notifications.jsonl` grew `28,832 → 28,852`, mtime **12:47:00**
  (frozen at 11:29 all day) with `{"appName":"SMS","title":"Liberator","text":"Liberator OTPCode: 693130 (RefCode: LNQY)"}`.
* **New edge case (remember):** a *synthetic* test SMS (sent ~12:40) produced **no cache entry** because **MIUI posted
  no notification banner** — KDE Connect relays *notifications*, NOT the SMS database. Real broker/bank SMS (which always
  banner) relayed in ~1s. **Diagnostic rule:** empty relay + `isReachable=true` ⇒ suspect a missing phone notification,
  do NOT assume the bridge is dead.
* **Correction to the 09:33 abort:** that morning `AWAITING_OTP` abort was the readiness gate reading the unreliable
  `iconName='smartphonedisconnected'` (false-negative) — the same trap documented above; the gate now uses live D-Bus
  `isReachable` only.
* **Manual-entry masking note:** the 10:37 Krungsri capture was `source=api_manual_entry` (**MANUAL**) — it did NOT
  prove the auto path. The 12:47 Liberator capture is the **first proof of the automatic path**.


---

### 📌 Incident `KDE-RCA-009`: Self-Id / Bogus Device-Id Used as the Phone Target (Docs + Live Script)

* **รหัสเหตุการณ์และวันที่ (Incident ID & Date):** `KDE-RCA-009` (2026-10-08 — พบระหว่าง Zero-Contradiction reconciliation ของ `directive/kdeconnect.md`)

* **อาการที่พบ (Symptom):**
  - `directive/kdeconnect.md` §6.2/§7 สอนให้ ping มือถือด้วย `--device 556f3369d5474626971e0aa088abc699` ซึ่ง **ไม่ใช่มือถือ**
  - `scripts/krungsri/execute_live_sawad_sell.py` (live sell) ยิง `kdeconnect-cli --device a0149021_f4f1_4193_8497_9f27027c4423 --ping-msg …`
    → alert "ขาย SAWAD สำเร็จ" **ไม่เคยถึงมือถือ** และคำสั่งไม่ error → ล้มเหลวแบบเงียบ
  - ตรวจสด: `kdeconnect-cli -l` → มีเพียง `Mi 10T: 9507a3fd53f848da9135ebe6253db18a (paired and reachable)`

* **การสืบหาต้นตอ (Root Cause Analysis — 3 จุด):**
  1. **Identity confusion (NUC self-id)** — `~/.config/kdeconnect/` เก็บ **self-id ของ NUC เอง** =
     `556f3369d5474626971e0aa088abc699` (identity ที่ NUC ประกาศออกไป) ไม่ใช่ id ของคู่สนทนา
     → ผู้เขียนเอกสารหยิบไฟล์นี้มาเป็น target จึง ping ไปหาตัวเอง
  2. **Invalid id format** — `a0149021_f4f1_4193_8497_9f27027c4423` ใช้ **underscore** แต่ KDE Connect ใช้ **hex 32 ตัว** → ไม่ match อุปกรณ์ใดเลย
  3. **No error surface** — `subprocess.run([... "--device", <bogus> ...])` ไม่ raise เมื่อไม่พบ device → `try/except` ไม่ทำงาน
     + ยัง `print("Sent KDE Connect alert to Xiaomi Mi 10T!")` → **false success** (ขัด Anti-Mock Guardrail)

* **Edge Cases ที่พบ (Edge Cases Identified):**
  - `kdeconnect-cli -l` โชว์ทั้ง NUC (self) และมือถือ — ถ้าไม่แยกมักหยิบ self-id ผิด (NUC เองจะ `paired=false`, ชื่อซ้ำ "NUC-Intel" ×2 ตาม `KDE-RCA-004`)
  - **ping สำเร็จ ≠ ส่งถึง:** ต้องยืนยันด้วย `is_device_reachable()` หรือดูบนมือถือจริง
  - **ห้ามใช้ `iconName`/`statusIconName`** อ้าง reachability (`KDE-RCA-008`)
  - `app/services/kdeconnect_service.py` อ้าง `92bf51aa…` = **ตัวกรองตัด NUC** (ไม่ใช่ target) → **ถูกต้องแล้ว ห้ามแก้ตามล่า**

* **วิธีแก้ปัญหาที่พิสูจน์แล้ว (Proven Working Solution):**
  - **Single source of truth:** `app/core/config.py` → `KDECONNECT_DEVICE_ID = "9507a3fd53f848da9135ebe6253db18a"`
    — เอกสาร/สคริปต์ต้องอ้างค่านี้ ห้าม hard-code literal
  - แก้ `directive/kdeconnect.md` (§4.1/§6.2×2/§7) → `9507a3fd…` + comment ชี้ config
    (หลักฐาน: `grep -c 556f3369 → 0`, `grep -c 9507a3fd → 4`)
  - **ลบ** ping block ที่ hard-code id ปลอมออกจาก `scripts/krungsri/execute_live_sawad_sell.py` (block #14, 2026-10-08)
  - Pre-flight: `kdeconnect-cli -d 9507a3fd53f848da9135ebe6253db18a --ping-msg test` → ต้องเห็นบนมือถือจริง

* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้สั่ง **ลบ** การเรียก id ปลอมออกจากสคริปต์เทรดจริง (ไม่ใช่แค่แก้ค่า) เพื่อไม่ให้เข้าใจผิดว่า alert ทำงานอยู่
  - ผู้ใช้กำหนดให้บันทึกเป็น RCA (รายการนี้) และให้ handoff เขียน **ชัดเจนว่า มือถือ + Wi-Fi (Home LAN) ทำงานได้ทั้งคู่**
    — ขาเข้า (OTP relay → NUC) และขาออก (critical alert → มือถือ) โดยไม่ต้องพึ่ง Tailscale เมื่ออยู่บ้าน (สอดคล้อง `KDE-RCA-003`)
