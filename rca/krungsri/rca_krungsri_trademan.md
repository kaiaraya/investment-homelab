# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: Krungsri Securities (TradeMan)
**Broker Platform:** `KRUNGSRI` (TradeMan Pro & Member Portal)  
**Main URL:** `https://www.krungsrisecurities.com` | `https://trademan.in.th`  
**Target Accounts:** Cash Balance (`3024952`), Margin Credit Balance / SBL (`3024959`)  
**Last Updated:** 2026-10-07  
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing  

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose & PDCA Policy)
เอกสารนี้ทำหน้าที่เป็น **Single Source of Truth (SSOT)** สำหรับองค์ความรู้เฉพาะทางของ **Krungsri Securities (TradeMan)** เพื่อ:
1. บันทึก Root Cause, Edge Cases, และวิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Verified Solutions) จากการทดสอบจริง
2. ป้องกันไม่ให้ Agent หรือ Developer ต้องแก้ปัญหาเดิมซ้ำๆ ในวันพรุ่งนี้ ช่วยประหยัดเวลาและลดการใช้ Token
3. รวบรวม User Guidance และ Feedback เพื่อให้ระบบปรับตัวแบบ Self-Annealing ได้อย่างต่อเนื่อง

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :---: | :---: | :--- | :--- | :---: |
| 2026-09-29 | `KSS-RCA-001` | `trademan_sso_failed`: หา `#dropDownAccountPort` ไม่พบบนหน้าจอ | ป๊อปอัป "What's news" เด้งซ้อนกัน 2 ชั้น + หน้ารีไดเรกต์เข้า `/AssetsCenter` ไม่ใช่ `/Portfolio` | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-002` | การสลับบัญชี Cash (`3024952`) เสี่ยงหลุดหากโครงสร้าง Tag ใน Vuetify เปลี่ยน | ตัวเลือกใน Dropdown มีทั้ง `span`, `div`, `.v-list-item` | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-005` | Action Exit Parsing & Tactical Windows: จัดการคำสั่งปิดรอบเช้า Krungsri Margin | ไม้กำไรต้องล็อกเงินสด (10:00-10:30) ไม้ขาดทุนรอตลาดนิ่ง (10:30-12:00) และวาง Passive Offer1 Queue | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-006` | ความเสี่ยงชน Derivative Warrant (DW) เมื่อค้นหาชื่อย่อหุ้น (เช่น พิมพ์ SAWAD แต่ระบบดึง SAWAD01C...) | โมดอล Symbol Search เรียงผลลัพธ์แบบ Prefix ทำให้ DW ขึ้นมาก่อน หากใช้ `.first` หรือไม่กรองหมวด Stock จะเกิด Fat-Finger สั่ง DW แทนหุ้นแม่ | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-007` | TradeMan PIN Confirmation Modal & Broker-Specific PIN Isolation | ช่อง PIN ใช้ `input#pin` ซ่อนด้วย CSS font-family + ขาดการแยก `KRUNGSRI_PIN` ใน `.env` | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-008` | Autonomous Background Dispatcher & Offer 1 / Bid 1 Dynamic Engine | คำสั่ง `SCHEDULED` ขาดตัวยิงอัตโนมัติเมื่อถึงเวลายุทธวิธี (10:00+jitter) ต้องพึ่งพานักพัฒนามารันมือ | 🟢 RESOLVED |
| 2026-09-29 | `KSS-RCA-009` | 09:45 AM Pre-Flight Session Health Check & Proactive OTP Alerting | เซสชัน TradeMan เสี่ยงหลุดข้ามคืน หากไม่เช็กล่วงหน้าก่อน 10:00 น. จะติด 2FA OTP ส่งคำสั่งไม่ทัน | 🟢 RESOLVED |
| 2026-09-27 | `KSS-RCA-003` | SSO Timeout จากหน้าพอร์ทัลกรุงศรีเข้าสู่ TradeMan | หน้าต่าง Pop-up ถูกบล็อกโดย Chrome หรือไอคอน SSO ด้านขวาเปลี่ยนรูป | 🟢 RESOLVED |
| 2026-09-25 | `KSS-RCA-004` | 2FA SMS OTP Timeout บน Terminal | รหัสอ้างอิง (Ref Code) ไม่ตรง หรือเครือข่ายมือถือดีเลย์ | 🟢 RESOLVED |
| 2026-10-06 | `KSS-RCA-010` | Login S2: ไม่ได้รับ SMS OTP ภายใน 180s ทั้งที่ SMS ส่งมาจริง (Relay มาถึงช้า ~7m39s แล้วถูกทิ้ง) | KDE Connect bridge ตัด payload ที่มาถึงช้า เพราะเทียบ **phone-clock (เวลาสร้าง SMS)** แทน **arrival time** + journal window คงที่ 3 นาที (รายละเอียดเต็ม: `KDE-RCA-005` ใน `rca/shared/rca_kdeconnect_bridge.md`) | 🟢 RESOLVED + **LIVE S2 PASS** (2026-10-06 16:58; Ref `ZHXZ` captured ~3s; อ้างอิง `KDE-RCA-005`) |
| 2026-10-06 | `KSS-RCA-011` | **Session-Drop Blindness**: MCP `session_get_health` / preflight / SessionSentinel รายงานว่า "พร้อม" ขณะที่ `data/session_state.json` หายหรือหมดอายุจริง → ปิดกั้น Gate D | 3 ช่องโหว่: (1) MCP อ่านแค่ in-memory driver state ไม่เคยดูไฟล์ session (REST `/session/status` ดู); (2) Sentinel ข้าม health check เมื่อไม่มี live tab (`auth_driver.page is None`); (3) alert ผูกกับ `is_trading_hours()` 09:30–16:35 → หลุดข้ามคืนแบบเงียบ | 🟢 RESOLVED (2026-10-06) — ดู [Deep Dive](#-incident-kss-rca-011) |
| 2026-10-07 | `KSS-RCA-012` | **`switch_account` Timeout จาก 'Connection Lost' Dialog**: คลิก `#dropDownAccountPort` ล้มเหลว (`ElementHandle.click: Timeout 30000ms`) เพราะป๊อปอัป "Connection Lost" บังจอ และ Gemini Vision fallback ใช้ไม่ได้ (HTTP 429/503) | `FAST_DISMISS_SELECTORS` มีแต่ปุ่ม ปิด/X/รับทราบ + scrim ไม่มี selector ปุ่ม "Reconnect" ของ Connection-Lost dialog → Tier 1 ไม่แมตช์, Escape ไม่ปิด, Gemini พัง → `dismiss_popups()` คืน False ปล่อย overlay ค้าง | 🟢 RESOLVED (2026-10-07) — Tier 0 Reconnect ใน `popup_manager`; ดู [Deep Dive](#-incident-kss-rca-012) |
| 2026-10-07 | `KSS-RCA-013` | **Zero-OTP Session Wiped by a Transient Timeout**: หลัง login Krungsri สำเร็จสด (OTP `807258`, เขียน `data/session_state.json` แล้ว) การรัน diagnostic เจอ `Page.goto: Timeout 12000ms` ใน `verify_saved_session()` → ไฟล์เซสชันที่ยัง **ใช้ได้** ถูกลบทิ้งทันที → ต้อง login ใหม่ (เผา SMS OTP + เสี่ยง lock) | `KrungsriAuthDriver.verify_saved_session()` มี `os.remove(SESSION_STATE_PATH)` **2 จุด** (except=timeout ชั่วคราว + else=หา selector ไม่เจอ) โดยไม่มีหลักฐานว่าเซสชันหมดอายุจริง → ละเมิด Invariant 8 | 🟢 RESOLVED (2026-10-07) — non-destructive quarantine; ดู [Deep Dive](#-incident-kss-rca-013) |
| 2026-10-07 | `KSS-RCA-014` | **Order Ledger อ่านคอลัมน์ผิด (symbol=UNKNOWN, status=<เวลา>)**: `scrape_all_orders()` คืน `symbol=UNKNOWN` ทุกแถว และ `status_raw` เป็นเวลา (เช่น `16:29:55`) บนแท็บ 'View Order' | ใช้ `page.query_selector_all("table tbody tr")` กว้างเกินไป (ปนตาราง Watchlist/กองทุน) + `switch_tab('order_status')` ใช้ `div:has-text('View Order')` กำกวม → อ่าน table/คอลัมน์ผิด | 🟢 RESOLVED (2026-10-07) — Deterministic Table Header Isolation; ดู [Deep Dive](#-incident-kss-rca-014) |
| 2026-10-08 | `KSS-RCA-015` | **Full-suite ลบ Zero-OTP session สดทิ้ง (เป็นเส้นทางที่ 2 ที่ `KSS-RCA-013` ปิดไม่ถึง)**: หลัง D2 ทำให้ `data/session_state.json` สดใหม่ (60 cookies @ 21:01) การรัน `pytest tests/ -q` ทำให้ไฟล์ **หายไปตอน ~21:08** โดยไม่มี backup → ต้อง login ใหม่ (เผา SMS OTP) | `tests/test_browser_driver.py::test_session_logout_endpoint` ยิง `POST /api/v1/session/logout` เข้า **app จริง** โดย **ไม่ monkeypatch** `settings.SESSION_STATE_PATH` → `app/api/v1/endpoints/session.py:103` เรียก `os.remove(settings.SESSION_STATE_PATH)` ลบไฟล์จริง · guard test เดิม (`tests/test_auth_session_nondestructive.py`) คุมเฉพาะเส้นทาง `verify_saved_session()` **ไม่ครอบคลุม logout endpoint** | 🟡 **OPEN + พิสูจน์ซ้ำ 2026-10-09 (full suite ผ่านเต็มแต่ไฟล์ session หาย)** (นอก scope ของ handoff `TASK-otp-channel-authoritative.md`) — ต้อง monkeypatch `SESSION_STATE_PATH` → `tmp_path`; ดู [Deep Dive](#-incident-kss-rca-015) |

| 2026-10-09 | `KSS-RCA-016` | **Fabricated Order IDs + No Native "Change" Button**: `execute_order` คืน `order_id` ปลอมรูป `ORD-<epoch>` และสมมติว่ามีปุ่ม "Change" บนหน้า View Order (ความจริง **ไม่มี**) → amend/ต่อราคาทำจริงไม่ได้ | (1) TradeMan ไม่มีปุ่ม Change (พิสูจน์สด 2026-10-09: `data/krungsri_order_actions_dump.json`) → amend ต้อง = Cancel + Re-submit; (2) driver สังเคราะห์ order id เองแทนการอ่าน `Order No.` จริงจาก ledger | 🟢 RESOLVED (2026-10-09) — ดู [Deep Dive](#-incident-kss-rca-016) |
| 2026-10-09 | `KSS-RCA-017` | **SHORT Uptick หลวม + `last` ปลอม**: `validate_short_uptick` ยอมให้ตั้งราคา `== last` (zero-plus tick) และ Price Negotiation ปั้น `last` จากราคาคำสั่งตัวเอง → เสนอราคา SHORT ที่ตลาด reject | SSOT ใช้ `>=` (ควรเป็น strict `>`); `price_negotiation_service` มี `last = quote.get("last") or bid_1 or offer_1 or current_order_price` (Anti-Mock violation); driver มีการตีความ uptick สองแบบขัดกัน | 🟢 RESOLVED (2026-10-09) — ดู [Deep Dive](#-incident-kss-rca-017) |
| 2026-10-09 | `KSS-RCA-018` | **Amend LIVE ยกเลิกคำสั่งจริงแล้ว Re-submit ตกกลับเข้า DRY_RUN (Guard ไม่สมมาตร) → Position หาย**: `cancel_order` ยกเลิกคำสั่งจริงสำเร็จ (เผา PIN) แต่ `execute_order` ยังคืน `SIM-<epoch>` ไม่ส่งคำสั่งใหม่ ⇒ SHORT position หายถาวร ขณะที่ caller ได้ `success=True` | (1) Guard ไม่สมมาตร — `cancel_order`/`modify_order_price` gate `DRY_RUN_MODE and not bypass_dry_run` แต่ `execute_order` gate `DRY_RUN_MODE` เดี่ยว ๆ **2 จุด**; (2) `execute_order` ไม่มีพารามิเตอร์ `bypass_dry_run` แต่มี `**kwargs` → flag ถูก **กลืนเงียบ** (silent no-op); (3) amend ไม่ atomic ไม่มี compensation | 🟢 RESOLVED (2026-10-09) — โค้ด+เทสต์; 🟡 **LIVE round-trip ยังไม่พิสูจน์** (รอบจริงถูก reject ที่ uptick ก่อนถึง cancel) ดู [Deep Dive](#-incident-kss-rca-018) |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `KSS-RCA-001`: Stacked Double Popups & Landing URL Mismatch
* **วันและเวลา:** 2026-09-29 07:36 น.
* **อาการ (Symptom):**  
  ระบบเข้าสู่ Watch-and-Learn HITL Grace Period (90 วินาที) และระบุข้อยกเว้น:
  ```
  RuntimeError: TradeMan SSO verification failed: #dropDownAccountPort not visible after login. Current URL: https://trademan.in.th/AssetsCenter
  ```
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  1. จากการตรวจสอบไฟล์ Snapshot `data/trademan_sso_failed_20260929_073655.html` และภาพถ่ายหน้าจอ พบว่า TradeMan เรนเดอร์โมดอลป๊อปอัป *"What's news มีอะไรใหม่ TRADEMAN Version 1.7.4.19"* ซ้อนกัน **2 ชั้นพร้อมกัน** (`z-index: 2400` และ `z-index: 2410`) เมื่อโค้ดเดิมสั่งคลิกปิดไปเพียง 1 ครั้ง ป๊อปอัปชั้นที่ 2 ยังคงค้างและบล็อกการโต้ตอบหน้าจอทั้งหมด
  2. การ SSO มาจากพอร์ทัลกรุงศรีผ่าน efin token (`https://www.efin.finance/auth_sso?token=...`) จะพาเบราว์เซอร์ไปลงที่หน้า `https://trademan.in.th/AssetsCenter` โดยค่าเริ่มต้น ซึ่งหน้า `AssetsCenter` **ไม่มีองค์ประกอบ `#dropDownAccountPort`** ใน DOM (จะปรากฏเฉพาะบนหน้า `https://trademan.in.th/Portfolio`)
* **Edge Cases ที่พบ:**  
  * การกดปิดผ่าน `.v-overlay button` ตัวเดียวไม่พอ เพราะมี Overlay ซ้อนกัน
  * ช่องติ๊ก `input.disable_show` ต้องถูกคลิกทั้งสองชั้นก่อนปิด เพื่อไม่ให้เด้งกลับมาในรอบถัดไป
  * การนำทางแบบ SPA ภายใน Nuxt อาจยัง Hydrate ไม่เสร็จ หากกด `#Menu_Portfolio_tab` ทันทีอาจเกิด No-op
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ใน [app/browser/auth_driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/auth_driver.py):
  1. ใช้ JavaScript DOM Evaluate กวาดติ๊ก `input.disable_show` ทุกตัว และคลิกปุ่มปิดทุก Overlay พร้อมกันเป็นรอบๆ พร้อมส่งคีย์ `Escape` ยืนยัน:
     ```javascript
     document.querySelectorAll("input.disable_show, input[type='checkbox']").forEach(cb => {
         if (!cb.checked) cb.click();
     });
     document.querySelectorAll(".v-overlay--active .absolute.top-3.right-3 button, .v-overlay--active button").forEach(btn => {
         btn.click();
     });
     ```
  2. ตรวจสอบว่าหาก URL ปัจจุบันไม่ใช่ `/Portfolio` ให้ทำการย้ายหน้าตรงทันที:
     ```python
     if "trademan.in.th" in active_page.url.lower() and "portfolio" not in active_page.url.lower():
         await active_page.goto(settings.TRADEMAN_PORTFOLIO_URL, wait_until="domcontentloaded", timeout=15000)
     ```
* **User Feedback & Context:**  
  ผู้ใช้กำชับให้แยกวิเคราะห์หาสาเหตุที่แท้จริง ประเมินผลกระทบ และให้ระบบแก้ปัญหาด้วยตนเองก่อน (Self-Annealing)

---

### 📌 Incident `KSS-RCA-002`: Multi-Tag Resilient Account Switcher
* **วันและเวลา:** 2026-09-29 07:38 น.
* **อาการ (Symptom):**  
  เมื่อคลิกเปิด Dropdown `#dropDownAccountPort` แล้วหาเลขบัญชีเป้าหมายไม่เจอเนื่องจาก Selector เดิมเจาะจงเฉพาะ `span:has-text('3024952')`
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  คอมโพเนนต์ Dropdown ของ TradeMan ใช้ Vuetify Menu (`.v-menu` / `.v-overlay`) ซึ่งโครงสร้างภายในอาจเรนเดอร์เป็น `span`, `div`, หรือ `.v-list-item` ขึ้นอยู่กับ Responsive View หรือเวอร์ชันของ Nuxt Theme
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ใน [app/browser/trademan_driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/trademan_driver.py):
  กำหนด Tag Fallback Pyramid ตามลำดับความแม่นยำ:
  ```python
  target_selectors = [
      f"span:has-text('{target_acc_no}')",
      f".v-list-item:has-text('{target_acc_no}')",
      f"div:has-text('{target_acc_no}')",
      f"button:has-text('{target_acc_no}')",
      f":has-text('{target_acc_no}')"
  ]
  ```
  เมื่อพบตัวเลือกจะคลิกและรอ 1.5 วินาทีเพื่อให้ตาราง Portfolio รีเฟรชข้อมูล

---

### 📌 Incident `KSS-RCA-003`: 2FA SMS OTP Auto-Capture via KDE Connect
* **วันและเวลา:** 2026-09-29 07:34 น.
* **อาการ (Symptom):**  
  การล็อกอินพอร์ทัลกรุงศรีบังคับใช้ 2FA SMS OTP เสมอ ทำให้ไม่สามารถทำ Headless แบบ Unattended ได้หากไม่มีกลไกดักจับ
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  Krungsri ส่ง SMS เข้าเบอร์โทรศัพท์ของผู้ใช้ พร้อม Ref Code ภาษาอังกฤษ 4 ตัว เช่น `[Ref: GAFJ]`
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. ใช้ `kdeconnect-cli` ดักจับข้อความแจ้งเตือนจาก Xiaomi Mi 10T (`9507a3fd53f848da9135ebe6253db18a`) ผ่าน Tailscale
  2. สกัดรหัสผ่าน Regex `Ref[:\s]+([A-Z]{4})` และดึงตัวเลข 6 หลัก ส่งต่อไปยัง EventBus / SQLite DB
  3. ไดรเวอร์กรอกรหัสและกดปุ่มยืนยันภายใน 2 วินาทีโดยอัตโนมัติ

---

### 📌 Incident `KSS-RCA-004`: Zero-OTP Direct Session Persistence
* **วันและเวลา:** 2026-09-29 07:40 น.
* **อาการ (Symptom):**  
  การล็อกอินใหม่ทุกครั้งทำให้ต้องขอ SMS OTP บ่อยครั้ง เสี่ยงติด Limit การส่ง SMS ของโบรกเกอร์
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  เซสชันของ TradeMan สามารถคงอยู่ได้นานหลายชั่วโมง หากทำการบันทึก Cookie Storage State ไว้
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. หลังจากล็อกอินสำเร็จ บันทึก Cookies ทั้งหมดลง `data/session_state.json`
  2. เมื่อเริ่มรันงานใหม่ โหลด Storage State และเปิดตรงไปที่ `https://trademan.in.th/Portfolio`
  3. ตรวจสอบว่า `#dropDownAccountPort` ปรากฏภายใน 6 วินาทีหรือไม่ หากพบ แสดงว่าเซสชันยังสมบูรณ์ เข้าเทรด/กวาดพอร์ตต่อได้ทันทีภายใน 3 วินาทีโดยไม่ต้องขอ OTP ซ้ำ

---

| 2026-09-29 | `KSS-RCA-005` | Action Exit Parsing & Tactical Windows: จัดการคำสั่งปิดรอบเช้าตามสถานะ Win/Loss | ไม้กำไรต้องรีบล็อกเงินสด (10:00-10:30) แต่ไม้ขาดทุนต้องรอตลาดนิ่งหลัง 10:30 (10:30-12:00) และห้ามเคาะขวา Matched ทันที | 🟢 RESOLVED |

---

### 📌 Incident `KSS-RCA-005`: Natural Language Tactical Action Exit & Window Allocation
* **วันและเวลา:** 2026-09-29 08:30 น.
* **อาการ (Symptom):**  
  ผู้ใช้ต้องการนำเข้าข้อความสรุป Action Exits ประจำวัน (ภาษาไทย มีอีโมจิ แท็ก `[Timeout]`, `[Weed-out]`, P&L %, ATR, และเหตุผล) สำหรับพอร์ต Krungsri Margin `3024959` เพื่อส่งคำสั่งขาย/ซื้อคืนตามกติกา Tactical Windows โดยไม่ต้องคีย์ทีละคำสั่งด้วยมือ และต้องมีระบบความปลอดภัยป้องกันไม่ให้ส่งคำสั่งทันทีก่อนได้รับอนุญาต
* **การสืบหาต้นตอและกติกา (Root Cause & Tactical Rules):**  
  1. การส่งคำสั่งปิดไม้ในตอนเช้ามีความเสี่ยงเรื่องความผันผวนของราคาช่วงเปิดตลาด:
     - **ไม้กำไร (Profitable, P&L >= 0%)**: เช่น SAWAD (+0.45%) ต้องส่งในช่วง **10:00 - 10:30** เพื่อล็อกกำไรปลดล็อกเงินสด พร้อมใส่ Random Jitter (1-5 นาที)
     - **ไม้ขาดทุน (Losing, P&L < 0%)**: เช่น COCOCO (-0.88%), AAV (-2.33%) ต้องรอหลัง **10:30** ไปก่อน (ส่งช่วง **10:30 - 12:00** ไม่เกินเที่ยง) เพื่อรอให้ตลาดเคลียร์แรงขายช่วงเปิด พร้อมใส่ Random Jitter (3-15 นาที)
  2. กติกาการตั้งราคา: **ห้าม Matched ทันที (No Immediate Match)**:
     - คำสั่ง **SELL**: ต้องตั้งคิวแบบ Passive ที่ **Offer 1** (Best Ask) บนกระดาน (`Queuing - SX`) เพื่อต่อรองราคาให้ดีที่สุด ไม่กิน Bid
     - คำสั่ง **COVER**: ต้องตั้งคิวแบบ Passive ที่ **Bid 1** (Best Bid) บนกระดาน (`Queuing - BX`) ไม่กิน Offer
  3. **Volatility & Price Deviation Guard**:
     - หากราคาตลาด ณ เวลาส่งคำสั่งเบี่ยงเบนเกิน 2-3 Ticks หรือเกิน ±1.5% จากราคาใน Briefing (โดยเฉพาะเปิด Gap Down) ต้องระงับการส่งทันทีและยิง Alert แจ้งเตือนด่วนเข้า Mi 10T
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. สร้าง `ActionExitService` ใน `app/services/action_exit_service.py` สกัดข้อมูลด้วย Regex ตรวจจับหัวพอร์ต `🏛️ [พอร์ต Krungsri Margin - KSS]` แมปเข้าบัญชี `3024959`
  2. จัดแบ่งคำสั่งเข้าสู่ช่วง Window อัตโนมัติ พร้อมสุ่ม Jitter
  3. บันทึกคำสั่งเข้าคิว SQLite ด้วยสถานะ `AWAITING_HITL_CONFIRMATION` และยิง Critical Alert เข้ามือถือ Xiaomi Mi 10T ผ่าน KDE Connect CLI
  4. เพิ่มการรองรับสถานะ `SCHEDULED` ใน `OrderStatus` เมื่อผู้ใช้กดยืนยัน Pre-Approve คำสั่งจะเข้าสู่คิวรอส่งตาม Window
  5. พัฒนาหน้าจอ Cockpit บน `app/console.py` แสดงแถบ Golden Pending Orders Banner แยกสีและป้ายกำกับ 🟢 Win (10:00-10:30) vs 🔴 Loss (10:30-12:00) และปุ่ม 1-Click Confirm All
  6. เปิดให้สั่งการผ่าน Remote MCP Tool `strategy_action_exit_from_text` ใน Pillar 6 ได้อย่างสมบูรณ์

---

### 📌 Incident `KSS-RCA-006`: Derivative Warrant (DW) Collision Risk in Symbol Search & Exact Match Protocol
* **วันและเวลา:** 2026-09-29 08:55 น.
* **อาการ (Symptom):**  
  เมื่อพยายามทดสอบการกรอกคำสั่งขายหุ้น `SAWAD` (100 หุ้น @ 22.50) บนแผง Buy/Sell ของ TradeMan โดยเปิดโมดอล `Symbol Search` แล้วพิมพ์คำว่า "SAWAD" ระบบกลับเลือกได้ `SAWAD01C2612A` (ใบสำคัญแสดงสิทธิอนุพันธ์ หรือ Derivative Warrant - DW) เข้าไปในช่อง Symbol แทนที่จะเป็นหุ้นสามัญ `SAWAD`
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  1. ในโมดอล `Symbol Search` ของ TradeMan ค่าเริ่มต้นจะอยู่ในแท็บ **"All"** ซึ่งรวบรวมหลักทรัพย์ทุกประเภท ทั้ง หุ้นสามัญ (Stock CS), กองทุน ETF, หุ้นบุริมสิทธิ (CSF), และ Derivative Warrants (DW)
  2. เมื่อพิมพ์คำค้นหา เช่น "SAWAD" รายการผลลัพธ์จะแสดงผลตามอัลกอริทึมการค้นหา โดย DW เช่น `SAWAD01C2612A` อาจขึ้นมาเป็นแถวแรกๆ ก่อนหุ้นแม่
  3. หาก Automation หรือ Selector ใช้วิธีจับตัวแรก (`.first`) หรือใช้ Substring Matching (`has_text("SAWAD")`) โดยไม่ตรวจความยาวสตริงและประเภทหลักทรัพย์ จะทำให้เกิด **Critical Fat-Finger Error** ส่งคำสั่งผิดประเภทสินทรัพย์ ซึ่งมี gearing, อัตราใช้สิทธิ, และวันหมดอายุที่ต่างกันโดยสิ้นเชิง
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution - 3-Tier Guardrails):**  
  1. **Tier 1 (Direct Table Selection - ปลอดภัยที่สุด 100% สำหรับการปิดไม้/ขาย/คืนหุ้น):**  
     บนหน้าจอ Portfolio หรือ Watchlist มีตารางแสดงรายการหุ้นอยู่แล้ว การคลิกที่เซลล์ของตารางโดยตรงด้วย Exact Text `td:text-is('{symbol}')` เช่น `td:text-is('SAWAD')` จะทำให้ TradeMan อัปเดต Active Symbol บนแผง Buy/Sell เป็น `SAWAD` โดยตรงทันที ไม่ต้องเปิดโมดอลค้นหา และไม่มีโอกาสชน DW แม้แต่น้อย
  2. **Tier 2 (Stock Filter Mode ในโมดอลค้นหา):**  
     หากจำเป็นต้องเปิดโมดอลค้นหา (กรณีหุ้นที่ไม่ได้อยู่ในพอร์ต) Automation **ต้องคลิกปุ่มกรอง "Stock"** ในโมดอลค้นหาก่อนเสมอ เพื่อตัดหมวด DW และ ETF ทิ้งทั้งหมด
  3. **Tier 3 (Strict Exact Matching & Post-Selection Assertion):**  
     - ตรวจสอบความถูกต้องของชื่อย่อแบบ Exact String (`el.innerText.trim() === target_symbol`)
     - ตรวจสอบกล่อง Symbol ในแผงคำสั่งว่าแสดงตรงกับเป้าหมายทุกตัวอักษร
     - สำหรับคำสั่งขาย (SELL/COVER) ให้ Assert ตรวจสอบว่าช่อง `On Hand` สอดคล้องกับยอดคงเหลือในพอร์ต (เช่น SAWAD มี 2,200 หุ้นจริง) ก่อนอนุญาตให้กรอก Volume และคลิก Send

---

### 📌 Incident `KSS-RCA-007`: TradeMan PIN Confirmation Modal & Broker PIN Separation
* **วันและเวลา:** 2026-09-29 09:15 น.
* **อาการ (Symptom):**  
  เมื่อคลิกปุ่ม `#send_order__btn` มีโมดอล `.v-overlay--active` เด้งขึ้นมาถาม PIN แต่ Automation หาช่อง `input[type='password']` ไม่พบ ทำให้คำสั่งค้างหน้าจอ
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  1. โครงสร้าง DOM ของ TradeMan ใช้ ID เจาะจงคือ `input#pin` และซ่อนตัวเลขด้วย CSS `style="font-family: password;"`
  2. มี Checkbox จำรหัส `input#savepin` ซึ่งควรติ๊กเพื่อจำ PIN ไว้ในรอบเซสชัน
  3. ปุ่มกดยืนยันในโมดอลไม่ได้ชื่อ Submit แต่เป็นปุ่มสีแดง (สำหรับ Sell) หรือสีเขียว (สำหรับ Buy) ที่มีตัวอักษร `Sell` หรือ `Buy` ในแท็ก `span` (`.v-overlay--active button:has(span:text-is('{Side}'))`)
  4. เดิมไฟล์ `.env` มีเฉพาะ `TRADING_PIN` รวม ทำให้เสี่ยงนำ PIN ผิดโบรกเกอร์มาใช้
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. แยกตัวแปร `KRUNGSRI_PIN="<redacted>"` ชัดเจนใน `.env` และ `app/core/config.py`
  2. อัปเดตไดรเวอร์ให้ตรวจจับโมดอล กรอก `input#pin`, ติ๊ก `input#savepin`, และคลิกปุ่มยืนยันตามฝั่งคำสั่ง

---

### 📌 Incident `KSS-RCA-008`: Autonomous Background Dispatcher & Offer 1 / Bid 1 Dynamic Engine
* **วันและเวลา:** 2026-09-29 10:45 น.
* **อาการ (Symptom):**  
  เมื่อคำสั่ง Action Exit ผ่านการวิเคราะห์และเข้าสู่สถานะ `SCHEDULED` ระบบกลับไม่มีตัวยิงคำสั่งอัตโนมัติเมื่อถึงเวลายุทธวิธี (เช่น 10:03 น. หรือ 10:36 น.) ต้องให้ผู้ใช้หรือนักพัฒนามารันสคริปต์ด้วยมือ
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  ขาด Background Asyncio Poller Daemon ที่เชื่อมต่อกับ FastAPI Lifespan เพื่อคอยมอนิเตอร์เวลาเปิดตลาด SET และตาราง `orders` ใน SQLite
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. สร้าง `ActionExitDispatcher` ใน [`app/services/action_exit_dispatcher.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/action_exit_dispatcher.py) เชื่อมต่อเข้ากับ `lifespan` ใน [`app/main.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/main.py)
  2. รันลูปตรวจทุก 15 วินาที เมื่อเวลาปัจจุบันถึง `scheduled_time` จะดึงราคาตลาดสด:
     - ฝั่ง `SELL`: ตั้งขายที่ราคา Best Offer 1 เพื่อต่อคิวหัวแถว
     - ฝั่ง `COVER`: ตั้งซื้อปิดชอร์ตที่ราคา Best Bid 1 เพื่อต่อคิวหัวแถว
  3. เฝ้าตรวจสถานะคำสั่งจนกระทั่งจับคู่สำเร็จ (`MATCHED`) แล้วยิงสรุปผลเข้ามือถือผ่าน KDE Connect

---

### 📌 Incident `KSS-RCA-009`: 09:45 AM Pre-Flight Session Health Check & Proactive OTP Alerting
* **วันและเวลา:** 2026-09-29 11:00 น.
* **อาการ (Symptom):**  
  เซสชันเบราว์เซอร์ของ TradeMan อาจหมดอายุข้ามคืน หากระบบไม่เตรียมการล่วงหน้าแล้วมารันตอน 10:00 น. พอดี การติด 2FA SMS OTP จะทำให้ส่งคำสั่งล่าช้าและพลาดราคาเปิด
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  การยืนยันตัวตนของ Krungsri บังคับใช้ OTP เมื่อเซสชันขาด จึงจำเป็นต้องมีเวลาเตรียมตัว (Grace Period) ก่อนตลาดเปิดจริง
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. เพิ่มฟังก์ชัน `_check_preflight_session` ใน `ActionExitDispatcher` ทำงานอัตโนมัติช่วงเวลา 09:45 - 09:55 น. ทุกวันทำการ
  2. หากเซสชันปกติ จะยิงแจ้งเตือนสีเขียวเข้ามือถือยืนยันความพร้อม
  3. หากเซสชันหมดอายุ จะเริ่มล็อกอินทันที และหากต้องการ OTP จะยิง Critical Alert พร้อม Ref Code เข้า Xiaomi Mi 10T ทันทีเพื่อให้ผู้ใช้เตรียมกรอกก่อน 10:00 น.

---

### 📌 Incident `KSS-RCA-010`: Login S2 — SMS OTP มาถึงช้าแล้วถูกทิ้ง (Bridge-Side, อ้างอิง `KDE-RCA-005`)

* **วันและเวลา:** 2026-10-06 (Live S2 login test)
* **อาการ (Symptom):**
  `_wait_for_otp_multi_channel` เฝ้า OTP 180s แล้ว **Timeout** ทั้งที่ Krungsri ส่ง SMS OTP จริง
  (`Your OTP is 749455 (Ref : VJKR)`) — SMS ถูกสร้าง 15:53:50.765 แต่มาถึง NUC 16:01:29 (**ช้า ~7m39s**)
* **การสืบหาต้นตอ (Root Cause Analysis):**
  ปัญหา**ไม่ได้อยู่ที่ฝั่ง Krungsri** แต่อยู่ที่ Hardware Bridge (shared):
  `poll_active_notifications` ตัด record ที่มาถึงช้าทิ้ง เพราะเทียบอายุกับ **phone-clock (เวลาสร้าง SMS)**
  แทน **arrival time** และ journal scan ใช้หน้าต่างคงที่ 3 นาที (รายละเอียดเต็ม: `KDE-RCA-005`)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - **ขยาย `OTP_TIMEOUT_SECONDS` ไม่ช่วย** — SMS ระบุ "expired within 5 mins" แต่ relay ใช้ 7m39s ⇒ OTP หมดอายุแล้ว
  - ต้องแยกบทบาท: ปัญหา SMS-channel เป็นของ shared bridge ห้ามปะปนเข้า logic เทรดของ Krungsri (Broker Knowledge Isolation)
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  1. `auth_driver.login()` ส่ง `since_ms=wait_start_time` เข้า `poll_active_notifications(expected_ref=self.current_ref, since_ms=...)`
  2. Ref Code ที่ตรง (`VJKR`) เป็น **definitive match** → ข้าม age guard
  3. journal scan ผูกกับเวลาที่ขอ OTP แทนหน้าต่างคงที่ + GSConnect เป็น link คู่ขนาน
  4. หลักฐาน: replay OTP จริงด้วย `scripts/replay_kde_rca005.py` → `otp=749455 ref=VJKR` (0.16s) **PASS**
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้กำหนด scope แบบ option 1 (U2+U3+U4) และเน้นว่าต้องมีหลักฐานจริงก่อนไปขั้นถัดไป (S3 `session_state.json`)

* **✅ Live S2 Re-Test Confirmation (2026-10-06 16:58):**
  - รัน `login --force-fresh` จริง → SMS OTP **รอบใหม่** `Ref ZHXZ` / `682729` ถูกจับผ่าน KDE Connect ใน **~3 วินาที** (Ref announced 16:58:32 → captured 16:58:35) → SSO verified (`#dropDownAccountPort` visible, `trademan.in.th/Portfolio`) → `data/session_state.json` เขียนใหม่ (27,879 B / 60 cookies)
  - **Verdict: PASS** — ปิด loop ของการแก้ `KDE-RCA-005` บนข้อมูลโบรกเกอร์จริง และผ่านเกณฑ์ S3 (`session_state.json` Zero-OTP persistence) ไปพร้อมกัน

---

### 📌 Incident `KSS-RCA-011`: Session-Drop Blindness (MCP / Preflight / SessionSentinel)

* **วันและเวลา:** 2026-10-06 ~22:40 น. (ค้นพบขณะเตรียม live verification "Gate D")
* **อาการ (Symptom):**
  - `session_get_health` (MCP) คืน `krungsri_trademan.authenticated = false` แต่ **ตอบไม่ได้ว่า**
    "ไม่มีไฟล์ session เลย" หรือ "มีไฟล์แต่ driver ยังไม่ attach" → agent ตัดสินใจผิดบริบท
  - `scripts/preflight_check.py` พิมพ์ `✅ Krungsri TradeMan: Saved cookies exist` โดยอิง
    `os.path.exists()` เท่านั้น (ขณะที่ไฟล์อาจเก่า ~27 ชม. = หมดอายุแล้ว)
  - `SessionSentinel` ไม่แจ้งเตือนเมื่อไฟล์ session หาย หากไม่มี live tab และไม่แจ้งนอกเวลาทำการ
    (`is_trading_hours()` 09:30–16:35) → session หลุดข้ามคืนแบบ **เงียบสนิท**
* **การสืบหาต้นตอ (Root Cause Analysis — 3 จุด):**
  1. **Session & Context Isolation:** MCP tool อ่านแต่ in-memory driver state
     (`app/mcp/pillars/pillar1_session.py` L27–30) ขณะที่ REST `GET /api/v1/session/status`
     มี `session_file_exists` อยู่แล้ว → **MCP drift from REST**
  2. **DOM & UI Reality:** `SessionSentinel._monitor_loop` เรียก `_perform_health_check()`
     ก็ต่อเมื่อ `auth_driver.is_authenticated and auth_driver.page` → ไม่มี tab = ไม่ตรวจอะไรเลย
  3. **Data Schema & Types:** trade-off ของ TradeMan SSO คือคุกกี้เป็น **session cookie**
     (`expires: -1`, ไม่มี JWT `exp` แบบ Liberator `LIB-RCA-006`) → **ไม่มีสัญญาณหมดอายุ offline**
     จึงต้องใช้ **presence + age ของไฟล์** เป็นตัวชี้วัด
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - "ไฟล์ session มีอยู่" ≠ "session ใช้ได้" (โดยเฉพาะงานที่ทำข้ามคืน/ข้ามวันหยุด)
  - preflight/driver/sentinel/MCP ต้องไม่ให้คำตัดสินขัดกัน (Zero-Contradiction)
  - ไฟล์ JSON เสียหาย (corrupt) → ห้ามเชื่อ presence อย่างเดียว (cookie_count = 0)
  - alert ซ้ำทุก tick = รบกวนผู้ใช้ → ต้อง dedupe (transition-based + once-per-day)
  - heartbeat interval (1800s) **ยาวกว่าหน้าต่าง 09:45–09:55** → loop อาจกระโดดข้ามหน้าต่างไปเลย
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  1. **Single source of truth**: `app/brokers/krungsri/session_health.py::session_file_info()`
     (browser-free, stdlib-only) คืน `{exists, mtime_iso, age_hours, cookie_count,
     needs_fresh_login, reason}` โดย `reason ∈ {MISSING, STALE, RECENT}` (STALE = age > 12h)
  2. **MCP** `pillar1_session.session_get_health()` เพิ่ม `session_file_exists`,
     `session_file_mtime`, `session_file_age_hours`, `needs_fresh_login`, `session_file_reason`
     (align กับ REST) — หลักฐานสด: `needs_fresh_login=true, reason=MISSING`
  3. **Sentinel** เพิ่ม `_check_session_file_transition()` เรียกใน `_monitor_loop` **ทุก tick**
     (ไม่ผูกกับ live tab หรือ trading hours) → log `SESSION_FILE_LOST` / `SESSION_FILE_EXPIRED`
     + ยิง **LINE + KDE Connect** (`_alert_session_drop`)
  4. **Pre-market** `is_premarket_window()` / `seconds_until_premarket_window()` +
     `_check_premarket_warning()` (Weekday 09:45–09:55 BKK, once/day) และ
     `_next_wait_seconds()` cap sleep ให้ loop ลงจอดในหน้าต่างเสมอ
  5. **Preflight** `check_krungsri_session()` ใช้ `krungsri_session_status()` (= `session_file_info`)
     → เลิกพิมพ์ ✅ ลอย ๆ; missing→⚠️ / stale→⚠️ EXPIRED / recent→ℹ️
  6. Regression tests: `tests/test_krungsri_session_health.py`,
     `tests/test_session_drop_detection.py`, `tests/test_preflight_check.py`
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้สั่งทำ Phase A (session-drop detection) ให้เสร็จก่อน Phase B (Gate D live login)
  - ต้องใช้หลักฐานจริงทุกครั้ง (รัน preflight จริง + เรียกโค้ดจริง) — ห้ามสรุปจากสมมติฐาน
  - **หมายเหตุ:** uvicorn ที่รันค้างอยู่จะ cache โมดูลเก่า → ต้อง restart ก่อน Gate D
    เพื่อให้ REST `/api/v1/session/health` คืน key ใหม่

---

### 📌 Incident `KSS-RCA-012`: 'Connection Lost' Dialog — Offline Reconnect (Zero Gemini Dependency)
* **วันและเวลา:** 2026-10-07 00:25–00:44 น. (ICT) — ค้นพบขณะทำ Pillar-2 per-account live evidence capture
* **อาการ (Symptom):**
  - `switch_account(KRUNGSRI, ...)` ล้มเหลว: `ElementHandle.click: Timeout 30000ms exceeded` ที่การคลิก `#dropDownAccountPort`
  - ป๊อปอัป **"Connection Lost"** ของ TradeMan SPA (Vuetify `.v-overlay-container`) บังอยู่บนจอ → ทุกคลิกใต้ overlay ล้มเหลว
  - `popup_manager.dismiss_popups()` ปิดไม่ได้ → ปล่อย overlay ค้าง → switch/สแครปพอร์ตทั้งหมด timeout
  - Gemini Vision fallback (Tier 2) ใช้ไม่ได้ในรอบนั้น (HTTP **429 / 503**) → ไม่มีอะไรช่วยปิด
* **การสืบหาต้นตอ (Root Cause Analysis — 3 จุด):**
  1. **Session & Context Isolation:** SPA websocket ของ TradeMan หลุด (เน็ตสะดุด/พักจอ) → front-end ขึ้น dialog ขอให้ user กด "Reconnect" เพื่อฟื้น socket **โดยไม่ reload ทั้งหน้า** (เซสชัน/คุกกี้ยังดี)
  2. **DOM & UI Reality:** `FAST_DISMISS_SELECTORS` ของ `popup_manager` มีแต่ปุ่ม ปิด/X/`รับทราบ` (Tier 1) และ scrim — **ไม่มี selector ของปุ่ม "Reconnect"** เลย → Tier 1 ไม่แมตช์; ปุ่ม Escape ก็ไม่ปิด (ไม่ใช่ dismissible dialog); ดีไซน์นี้ไม่มีปุ่ม X → `dismiss_popups()` คืน False
  3. **Data Schema & Types:** logic ฟื้นเซสชันที่ถูกต้องมีอยู่แล้วใน runbook `learned_workflows/krungsri/trademan_session_reconnect.md` แต่ **ไม่ได้ wire เข้า runtime `popup_manager`** → องค์ความรู้มีแต่ไม่ถูกใช้ (docs↔code drift)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - Connection-Lost dialog **ไม่มีปุ่มปิด/X** — ต้องกด "Reconnect" เท่านั้น (เอา X/Escape มากดจะไม่มีอะไรเกิดขึ้น)
  - ต้อง **รอ 3000ms** หลังคลิก ให้ SPA ฟื้น websocket + re-render ก่อนอ่าน DOM ต่อ
  - overlay เป็นชนิด `.v-overlay` (ไม่ใช่ `.v-dialog`) → `is_overlay_present()` ต้องจับ `.v-overlay--active` (มีอยู่แล้ว)
  - ต้อง **ไม่พึ่ง Gemini Vision** เด็ดขาด (provider ล่ม/โดน rate-limit เป็นปกติ) → handler ต้องเป็น pure selector
  - ปุ่ม "Reconnect" โผล่เฉพาะในดีไซน์ Connection-Lost เท่านั้น → ปลอดภัยเมื่อรันเป็น Tier 0 ก่อน flip อื่น
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  1. เพิ่ม `PopupManager.RECONNECT_SELECTORS` (specific → ทั่วไป):
     `button:has-text('Reconnect')`, `button:has-text('เชื่อมต่อใหม่')`, `button:has-text('ลองใหม่')`, `button:has-text('ลองอีกครั้ง')`, `button:has-text('Try again')`, `button:has-text('Retry')`
  2. เพิ่มเมธอด `PopupManager._reconnect_if_connection_lost(page)` → query selector ทีละตัว ถ้าพบและ visible → `click(timeout=5000, force=True)` + `wait_for_timeout(3000)` → คืน True
  3. Wire เป็น **Tier 0** ใน `dismiss_popups()` (ก่อน Tier 0.5 dont-show-again และ Tier 1) → ถ้าฟื้นสำเร็จ log `POPUP_DISMISSED / Tier 0 Reconnect (Connection Lost)` แล้ว `continue`
  4. Regression tests: `tests/test_popup_manager.py::test_reconnect_if_connection_lost_clicks_reconnect` (พบ → คลิก 1 ครั้ง/คืน True) และ `::test_reconnect_if_connection_lost_no_dialog_is_noop` (ไม่พบ → no-op/คืน False)
  5. **หลักฐานสด (2026-10-07):** หลังปิด Connection-Lost dialog แล้ว MCP `switch_account` กลับมาทำงาน 100% — Krungsri CASH 3024952 (0 holdings) ≠ MARGIN 3024959 (15 holdings); restore CASH สำเร็จ; Liberator CASH <liberator-acct> สำเร็จ
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้สั่งให้ทำ **ถาวรแบบไม่พึ่ง Gemini** ("Gemini-free") — Vision ใช้เป็นทางเลือกสุดท้ายเท่านั้น
  - ทำหลักฐานจริง (Track A) ก่อน แล้วค่อยลงโค้ดแก้ถาวร (Track B) เพราะ uvicorn ไม่มี `--reload` → โค้ดใหม่ต้อง restart กว่าจะมีผล
  - ต้อง restore Krungsri กลับเป็น **CASH** เสมอหลังสลับไป MARGIN
  - ต้องบันทึกลง RCA ของโบรกเกอร์นั้น + อัปเดต runbook เดิมให้ตรงกัน (Zero-Contradiction)

---

### 📌 Incident `KSS-RCA-013`: Zero-OTP Session Wiped by a Transient Navigation Timeout
* **วันและเวลา:** 2026-10-07 ~20:44–20:52 น. (ICT)
* **อาการ (Symptom):**
  หลัง login Krungsri สำเร็จแบบสด (OTP `807258` ผ่าน browser DOM → SSO → `trademan.in.th/Portfolio`;
  เขียน `data/session_state.json` เรียบร้อย) การรัน diagnostic เพื่ออ่าน DOM ของแท็บ "View Order"
  เกิด `Page.goto: Timeout 12000ms exceeded` ใน `verify_saved_session()` → **ไฟล์ `data/session_state.json`
  ที่ยังใช้ได้ถูกลบทิ้งทันที** → ต้อง login ใหม่ (เผา SMS OTP + เสี่ยง account lock)
* **การสืบหาต้นตอ (Root Cause Analysis — 3 จุด):**
  1. **Session & Context Isolation:** ไฟล์ Zero-OTP ถูกทำลายโดย path ที่ไม่ควรแตะ — `Page.goto` timeout เป็นเหตุการณ์
     **ชั่วคราว** (เครือข่าย/SPA hydration ช้า) ไม่ได้แปลว่าเซสชันหมดอายุ
  2. **DOM & UI Reality:** `verify_saved_session()` มี `os.remove(settings.SESSION_STATE_PATH)` **2 จุด** —
     (ก) ใน `except Exception` (timeout/exception ชั่วคราว) และ (ข) ใน `else` (หา `#dropDownAccountPort` ไม่เจอ)
     ทั้งสองจุดลบไฟล์โดยไม่มีหลักฐานยืนยันว่าเซสชันหมดอายุจริง
  3. **Data Schema & Types:** เทียบ Liberator ที่ `verify_saved_session()` แค่ `return False` (ไม่ลบไฟล์)
     → Krungsri เป็น outlier ที่ทำลาย state (ขัด Invariant 8)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - `Page.goto` timeout / DNS ช้า / Nuxt hydrate ช้า → **ห้ามตีความเป็น "หมดอายุ"**
  - `wait_for_selector("#dropDownAccountPort", timeout=6000)` สั้นเกิน → false-negative ได้
  - cold-start headless browser มีโอกาส timeout สูงกว่าปกติ
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  ใน [app/browser/auth_driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/auth_driver.py):
  1. **except branch (transient):** ลบ `os.remove()` ออกทั้งหมด — ปล่อยไฟล์ไว้ 100%, `status="DISCONNECTED"`, `return False`
  2. **else branch (validation miss):** เปลี่ยน `os.remove()` → `self._quarantine_session_file()` ที่ **rename**
     เป็น `<SESSION_STATE_PATH>.stale.bak.json` (non-destructive, mirror Liberator `*.stale.bak.json`)
  3. ไม่ `clear_cookies()` ทำลาย context ในเส้นทาง verify (การ purge จริงทำเฉพาะเมื่อ `force_fresh`)
  4. Regression tests: `tests/test_auth_session_nondestructive.py` (3 tests)
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้เลือก **"ยังไม่ยิง OTP"** — ให้แก้ bug + อัปเดตเอกสารก่อน (ลดความเสี่ยง OTP ซ้ำซ้อน)
  - หลักการยืนยัน: **Invariant 8 — ห้ามลบ `session_state.json` เมื่อเจอ DOM Exception/Timeout ชั่วคราว**

---

---

### 📌 Incident `KSS-RCA-014`: Order Ledger Column Mis-Mapping (`symbol=UNKNOWN`, `status=<time>`)
* **วันและเวลา:** 2026-10-07 (ช่วง U6 live E2E ของ `TASK-pillar2-order-ledger`)
* **อาการ (Symptom):** `current_orders(platform="KRUNGSRI")` บนแท็บ 'View Order' คืนค่าผิด — `symbol` = `UNKNOWN` ทุกแถว, `status_raw` เป็น **เวลา** (เช่น `16:29:55`), `broker_order_no` เป็น fallback `ORD-x`
* **การสืบหาต้นตอ (Root Cause Analysis):**
  1. **DOM & UI Reality:** `scrape_all_orders()` (และ `scrape_unmatched_orders()`) ใช้ `page.query_selector_all("table tbody tr")` **กว้างเกินไป** → กวาดตาราง **Watchlist / กองทุน** (คนละ container `div.drag-container`) เข้ามาด้วย แล้ว index คอลัมน์เพี้ยน
  2. **แท็บจริง:** ปุ่ม 'View Order' คือ element เฉพาะตัว **`div#order_btn`** — โค้ดเดิมใช้ `div:has-text('View Order')` ซึ่งแมตช์ ancestor/navbar ได้ (คลิกกำกวม)
  3. **โครงสร้างแท็บ:** แท็บนี้เรนเดอร์ **2 `<table>` พี่น้อง** ใน section เดียวกัน (`div.relative.bg-[#1F2025]`): **header** = `div.pr-[20px] > table.w-full.h-[2.5rem]` (thead: `Order No.|Side|Symbol|Volume|Price|Matched|Status|Time|Quote`) และ **body** = `div.overflow-y-auto.scrollbar-container > table.w-full.relative` (10 `td`/แถว)
* **Edge Cases ที่พบ:**
  * **Status เป็นคำเต็ม** (`Matched` / `Canceled` / `Reject`) — **ไม่ใช่** ตัวอักษร `M/O/C` (ที่ runbook เก่าเข้าใจผิด)
  * **Time แยกคอลัมน์ของตัวเอง** (คอลัมน์ 8) ไม่ได้ต่อท้าย status
  * **Side เป็นรหัสตัวอักษรเดียว** `H`/`C` (สี `#D964D7`/`#478BCC`) — ไม่ใช่คำ `BUY/SELL/SHORT/COVER`
  * โมดอล 'Order Detail' (คลิก `#order_detail_btn`) เรนเดอร์เป็น `.v-overlay--active` — **ไม่ใช่** `[role="dialog"]`/`.modal`
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  * **Deterministic Table Header Isolation** ผ่าน JS (`TradeManDriver._VIEW_ORDER_ROWS_JS`): หา `table` ที่ `thead th` มี `Order No.`+`Status`+`Symbol` → ไต่ขึ้นหา section ที่มี `div.overflow-y-auto.scrollbar-container` → อ่าน `table` ในนั้น
  * `switch_tab("order_status")` → selector = **`div#order_btn`** เท่านั้น
  * Side code map (ยืนยันจาก bundle ของแอปเอง): `TRADEMAN_SIDE_CODE_MAP = {"B":"BUY","S":"SELL","H":"SHORT","C":"COVER"}` (`Ga3w9f6D.js`/`XNfJS877.js`: `side==="Short"`→`#D964D7`, `side==="Cover"`→`#478BCC`)
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):** ผู้ใช้ยืนยัน semantics `H=Short, C=Cover` บนบัญชี MARGIN `3024959` → **ห้ามเดา** side codes ของโบรกเกอร์ (Broker Knowledge Isolation); bug นี้คลาสเดียวกับ Liberator (`LIB-RCA`, table-header isolation)
* **อ้างอิง:** [`learned_workflows/krungsri/trademan_order_submit.md`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/krungsri/trademan_order_submit.md) §5 · [`learned_workflows/krungsri/trademan_view_order.md`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/krungsri/trademan_view_order.md) · [`tests/test_trademan_view_order_scraper.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_trademan_view_order_scraper.py)

### 📌 Incident `KSS-RCA-015`: Full-suite ลบ Zero-OTP Session สดทิ้ง (Logout-Endpoint Vector)

**Incident ID & Date**: KSS-RCA-015 (2026-10-08 ~21:08 +07 — ตรวจพบตอนปิดงาน D2 ของ handoff `TASK-otp-channel-authoritative.md`)
**Status**: 🟡 **OPEN** — บันทึกตามจริง ยัง**ไม่แก้** (ไฟล์เทสต์นอก scope ของ handoff นั้น)
**พิสูจน์ซ้ำ (Recurrence — 2026-10-09 ~15:39 +07)**: 🔴 ระหว่างปิดงาน handoff `TASK-krungsri-cancel-amend-uptick.md`
รัน `scripts/verify_changes.py --full` → **`362 passed in 204.97s` (ผ่านเต็ม ไม่ถูก kill)** แต่หลังจบการรัน
`data/session_state.json` **หายไปจริง** ⇒ ยืนยันว่า **ตัวเทสต์เองเป็นผู้ลบ** ไม่เกี่ยวกับการ kill ค้าง (ตัดสมมติฐานทิ้ง)
รอบนั้นรอดเพราะสำรอง `data/session_state.json.manual.bak` ก่อนรัน → กู้คืนแล้ว md5 `619dee547e9f0037bf84e17b1f77dddd` ตรงกัน (56 cookies / 3 origins)

**Symptom**:
- D2 live verification ทำให้ได้ session Krungsri สดใหม่: `data/session_state.json` (60 cookies, mtime `21:01:09`) → `LOGIN_SUCCESS` (row #1484)
- ต่อมาเมื่อรัน **full suite** ปิดงาน (`pytest tests/ -q`) พบว่า **ไฟล์ `data/session_state.json` หายไป** (mtime ของโฟลเดอร์ `data/` = `21:08`)
- ตรวจซ้ำ: `ls data/session_state.json` → `No such file or directory` · `find . -name '*session_state*'` → **ไม่พบเลยแม้แต่ backup**
  (ขณะที่ `data/liberator_session.json` ยังอยู่ — เพราะไม่มีอะไรไปลบ)
- ผลกระทบจริง: **ต้อง login Krungsri ใหม่ + เผา SMS OTP อีกรอบ** (เสี่ยง account lock) — ตรงกับสิ่งที่ Invariant 8 ห้ามไว้
- ⚠️ บริบทสำคัญ: full suite **ค้าง** ที่ ~82–87% (known SQLite issue) แล้วถูก `kill -9` → เป็นไปได้ว่า teardown ไม่ได้รัน
  **แต่การลบไฟล์เกิดจากตัวเทสต์เอง ไม่ใช่จากการ kill** (ดู RCA ด้านล่าง)

**Root Cause Analysis (RCA)**:
1. **จุดลบไฟล์จริง**: `app/api/v1/endpoints/session.py:101–103` — `logout_session()` เรียก
   `os.remove(settings.SESSION_STATE_PATH)` (พฤติกรรมที่ถูกต้องใน production: ผู้ใช้สั่ง logout ก็ควรลบ)
2. **ตัวกระตุ้น**: `tests/test_browser_driver.py` → `test_session_logout_endpoint()` (สร้าง `AsyncClient(transport=ASGITransport(app=app))`
   แล้ว `await client.post("/api/v1/session/logout")`) — ยิงเข้า **app จริง** และใช้ **`settings` จริง**
3. **ช่องว่างที่ทำให้อันตราย**: ไฟล์เทสต์นั้น**ไม่มี fixture/test-mode ที่ monkeypatch `settings.SESSION_STATE_PATH` ไป `tmp_path`**
   (เทสต์อื่นในไฟล์เดียวกันก็ไม่ เช่น `test_session_status_endpoint` แค่อ่าน) → เทสต์จึงลบ **ไฟล์ของผู้ใช้จริง**
   ⇒ **เทสต์ไม่ isolate = side effect หลุดสู่ production state**
4. **ทำไม guard เดิมไม่จับ**: `tests/test_auth_session_nondestructive.py` (สร้างจาก KSS-RCA-013) คุม
   `verify_saved_session()` **เท่านั้น** — เป็น guard ระดับ "ฟังก์ชัน" ไม่ใช่ระดับ "ทั้งระบบ"
   ⇒ คลาสของบั๊ก (destructive session handling) ยังมี **เส้นทางที่ 2** ที่ไม่มีใครคุม
5. **ทำไมเพิ่งเจอ**: เส้นทางนี้จะทำอันตรายก็ต่อเมื่อ **มี session สดจริงอยู่ก่อน** รัน full suite —
   ซึ่งเพิ่งเกิดขึ้นในงานวันนี้ (ปกติ full suite รันตอน session หมดอายุอยู่แล้ว จึงดู "ไม่เป็นไร")

**Edge Cases ที่พบ**:
- **`kill -9` กลางเทสต์ = teardown หาย**: แม้การลบจะไม่ได้มาจากการ kill แต่การ kill ทำให้ไม่มีโอกาส restore
  (และงานนี้พิสูจน์แล้วว่า full suite ค้างจริง → kill เป็นเรื่องปกติที่ต้องทำ)
- **ไม่มี git, ไม่มี backup**: `data/session_state.json` ไม่ถูก track (repo ไม่มี `.git`) และไม่มีกลไกสำรอง
  → ลบแล้วกู้ไม่ได้ ต้องพึ่ง OTP ใหม่เท่านั้น
- **`session_file_info()` มองไม่เห็น "ถูกลบ" ทันที** ถ้ามีคนรัน `--no-login` (report-only) → จะรายงาน `MISSING`
  แต่ไม่มีคำอธิบายว่า "ใครลบ" (ควรมี audit row สำหรับการลบไฟล์ session)
- ลำดับการรันเทสต์มีผล: ถ้า logout test รัน **หลัง** เทสต์ที่ login/save session → จะลบไฟล์ที่เทสต์เพิ่งสร้าง

**Proven Working Solution (ข้อเสนอ — ยังไม่นำไปใช้ เพราะนอก scope)**:
```python
# tests/test_browser_driver.py — เพิ่ม isolation ให้เทสต์ที่แตะ session endpoint
@pytest.fixture(autouse=True)
def _isolate_session_path(monkeypatch, tmp_path):
    """KSS-RCA-015: ห้ามเทสต์แตะ session file จริงของผู้ใช้"""
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(tmp_path / "session_state.json"))
```
ตรวจแบบ targeted (ไม่สะสม state) แทนการรัน full suite:
```bash
.venv/bin/python -m pytest tests/test_browser_driver.py -q          # ต้องยังผ่าน
ls -l data/session_state.json                                       # ต้อง "ยังอยู่" หลังรัน (regression guard)
```
และก่อนรัน full suite ควรสำรอง: `cp data/session_state.json data/session_state.json.manual.bak`

**User Feedback & Context**:
- หลักการที่ต้องยึด: **เทสต์ต้องไม่ทำลาย state ของ production** — `pytest` ต้องรันซ้ำได้โดยไม่เปลี่ยนพฤติกรรมระบบจริง
- บทเรียน: การปิดบั๊กเป็น *เส้นทาง* (function-level) ไม่เท่ากับปิด *คลาส* ของบั๊ก — KSS-RCA-013 แก้แล้ว
  แต่คลาส "มีโค้ดที่ลบ session file" ยังเหลืออีกจุด (`session.py`) ที่ต้องมี guard ระดับระบบ
- ผลต่อแผนงาน: session ที่ได้จาก D2 (21:01) **ใช้ไม่ได้แล้ว** — การทดสอบ pillar ถัดไปต้องทำ login ใหม่
  (ผู้ใช้ต้องพิมพ์ OTP อีกครั้ง) จึงต้องแจ้งล่วงหน้า ไม่ใช่ให้เจอตอนรัน (Anti-Mock / truthful reporting)

---

### 📌 Incident `KSS-RCA-016`: Fabricated Order IDs & Absence of a Native "Change" Button

**Incident ID & Date**: KSS-RCA-016 (2026-10-09)
**Status**: 🟢 RESOLVED

**Symptom**:
- `trademan_driver.execute_order()` คืน `broker_order_no` ปลอมรูป `ORD-<epoch>` (เช่น `ORD-1759999999`) ไม่ตรงกับเลขจริงบน ledger ของ TradeMan
- โค้ด/รันบุ๊กเดิมสมมติว่ามีปุ่ม **"Change"** ในแถวคำสั่งที่ยังไม่ match → amend ต่อราคาที่ implement ไว้จึงไม่มีปุ่มให้กด (หรือกดผิดปุ่ม)

**Root Cause Analysis (RCA)**:
1. **ไม่มีปุ่ม Change จริง**: พิสูจน์สด 2026-10-09 (`data/krungsri_order_actions_dump.json`, `data/krungsri_cancel_confirm.html`) — แถวคำสั่งมีเฉพาะ action cell ที่กดยกเลิกได้ → **amend ต้องทำเป็น Cancel + Re-submit** (ไม่มีทางแก้ราคา in-place)
2. **Order ID สังเคราะห์เอง**: driver เดิมสร้าง id ขึ้นมาเองเพื่อให้ caller มีค่าตอบกลับ แทนที่จะอ่าน `Order No.` จริงจากตาราง View Order → ผิด Anti-Mock Guardrail (Invariant 1) และทำให้ cancel/amend ภายหลังอ้าง id ที่ไม่มีอยู่จริงไม่ได้

**Edge Cases ที่พบ**:
- แถวสถานะ terminal (`CANCELLED` / `REJECTED`) ต้อง amend ไม่ได้ → คืน `NOT_OPEN`
- Amend บนคำสั่งที่ **partial fill** ต้อง re-submit เฉพาะ **remaining volume**
- ป๊อปอัปยืนยันการยกเลิกเด้งซ้อน → ต้อง dismiss ให้ครบก่อนดำเนินการต่อ
- PIN modal (`input#pin`) ต้องกรอกทุกครั้งที่ยืนยัน (Broker PIN Isolation — KSS-RCA-007)
- Cancel สำเร็จแต่ Re-submit ล้มเหลว → ต้องรายงาน `CANCEL_FAILED` / partial state ให้ชัด ห้ามรายงานสำเร็จลวง

**Proven Working Solution**:
- `cancel_order()` ใช้ row-scoped selector ยึดบน `Order No.` (`_CANCEL_ROW_CLICK_JS`) แล้วปิด modal ยืนยันด้วย `_dismiss_cancel_modal()` + กรอก PIN
- `modify_order_price()` = `cancel_order()` → `execute_order()` (ด้วยราคาใหม่) แล้ว **อ่านเลขจริงกลับ** ด้วย `_scrape_new_order_no()` จาก View Order ledger
- ลบการสร้าง `ORD-<epoch>` ออกทั้งหมด → คืน `order_id` จริงที่ read-back มาได้
- Plugin ฝั่ง Krungsri (`app/brokers/krungsri/plugin.py`) ต่อสาย `cancel_order(order_id, symbol, pin, ...)` และ `modify_order_price(order_id, new_price, symbol, side, remaining_volume, pin, account_no, ...)`

**User Feedback & Context**:
- ต้องใช้ **เลขคำสั่งจริงเท่านั้น** ห้ามแสดง/คืนค่าที่แต่งขึ้น (Anti-Mock)
- การยืนยันต้องผ่าน PIN เสมอ (Human-in-the-Loop)

---

### 📌 Incident `KSS-RCA-017`: SET Short Uptick เป็น Strict + SHORT Negotiation ไม่ปั้น `last`

**Incident ID & Date**: KSS-RCA-017 (2026-10-09)
**Status**: 🟢 RESOLVED

**Symptom**:
- `validate_short_uptick(price=last, last_trade_price=last)` คืน **ผ่าน** (นับเป็น "zero-plus tick") → ระบบยอมเสนอคำสั่ง SHORT ที่ราคา **เท่ากับ** ราคาซื้อขายล่าสุด ซึ่งตลาด/โบรกเกอร์จะ reject
- Price Negotiation เสนอราคา SHORT โดยใช้ `last` ที่ **ปั้นขึ้นเอง** จาก Bid1/Offer1/ราคาคำสั่งเดิม เมื่อดึงราคาตลาดจริงไม่ได้

**Root Cause Analysis (RCA)**:
1. **SSOT หลวม**: `app/services/validator.py::validate_short_uptick` ใช้เงื่อนไข `price < last_trade_price` → ราคาเท่า last ถือว่าผ่าน
2. **การตีความสองแบบขัดกัน**: `trademan_driver.modify_order_price` เคย gate ด้วย `get_next_tick(last, 1)` (strict) ขณะที่ validator ใช้ `>=` → เกิด Zero-Contradiction (แก้โดยให้ driver delegate ไปที่ validator SSOT)
3. **Anti-Mock violation**: `price_negotiation_service.evaluate_order_negotiation` มี `last = quote.get("last") or bid_1 or offer_1 or current_order_price` → เมื่อ API จริง (TradeMan) ไม่ส่ง depth/`last` ก็ยัดราคาคำสั่งตัวเองเป็น `last` → กฎ uptick ถูกปิดแบบเงียบ

**Edge Cases ที่พบ**:
- **TradeMan quote API ไม่มี depth**: `loadstockinformation` คืน `lastSalePrice` แต่ **ไม่มี** bid/offer → `bid_1`/`offer_1` เป็น `None` เสมอบน TradeMan (มี depth เฉพาะฝั่ง Click2Win)
- **คำสั่ง SHORT ตั้งไว้ที่ best offer หรือ +1 tick อยู่แล้ว** → ห้ามต่อราคา (รอราคาขยับเอง) ตามที่ผู้ใช้ยืนยัน
- **`last` อ่านไม่ได้** → ต้อง fail-closed ไม่เสนออะไรเลย (ห้าม backfill)
- tick bracket: `last + 1 tick` ต้องคำนวณตามช่วงราคา (เช่น 8.20 → 8.25 ที่ tick 0.05)

**Proven Working Solution**:
- `validator.validate_short_uptick` → `if price <= last_trade_price:` reject; ข้อความ error ระบุ **minimum = `get_next_tick(last, 1)`** (strict, ไม่มี zero-plus tick)
- `trademan_driver.modify_order_price` → `minimum_price = validator.get_next_tick(last_trade_price, steps=1)` ใน reject payload; comment อัปเดตเป็น "strictly above, ไม่มี zero-plus tick"
- `price_negotiation_service.evaluate_order_negotiation` (SHORT):
  - `last = quote.get("last")` เท่านั้น (ไม่มี backfill)
  - `last` ว่าง → คืน `needs_adjustment=False, needs_review=True` (fail-closed)
  - `offer_1` มีค่า และ `current_order_price <= offer_1 + 1 tick` → **no-op** (รอราคาขยับ)
  - ไม่เข้าเงื่อนไขข้างบน → `floor = get_next_tick(last, 1)`, `target = max(offer_1, floor)`, แล้ว re-validate ด้วย SSOT อีกชั้น
- Runbook `krungsri_market_open_operational_runbook.md` §C แก้จาก "`>= Last`" → "**strictly > Last** (min Last + 1 tick)"
- เทสต์: `tests/test_validator.py::test_short_uptick_rule` (equality → False) + `tests/test_trade_negotiation.py` (fail-closed / strict floor / no-op ที่ offer / no-op ที่ offer+1 tick / re-price เมื่อห่างเกิน)

**User Feedback & Context**:
- ผู้ใช้แก้ข้อมูลกลางทางว่า: *"ถ้า Order ราคาที่ตั้งมัน price = best offer แล้ว หรือ มากกว่า 1 ช่อง อันนี้ถือว่า ok แล้วครับ ต่อราคา Short ไม่ได้แล้ว ต้องรอราคาขยับขึ้นเอง"* → เงื่อนไข skip จึงผูกกับ **ราคาคำสั่ง vs best offer** ไม่ใช่ `last` vs best offer

---

### 📌 Incident `KSS-RCA-018`: Amend LIVE ยกเลิกคำสั่งจริงแล้ว Re-submit ตกกลับเข้า DRY_RUN (Guard ไม่สมมาตร) → Position หาย

**Incident ID & Date**: KSS-RCA-018 (2026-10-09 — ตรวจพบตอนเตรียม Live E2E Gate 4 ของ handoff `TASK-krungsri-cancel-amend-uptick.md`)
**Status**: 🟢 RESOLVED (ซอร์ส + เทสต์) · 🟡 **LIVE round-trip ยังไม่ถูกพิสูจน์ครบ** (รอบทดลองจริง 2026-10-09 ถูก REJECT ที่ uptick guard *ก่อน* ถึงขั้น cancel — ดู Edge Cases)

**Symptom**:
- รัน amend ในโหมด LIVE จริง (`bypass_dry_run=True`) → (1) ขั้น `cancel_order` **ยกเลิกคำสั่งจริงบนโบรกเกอร์สำเร็จ** (เผา PIN) แต่ (2) ขั้น re-submit **ตกลงในเส้นทาง DRY_RUN** → ไม่มีคำสั่งใหม่ถูกส่ง → **position (SHORT) หายจากพอร์ตถาวร**
- caller ได้ `success=True` + `status="AMENDED"` + `broker_order_no` รูป **`SIM-<epoch>`** → ทุกระบบรายงานว่าสำเร็จ ยกเว้นตำแหน่งที่หายไป

**Root Cause Analysis (RCA)**:
1. **Guard ไม่สมมาตร (asymmetric)**: `cancel_order()` L1238 และ `modify_order_price()` L1412 gate ด้วย `settings.DRY_RUN_MODE and not bypass_dry_run` แต่ `execute_order()` gate **สองจุด** (L624 "no browser page" และ L748 "ก่อนคลิก Send") ด้วย `settings.DRY_RUN_MODE` เดี่ยว ๆ ⇒ เมื่อ `bypass_dry_run=True`: **cancel จริง แต่ submit จำลอง**
2. **Flag ถูกกลืนเงียบ (silent no-op)**: `execute_order()` **ไม่มีพารามิเตอร์ `bypass_dry_run`** แต่มี `**kwargs` → ค่าที่ส่งเข้ามาถูกดูดเข้า `**kwargs` โดยไม่เกิด `TypeError` และไม่มีผลใด ๆ = บั๊กชนิดที่อันตรายที่สุด (เงียบ ไม่มี error)
3. **Amend ไม่ atomic / ไม่มี compensation**: `modify_order_price` เรียง `cancel_order` → `execute_order` ⇒ ถ้าขั้นหลัง cancel ล้ม (หรือถูก simulate) **ไม่มี rollback** (re-submit ที่ราคาเดิม) ⇒ position สูญหาย
4. **Anti-Mock ซ้ำรอย KSS-RCA-016**: การคืน `SIM-<epoch>` ทำให้ caller แยกไม่ออกว่าคำสั่งจริงถูกส่งหรือไม่ (Invariant 1)

**Edge Cases ที่พบ**:
- 🛡️ **Fail-safe ที่มีอยู่จริง (พิสูจน์สด)**: ด่าน uptick/`validate_all` ถูกเรียก **ก่อน** `cancel_order` ⇒ guardrail reject ทิ้งคำสั่งเดิมไว้ครบ
  หลักฐาน 2026-10-09: amend BCPG ฿6.50 → **REJECTED ที่ uptick**, forensics ไม่พบ `cancel_order`/re-submit, `Order No. 11014378` ยังอยู่ที่เดิม
- ⚠️ **Residual risk (ยังไม่ปิด)**: `execute_order` เรียก `validate_all` **ซ้ำอีกครั้งหลัง cancel** (L616) ⇒ ถ้าตกที่ด่านนั้น (สาเหตุอื่นที่ไม่ใช่ uptick) จะเสีย position เพราะไม่มี compensation — บันทึกเป็น open item
- `current_price` ใน `modify_order_price` = `row["price"]` = **ราคา limit ของคำสั่ง** ไม่ใช่ราคาตลาด (ห้ามสับสน)
- **โหมด TEST กันไม่ได้**: `phase3.execute_direct_price_modification` hard-code `force_live=True` ⇒ ส่ง `bypass_dry_run=true` เข้า `execute-direct` ยิง LIVE ทันทีแม้ `TRADING_MODE=TEST`

**Proven Working Solution**:
- `execute_order(..., bypass_dry_run: bool = False)` — เพิ่มพารามิเตอร์จริง (L575) ไม่พึ่ง `**kwargs`
- Gate ทั้งสองจุดใน `execute_order` เปลี่ยนเป็น `if settings.DRY_RUN_MODE and not bypass_dry_run:` (L624, L748) → **Symmetric Guards**
- `modify_order_price` ส่ง `bypass_dry_run` ต่อให้ **ทั้งสอง** ขั้น: `cancel_order` (L1510) และ `execute_order` (L1524)
- เทสต์กันถอยหลัง: `tests/test_trademan_amend_bypass_dryrun.py` (2 tests) + map ใน `scripts/verify_changes.py` (`MODULE_TEST_MAP`)
- หลักฐาน: `.venv/bin/python scripts/verify_changes.py app/browser/trademan_driver.py` → **PASS (exit 0)** · `29 passed` · `compileall: OK`

**User Feedback & Context**:
- ผู้ใช้ยืนยันว่าราคาที่ขยับ (BCPG → ฿6.55, VGI → ฿0.95) เป็นการ **แก้ด้วยมือ** ของผู้ใช้เอง ไม่ใช่ผลจากระบบ
- ก่อนยิง amend ทุกครั้งต้องมี **คำสั่งชัดเจนในแชทของ task นั้น + human confirm** (Trading safety) และต้องเป็นโหมด LIVE เท่านั้นจึงจะใช้ `bypass_dry_run=True`

---

## 🔒 กฎเหล็กประจำตัว Krungsri (Strict Constraints & Guardrails)
1. **บัญชี Cash (`3024952`) vs Margin (`3024959`)**:
   - บัญชี Cash ใช้สำหรับการซื้อหุ้นด้วยเงินสดสด (Line Available)
   - บัญชี Margin ใช้สำหรับกลยุทธ์ SBL Short และวงเงินกู้ (Excess Equity)
   - ก่อนส่งคำสั่งทุกครั้ง ต้องสลับบัญชีผ่าน `#dropDownAccountPort` และตรวจสอบข้อความในปุ่มให้ตรงกับเลขบัญชีเสมอ
2. **ป๊อปอัป "มีอะไรใหม่"**:
   - ต้องกวาดปิดแบบ Multi-Overlay ทุกครั้งหลังเข้าสู่ `trademan.in.th`
3. **การเก็บรักษาเซสชัน**:
   - ต้องเซฟ Storage State ลง `data/session_state.json` ทุกครั้งที่มีการล็อกอินใหม่สำเร็จ
4. **Action Exit Pricing & Window Rule (Pillar 6)**:
   - ห้ามส่งคำสั่งเคาะขวา/โยนซ้ายกิน Spread ทันที ต้องวางคิว Passive ที่ Offer 1 (สำหรับ Sell) หรือ Bid 1 (สำหรับ Cover)
   - ไม้กำไรส่งช่วง 10:00 - 10:30, ไม้ขาดทุนส่งช่วง 10:30 - 12:00 เสมอ
   - เฝ้าระวังส่วนต่างราคาเกิน 2-3 Ticks หรือ ±1.5% หากหลุดเกณฑ์ต้องสั่ง Halt แล้วแจ้งเตือนผู้ใช้ทันที
5. **Anti-DW Strict Common Stock Guardrail (KSS-RCA-006)**:
   - ห้ามใช้ Prefix หรือ Loose Regex ในการเลือกหุ้นเข้าแผงส่งคำสั่งเด็ดขาด
   - คำสั่งปิดไม้ในพอร์ต ต้องเลือกผ่านการคลิกตาราง `td:text-is('{symbol}')` หรือใช้ Exact Match เท่านั้น
   - ต้องตรวจสอบค่า `On Hand` ก่อนส่งคำสั่งฝั่ง SELL เสมอ ห้ามขาย DW โดยไม่ตั้งใจ
6. **Isolated Broker PIN Rule (KSS-RCA-007)**:
   - ต้องใช้ `KRUNGSRI_PIN` จาก `.env` เสมอ ห้ามใช้ PIN ของโบรกเกอร์อื่นปนกัน
7. **09:45 Pre-Flight Sentinel Rule (KSS-RCA-009)**:
   - ต้องตรวจสอบสถานะเซสชันเวลา 09:45 น. และแจ้งเตือนมือถือล่วงหน้าก่อนตลาดเปิด
8. **Automated Regression Verification**:
   - ทุกการเปลี่ยนแปลงของ Krungsri Module ต้องผ่านการรัน [`tests/test_krungsri_pdca_guardrails.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_krungsri_pdca_guardrails.py) (100% Pass) ก่อนนำขึ้น Production เสมอ
   - อ่านสรุปบทเรียนและระเบียบปฏิบัติฉบับเต็มได้ที่ [`app/brokers/krungsri/PDCA_RETROSPECTIVE.md`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/krungsri/PDCA_RETROSPECTIVE.md)
9. **SMS OTP Arrival-Time Rule (KSS-RCA-010 / `KDE-RCA-005`)**:
   - Gate 6 ต้องเรียก `poll_active_notifications(expected_ref=self.current_ref, since_ms=int(wait_start_time.timestamp()*1000))` เท่านั้น
   - **ห้ามขยาย `OTP_TIMEOUT_SECONDS`** เพื่อกลบปัญหา SMS มาช้า (SMS หมดอายุ ~5 นาที; relay อาจใช้ ~7m39s) — ต้องลด latency
   - ยึดหลัก **Ref Code ที่ตรง = definitive** และรับ payload ที่มาถึงช้าได้ แม้ phone-clock จะแก่กว่า grace window
   - ห้ามปะปนตรรกะ SMS-channel เข้ากับ logic ธีมเทรดของ Krungsri (Broker Knowledge Isolation)
10. **Session-Drop Detection Rule (KSS-RCA-011)**:
   - ทุก component (MCP / preflight / sentinel) ต้องตัดสินสถานะไฟล์ session จาก
     `app.brokers.krungsri.session_health.session_file_info()` **ตัวเดียวเท่านั้น** (ห้ามใช้ `os.path.exists()` เดี่ยว ๆ)
   - ห้ามรายงาน ✅ สำหรับ session ที่ตรวจ offline ไม่ได้ — ให้ใช้ ℹ️ (recent) / ⚠️ (missing, EXPIRED)
   - SessionSentinel ต้องตรวจ session-file ทุก tick โดยไม่ผูกกับ live tab หรือ trading hours
   - Pre-market warning window = **Weekday 09:45–09:55 BKK** (สอดคล้อง `KSS-RCA-009`) และยิงซ้ำไม่เกิน 1 ครั้ง/วัน



11. **Deterministic Order-Ledger Isolation Rule (KSS-RCA-014)**:
   - ห้ามใช้ `query_selector_all("table tbody tr")` บน TradeMan เด็ดขาด — ต้อง anchor บน `thead th` (`Order No.`/`Status`/`Symbol`) แล้วอ่าน sibling body table (`_VIEW_ORDER_ROWS_JS`)
   - ปุ่ม 'View Order' ต้องคลิกด้วย `div#order_btn` (ไม่ใช่ `div:has-text('View Order')`)
   - Side codes: `B`=BUY `S`=SELL `H`=SHORT `C`=COVER (`TRADEMAN_SIDE_CODE_MAP`); status เป็นคำเต็ม ไม่ใช่ `M/O/C`

12. **Test-Suite Session-Safety Rule (KSS-RCA-015 — 🟡 OPEN)**:
   - **ห้ามมีเทสต์ใดยิง endpoint ที่ลบ/แตะ `settings.SESSION_STATE_PATH`** (เช่น `POST /api/v1/session/logout`)
     โดยไม่ monkeypatch path ไป `tmp_path` ก่อน — การรัน full suite จะ **ลบ session สดของผู้ใช้จริง**
   - ก่อนรัน `pytest tests/` ให้ถือว่า session สดอาจถูกทำลาย → **สำรองก่อนเสมอ**
     (`cp data/session_state.json data/session_state.json.manual.bak`) หรือใช้ targeted mode
     (`scripts/verify_changes.py`) ระหว่างทำงาน
   - Guard ระดับฟังก์ชัน (`test_auth_session_nondestructive.py` จาก `KSS-RCA-013`) **ไม่พอ** —
     destructive session handling เป็น *คลาส* ของบั๊ก ต้องมี guard ระดับระบบที่กวาดทุก call-site ของ `os.remove(...SESSION...)`

13. **Strict SET Short Uptick & No-Fabricated-Last Rule (KSS-RCA-017)**:
   - `validator.validate_short_uptick` เป็น **SSOT เดียว** และเป็น **strict** — ราคา SHORT ต้อง **`> last`** เท่านั้น
     (zero-plus tick / ราคาเท่า last = **reject**); ราคาต่ำสุดที่ถูกกฎ = `get_next_tick(last, 1)`
   - **ห้ามปั้น `last`**: `price_negotiation_service` ต้องใช้ `quote.get("last")` เท่านั้น — อ่านไม่ได้ = **fail-closed**
     (`needs_review=True`, ไม่เสนอปรับราคา) ห้าม backfill จาก Bid1/Offer1/ราคาคำสั่งเดิม (Anti-Mock, Invariant 1)
   - SHORT ที่ตั้งราคาไว้ **ที่ best offer หรือ +1 tick** แล้ว = **ปล่อยไว้** รอราคาขยับขึ้นเอง (ห้ามต่อราคา)
   - TradeMan quote API ไม่มี depth → `bid_1`/`offer_1` = `None` บน TradeMan (depth มีเฉพาะ Click2Win) —
     ห้ามตีความ `None` เป็น 0 หรือเดาราคา

14. **Real Order ID Only Rule (KSS-RCA-016)**:
   - `execute_order` ต้องคืน **`Order No.` จริง** ที่ read-back จาก View Order ledger (`_scrape_new_order_no`) เท่านั้น
   - **ห้าม** สร้าง id สังเคราะห์ (เช่น `ORD-<epoch>`) เพื่อให้ caller มีค่าตอบกลับ (Anti-Mock, Invariant 1)
   - TradeMan **ไม่มีปุ่ม "Change"** → amend = `cancel_order` + `execute_order(new price)` เสมอ (row-scoped บน `Order No.`)

15. **Symmetric DRY_RUN Bypass Rule (KSS-RCA-018)**:
   - ทุกเมธอดที่แตะคำสั่งจริง (`execute_order`, `cancel_order`, `modify_order_price`) ต้องรับ
     `bypass_dry_run: bool = False` และ gate DRY_RUN ด้วย `settings.DRY_RUN_MODE and not bypass_dry_run`
     **เหมือนกันทุกจุด** — ห้ามมีจุดใดใช้ `settings.DRY_RUN_MODE` เดี่ยว ๆ
   - **ห้ามพึ่ง `**kwargs` ให้กลืน flag** — ต้องประกาศเป็นพารามิเตอร์จริง (flag ที่ถูกกลืน = silent no-op = position หาย)
   - `modify_order_price` = cancel + re-submit ⇒ ต้องส่ง `bypass_dry_run` ต่อให้ **ทั้งสอง** ขั้น (L1510, L1524)
   - ลำดับใน `modify_order_price` **ต้องเป็น validate → cancel → submit เสมอ** (reject ก่อน cancel = ทิ้งคำสั่งเดิมไว้ครบ);
     ถ้าจะเรียก `validate_all` ใน `execute_order` (หลัง cancel) ต้องมี compensation/rollback กำกับ (ตอนนี้ยังไม่มี — open item)
   - amendment นี้ **เฉพาะ Krungsri TradeMan** (Broker Knowledge Isolation)
