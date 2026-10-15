# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: Liberator Securities (WebTrade)
**Broker Platform:** `LIBERATOR` (Liberator WebTrade Portal)  
**Main URL:** `https://webtrade.liberator.co.th`  
**Target Accounts:** Cash Balance (`<liberator-acct>` / `70559382 C`)  
**Last Updated:** 2026-10-06  
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing  

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose & PDCA Policy)
เอกสารนี้ทำหน้าที่เป็น **Single Source of Truth (SSOT)** สำหรับองค์ความรู้เฉพาะทางของ **Liberator WebTrade** เพื่อ:
1. บันทึก Root Cause, Edge Cases, และวิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Verified Solutions) จากการทดสอบจริง
2. ป้องกันไม่ให้ Agent หรือ Developer ต้องแก้ปัญหาเดิมซ้ำ ช่วยประหยัดเวลาและลดความเสี่ยงต่อการถูกล็อกบัญชี
3. ติดตามและกำกับดูแลความปลอดภัยของบัญชีเทรดอย่างเข้มงวดสูงสุด

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :--- :---: | :---: | :--- | :--- | :---: |
| 2026-10-03 | `LIB-RCA-001` | ความเสี่ยงบัญชีถูก Lock หากกรอก OTP ผิดเกิน 3 ครั้ง / ระบบเกือบหยิบ OTP เก่ามากรอก | `candidate_payload` ใน `kdeconnect_service` ยอมให้หยิบ SMS ล่าสุดมาใช้แม้ Ref Code ไม่ตรง เมื่อเกิด Network Latency | 🟢 RESOLVED |
| 2026-10-03 | `LIB-RCA-002` | อัตราการยิง Gemini เกินโควตา Free Tier (429 Too Many Requests) ขณะรอ OTP | `extract_otp_from_text` ส่งแจ้งเตือนทุกแอปบนมือถือเข้า LLM แม้ไม่มีคำสำคัญเกี่ยวกับ OTP/ตัวเลข | 🟢 RESOLVED |
| 2026-10-03 | `LIB-RCA-003` | ข้อผิดพลาด `NameError: name 'AuthStatus' is not defined` | ลืม Import Enum `AuthStatus` และ `BrokerPlatform` ในโมดูล `driver.py` | 🟢 RESOLVED |
| 2026-10-03 | `LIB-RCA-004` | ตัวเลขติดลบ (เช่น Unreal P/L) แปลงเป็น float แล้วได้ 0.0 หรือเกิด ValueError | เว็บ Liberator ใช้ Unicode En-Dash (`–` U+2013) แทนเครื่องหมายลบมาตรฐาน (`-` ASCII 45) | 🟢 RESOLVED |
| 2026-10-03 | `LIB-RCA-005` | แถวจากตารางประวัติ Order (#14560) ถูกดึงเข้ามาปนในรายชื่อหุ้น Portfolio | ใช้ selector กวาด `table tr` รวม ทำให้จับแถวจากตารางคำสั่งซื้อขายที่มีโทเค็นคล้ายกัน | 🟢 RESOLVED |
| 2026-10-05 | `LIB-RCA-006` | Startup รายงานว่า Liberator session ใช้งานได้ แต่จริง ๆ JWT หมดอายุ (~24 ชม.) แล้ว → เข้า `/Portfolio` แล้วโดน Redirect ไป `/login` | `verify_saved_session()` ไม่เคย decode/ตรวจ `exp` ของ JWT ในคุกกี้ `api-token` / `ws-token` จึงมอง session ที่ "จำไว้แต่หมดอายุ" ว่าใช้ได้ (ขัด Anti-Mock Guardrail) | 🟢 RESOLVED |
| 2026-10-05 | `LIB-RCA-007` | `scripts/preflight_check.py` รายงาน `✅ Liberator WebTrade: Saved session exists` (และแบบเดียวกันกับ Click2Win) ทั้งที่ JWT ของ session **หมดอายุไปแล้ว ~29 ชม.** → ผู้ใช้/Agent เข้าใจผิดว่าระบบพร้อมใช้ | preflight ตรวจแค่ `os.path.exists(lib_path)` (L120-122) ไม่ได้เรียก `session_token_expiry()` / `verify_saved_session()` ที่ `LIB-RCA-006` แก้ให้ decode `exp` แล้ว → preflight ยัง "เชื่อว่าใช้ได้" ขณะที่ driver บอก "หมดอายุ" (ขัด Zero-Contradiction) | 🟢 **RESOLVED (2026-10-06)** — preflight ใช้ shared inspector (`app.brokers.liberator.session_health` + `app.brokers.krungsri.session_health`) แล้ว; Krungsri เองก็ปิดช่องโหว่เดียวกันใน `KSS-RCA-011` |
| 2026-10-09 | `LIB-RCA-016` | `page.locator("#OrderTableList tbody tr").filter(has_text=re.compile(r"\b11894\b"))` คืน **0 แถว** ทั้งที่มี order #11894 จริงในตาราง ⇒ หาปุ่ม `Change`/`Cancel` ไม่เจอ (`matches=0`, click timeout) | `<tr>` ของ `#OrderTableList` เป็น Vue ที่ `<td>` ติดกันโดยไม่มี text node คั่น → `textContent` = `'1189410:03:21BCHSELL12.004,00004,0000Open Change  Detail  Cancel '` → `\b` หลัง `11894` ไม่มี (ตัวถัดไปคือ `1` ของ `10:03:21`) จึง **ไม่ match เด็ดขาด** | 🟢 RESOLVED — anchor ด้วย checkbox แทน: `#OrderTableList tbody tr:has(input[id='<order_no>'])` |
| 2026-10-09 | `LIB-RCA-017` | ถ้ากรอก `#price` / `#volume` / `#pin` ตรง ๆ ขณะ amend → ค่าไปลง **ฟอร์ม Buy/Sell footer** ไม่ใช่ฟอร์ม amend ในโมดอล | DOM มี id **ซ้ำ 2 ชุด** — footer มาก่อน (ค่า `''`, placeholder `Price ...`), overlay amend มาหลัง (ค่า `'12.00'`) → `page.locator("#price")` = first match = **ตัวผิด** | 🟢 RESOLVED — scope ด้วย `div.overlay` เสมอ (`overlay.locator("#price")`) |
| 2026-10-09 | `LIB-RCA-018` | `cancel_order()` คืน `"Order #NNN does not have an active cancel action (may already be matched)"` ทั้งที่แถวยังมีปุ่ม `Cancel` อยู่ ⇒ **cancel ไม่เคยทำงานเลย** | selector เดิม `button:has-text('Cancel'), [role='button']:has-text('Cancel'), svg.text-sell` — DOM จริงเป็น `<div class="cursor-pointer">Cancel</div>` (ไม่มี `button`/`role`) และ `svg.text-sell` เป็น selector สกุล **Click2Win** (ผิด Broker Knowledge Isolation) | 🟡 CODE FIXED — ใช้ `_order_action_locator(row, "Cancel")`; **ยังไม่ live-test** (ต้องมี order ที่ user ยอมให้ยกเลิก → HITL) |
| 2026-10-15 | `LIB-RCA-019` | (D2/D3/D4 hardening) ① `get_market_bid_offer` อ่าน DOM ไม่ได้แล้วคืน sentinel `_unknown_quote` ที่ยัง "หน้าตาเหมือน quote" (`source="unavailable"`, ทุกตัวเลข None) → caller ที่ไม่ได้เช็ค `source` จะเอา `None or order_price` ไปใช้ = ราคาเดา (Anti-Mock). ② `change_order` ไม่ยืนยัน symbol ของแถวจริงก่อนกด `Change` → เสี่ยงแก้ออเดอร์ผิดตัว (`/nego lib` ส่งมาแค่ `order_no`) | ① สัญญาผลลัพธ์ไม่มี field บังคับให้ fail-closed (`success`/`status` ไม่มี) จึงพึ่ง caller ทุกจุดให้จำเช็ค `source` เอง. ② symbol มาจาก ledger ที่อ่านไว้ก่อนหน้า (TOCTOU) ไม่ได้ re-read จากแถวออเดอร์ที่กำลังจะแก้ | 🟢 **RESOLVED (unit/mock)** — ① `_unknown_quote` → `LiberatorDriver.QUOTE_UNAVAILABLE` (`success=False`+`status`+`error`); ② `change_order(..., expected_symbol=...)` re-read แถวจริง → ไม่ตรง = `SYMBOL_MISMATCH` **ก่อนกด**; ③ `/nego lib` (`_broker_modify` LIVE) re-check ราคา/symbol/side → ไม่ผ่าน = `QUOTE_UNAVAILABLE` + หยุด batch + push `unavailable_card`. Live verify = การ์ดถัดไป (TASK-loop1-4) |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `LIB-RCA-001`: 3-Attempt Lockout Risk & Strict Ref Code Matching
* **วันและเวลา:** 2026-10-03 13:10 น.
* **อาการ (Symptom):**  
  ระบบส่งคำขอ OTP ไปยัง Liberator ซึ่งหน้าจอกำหนด `(ref. code: NOQO)` แต่ระบบหยิบ OTP เก่าจากรอบก่อนหน้า `(Ref: KCNX)` มาเตรียมกรอก ซึ่งหากกรอกผิดสะสมเกิน 3 ครั้ง บัญชี Liberator จะถูกระงับ (Account Locked) ทันที
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  ใน [app/services/kdeconnect_service.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/kdeconnect_service.py) มีโค้ด Fallback `candidate_payload = payload` ที่อนุญาตให้หยิบข้อความ SMS ล่าสุดที่พบในรอบ 5 นาทีมาใช้สำรอง หาก SMS ใหม่ยังเดินทางมาไม่ถึงจากปัญหาเครือข่ายมือถือล่าช้า ทำให้ระบบหยิบ OTP เก่าของ Ref: KCNX มาแทน
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  1. **Strict Ref Matching:** ปรับปรุงเงื่อนไขใน `kdeconnect_service.py`: เมื่อมีการระบุ `norm_expected_ref` จะไม่อนุญาตให้เซ็ตหรือคืนค่า `candidate_payload` ที่มี Ref Code ขัดแย้งกันอย่างเด็ดขาด
  2. **Extended Timeout to 180s:** ปรับเวลา Timeout รอรับ SMS จาก 90 วินาที เป็น 180 วินาที เพื่อรองรับความล่าช้าของเกตเวย์ SMS ผู้ให้บริการ
  3. **Visual Screen Confirmation:** ใส่การไฮไลต์สีกรอบเขียวนีออน (`#00E676`) บนช่องกรอกใน Chrome และหน่วงเวลา Safety Hold 4 วินาทีก่อนกดส่งคำตอบ เพื่อให้ผู้พัฒนาสามารถตรวจเช็กความถูกต้องบนหน้าจอได้ด้วยตาเปล่า

---

### 📌 Incident `LIB-RCA-002`: PydanticAI / LLM Polling Rate Limit (HTTP 429)
* **วันและเวลา:** 2026-10-03 13:06 น.
* **อาการ (Symptom):**  
  ในระหว่างวนลูปดักจับ OTP ปรากฏข้อความแจ้งเตือน `429 Too Many Requests: Quota exceeded for metric: generativelanguage.googleapis.com`
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  เมื่อ `kdeconnect-cli` ดึงรายการ Notification ทั่วไปในโทรศัพท์ (เช่น ข่าว, การแจ้งเตือนระบบ) ฟังก์ชัน `extract_otp_from_text` ใน [app/ai/otp_agent.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/ai/otp_agent.py) ที่ไม่พบ OTP จาก Regex จะส่งข้อความที่ไม่เกี่ยวข้องทั้งหมดไปให้ Gemini ประมวลผล ทำให้ชนเพดาน Free Tier 5 requests/minute ทันที
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  เพิ่มตัวกรอง **Keyword & Digit Pre-Filter** ก่อนเรียก LLM:
  ```python
  has_otp_hint = any(w in clean_text.lower() for w in ["otp", "code", "ref", "รหัส", "verify", "verification", "sms", "liberator", "krungsri", "password"])
  has_digits = bool(re.search(r'\d{3,}', clean_text))
  if (model_override or is_gemini_configured()) and (has_otp_hint or has_digits):
      ...
  ```
  ข้อความที่ไม่มีคำใบ้เกี่ยวกับรหัสยืนยันหรือตัวเลขเลยจะถูกตัดทิ้งทันทีในระดับมิลลิวินาที ไม่เปลือง Quota API

---

### 📌 Incident `LIB-RCA-003`: Missing Schema Enums in Driver
* **วันและเวลา:** 2026-10-03 13:09 น.
* **อาการ (Symptom):**  
  `NameError: name 'AuthStatus' is not defined`
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  ใน [app/brokers/liberator/driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/liberator/driver.py) มีการเรียกใช้ Enum `AuthStatus.AUTHENTICATED` และ `BrokerPlatform.LIBERATOR` แต่ตอน Import มีเพียง `LoginResult`
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  เพิ่ม `LIBERATOR` เข้าไปใน `BrokerPlatform` Enum ใน [app/schemas/auth.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/schemas/auth.py) และ Import `AuthStatus, BrokerPlatform` เข้ามาใน `driver.py` ครบถ้วน

---

### 📌 Incident `LIB-RCA-004`: Unicode En-Dash in Negative Numbers
* **วันและเวลา:** 2026-10-03 13:21 น.
* **อาการ (Symptom):**  
  ค่า Unrealized PnL หรือ Realized PnL ที่ติดลบ (เช่น `–11.61`, `–270.07`, `–301.01`) เมื่อแปลงผ่าน `parseFloat()` ใน JavaScript หรือ `float()` ใน Python ให้ผลลัพธ์เป็น `NaN` หรือ `0.0`
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  Liberator WebTrade ใช้ตัวอักษร **Unicode En-Dash (`–`, `\u2013`)** ในการแสดงผลค่าติดลบ ซึ่งไม่ใช่เครื่องหมายขีดลบมาตรฐาน ASCII Minus (`-`, ASCII 45) ทำให้ Parser ตัวเลขมาตรฐานล้มเหลว
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  สร้างฟังก์ชัน Normalizer ก่อนแปลงตัวเลขทุกจุด:
  ```javascript
  function cleanNum(val) {
      if (!val) return 0.0;
      let s = val.toString().replace(/,/g, "").replace(/–/g, "-").replace(/%/g, "").trim();
      return parseFloat(s) || 0.0;
  }
  ```

---

### 📌 Incident `LIB-RCA-005`: Multi-Table Row Collision (Orders vs. Portfolio)
* **วันและเวลา:** 2026-10-03 13:22 น.
* **อาการ (Symptom):**  
  มีสัญลักษณ์หุ้นแปลกปลอมชื่อ `14560` ปรากฏอยู่ในรายชื่อหุ้นพอร์ตโฟลิโอ (Holdings)
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  หน้าเว็บ Liberator Portfolio แสดงตารางหลายชุดในหน้าเดียวกัน ได้แก่:
  1. ตาราง Portfolio Holdings (Table 0)
  2. ตาราง 5-Bid/Offer Depth (Table 1)
  3. ตาราง Order Status (Table 2)  
  การใช้ Selector รวมแบบ `document.querySelectorAll("table tr")` ทำให้แถวของคำสั่งซื้อขาย `#14560` ซึ่งมีรูปแบบคล้ายแถวหุ้นถูกประมวลผลเข้ามาเป็นหุ้น
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ใช้ **Deterministic Table Header Isolation**:
  - หาตารางที่ `thead` มีคำว่า `symbol` และ `in port` -> ใช้เป็นตาราง Holdings เท่านั้น
  - หาตารางที่ `thead` มีคำว่า `order #` และ `side` -> ใช้เป็นตาราง Order Status เท่านั้น
  - ใส่ Regex Validation กำกับชื่อสัญลักษณ์หุ้น `^[A-Z][A-Z0-9.\-]{1,9}$` และห้ามเป็นตัวเลขล้วน `!/^\d+$/.test(symbol)`

---

### 📌 Incident `LIB-RCA-006`: Stale (~24h) JWT Remembered as a Valid Session
* **วันและเวลา:** 2026-10-05 (ตรวจพบช่วง Startup)
* **อาการ (Symptom):**
  ระบบ Startup พบไฟล์ `data/liberator_session.json` และรายงานว่า Liberator พร้อมใช้งาน
  แต่เมื่อตรวจสอบสถานะจริงกลับถูก Redirect ไปหน้า `/login` ทำให้ดึงพอร์ต/ยอดเงินไม่ได้
* **การสืบหาต้นตอ (Root Cause Analysis):**
  `LiberatorDriver.verify_saved_session()` เดิมตรวจแค่ "ไฟล์มีอยู่ไหม" + "หลัง navigate แล้ว URL เป็น login ไหม"
  แต่ **ไม่เคย decode/validate ค่า `exp` ของ JWT** ในคุกกี้ `api-token` / `ws-token`
  Liberator ออก JWT อายุราว **24 ชั่วโมง** (หลักฐานจริงจากไฟล์: `exp = 1791094359` → 2026-10-04 13:12:39 น.
  ขณะที่ไฟล์ถูกบันทึกเมื่อ 2026-10-03 06:12:42 UTC) เมื่อรันวันที่ 2026-10-05 JWT จึงหมดอายุไปแล้ว
  แต่โค้ดยังถือว่า session ที่ "จำไว้" นั้นใช้ได้ (ขัดกับ Anti-Mock Guardrail / Invariant 1)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - ไฟล์ session อาจมีเพียงคุกกี้กันบอตของ Incapsula (`visid_incap_*`, `nlbi_*`, `incap_ses_*`) โดยไม่มี JWT เลย → ต้องไม่ throw และต้องปล่อยให้ตรวจ DOM ต่อ
  - JWT ที่ใกล้หมดอายุ (เหลือ < safety margin 60 วินาที) ควรถูกปฏิเสธล่วงหน้าเพื่อกัน race condition ระหว่าง login
  - ต้องถอด `exp` จาก JWT ก่อน แล้วค่อย fallback ไปที่ฟิลด์ `expires` ของคุกกี้ถ้าถอด JWT ไม่ได้
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  เพิ่ม helper ใน [app/brokers/liberator/driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/liberator/driver.py):
  ```python
  def _session_token_expiry(self) -> Optional[int]:
      # decode JWT payload ของคุกกี้ api-token / ws-token -> คืนค่า exp (Unix sec)
      ...
      return jwt_exp if jwt_exp is not None else fallback_exp

  def _saved_session_expired(self, safety_margin_seconds: int = 60) -> bool:
      exp = self._session_token_expiry()
      if exp is None:
          return False  # ตรวจไม่ได้ -> ให้ไปตรวจ DOM ต่อ ไม่ block
      return exp <= int(time.time()) + safety_margin_seconds
  ```
  แล้วเรียกที่ต้น `verify_saved_session()`:
  ```python
  if self._saved_session_expired():
      self.status = "DISCONNECTED"
      return False
  ```
  ทำให้ session ที่ JWT หมดอายุถูกปฏิเสธทันที (< 1 ms) โดยไม่ต้อง launch browser แล้วบังคับเข้าสู่ fresh login
* **เทสต์ที่พิสูจน์ (Regression Tests):** [tests/test_liberator_session.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_liberator_session.py)
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  Startup ไม่ควร auto-login Liberator แบบ headed (เสี่ยงกระตุ้น 2FA SMS OTP โดยพลการ ผิด Invariant 7)
  ให้รายงานสถานะจริงเป็น "LIBERATOR OFFLINE" และให้ผู้ใช้กด 'Connect All Brokers' บน `/console` เมื่อต้องการเชื่อมต่อ
  (ดูงาน Hardware Bridge ที่เกี่ยวข้อง: [rca/shared/rca_kdeconnect_bridge.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_kdeconnect_bridge.md))


---

### 📌 Incident `LIB-RCA-007`: Preflight False-Positive — `os.path.exists()` Is Not Session Validity
* **วันและเวลา:** 2026-10-05 (ระหว่างทดสอบ Stage 3 — Liberator WebTrade Session Gate)
* **อาการ (Symptom):**
  - `scripts/preflight_check.py` (รัน 18:16) รายงาน:
    ```
    ✅ Liberator WebTrade: Saved session exists (data/liberator_session.json)
    ```
    ซึ่งผู้ใช้อ่านแล้วเข้าใจว่า Liberator พร้อมใช้งาน
  - แต่เมื่อรัน Stage 3 จริง (`stage3_verify_liberator_session`) ได้ผลตรงข้าม:
    ```
    [WARNING] Liberator saved session JWT expired/insufficient (exp=1791094359, now=1791199325, remaining=-104966s). Forcing fresh login.
    [INFO]    Liberator saved session JWT is EXPIRED. Discarding stale session.
    ⚠️  LIBERATOR OFFLINE: No valid (unexpired) Liberator session was found.
    STAGE3_RESULT=False elapsed=0.0s
    ```
  - `remaining=-104966s` ≈ **หายไปแล้ว ~29 ชั่วโมง**
* **การสืบหาต้นตอ (Root Cause Analysis):**
  - [scripts/preflight_check.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/preflight_check.py) L120-122 ใช้ **`os.path.exists(lib_path)`** เป็นเกณฑ์เดียว
    แล้วพิมพ์ `✅ Saved session exists` → เป็นแค่ "ไฟล์มีอยู่" ไม่ใช่ "session ยังไม่หมดอายุ"
  - ขณะเดียวกัน `LIB-RCA-006` แก้ให้ `liberator_driver.verify_saved_session()` **decode JWT `exp`** และปฏิเสธ session ที่หมดอายุแล้ว (ทำงานถูกต้องจริง — ยืนยันจากการรันครั้งนี้)
  - ⇒ เกิด **contradiction 2 แหล่งความจริง**: preflight (เช็คไฟล์) พูดว่า ✅ แต่ driver (เช็ค `exp`) พูดว่า ❌
  - รากของปัญหาเชิงออกแบบ: preflight ไม่ได้ **reuse** ตรรกะ validation ตัวเดียวกับ driver (duplicated/weaker check)
* **Edge Cases ที่พบ (Edge Cases Identified):**
  - "ไฟล์ session มีอยู่" ≠ "session ใช้ได้" — โดยเฉพาะ session ที่หมดอายุแบบ TTL/JWT
  - ปัญหาเดียวกันมีอยู่กับ **Click2Win**: `scripts/preflight_check.py` L113-115 ใช้ `os.path.exists("data/click2win_session.json")` เช่นกัน
  - อาการนี้ **หลอกตาแบบ false-positive** คล้าย `KDE-RCA-002` (รายงานพร้อมทั้งที่ยังไม่พร้อม) — คนละ component แต่ pattern เดียวกัน
  - การแก้ที่ driver แต่ไม่แก้ที่ preflight ทำให้เอกสาร/เครื่องมือขัดกัน (ผิดหลัก Zero-Contradiction) แม้ตัว automation หลักจะถูกต้องแล้ว
* **วิธีแก้ปัญหาที่แนะนำ (Recommended Solution — ยังไม่ลงมือ เพราะอยู่นอก scope):**
  1. ให้ preflight เรียกใช้ตัวตรวจเดียวกับ driver แทน `os.path.exists` เช่น
     `liberator_driver.saved_session_expired()` / `session_token_expiry()` แล้วรายงานผลลัพธ์จริง
  2. แสดงผล 3 สถานะให้ชัดเจน: `✅ Active (เหลือ Ns)` / `⚠️ EXPIRED (เกินมา Ns — ต้อง reconnect)` / `ℹ️ No saved session`
  3. ทำเช่นเดียวกันกับ Click2Win เพื่อไม่ให้เกิด contradiction ซ้ำ
  4. เพิ่ม Unit Test กัน regression (ไฟล์มีอยู่แต่ `exp` ผ่านมาแล้ว → ต้องรายงาน EXPIRED ไม่ใช่ ✅)
* **หมายเหตุความปลอดภัย (Anti-Mock / Invariant 7):**
  Stage 3 **ทำงานถูกต้องแล้ว** — ตรวจพบ session หมดอายุ, ทิ้งไฟล์ stale, และ **ไม่** สั่ง headed login ที่จะกระตุ้น 2FA SMS
  โดยพลการ (`start_homelab.py` L454-458) ⇒ สิ่งที่ต้องแก้คือ *ความถูกต้องของรายงาน preflight* ไม่ใช่ logic ของ Stage 3
* **ข้อคิดเห็นและแนวทางจากผู้ใช้ (User Feedback & Context):**
  - ผู้ใช้สั่งให้ทดสอบ "Step 3" ต่อหลัง Stage 2 ผ่าน → นำมาซึ่งการค้นพบ false-positive นี้
  - แนวปฏิบัติของผู้ใช้: ทุกการทดสอบต้องมีหลักฐานจริงและต้องไม่รายงานความพร้อมเกินจริง (Zero Hallucination)
* **✅ Reconciliation (2026-10-06) — ปิดเหตุการณ์:**
  - Liberator: `scripts/preflight_check.check_liberator_session()` เรียก
    `app.brokers.liberator.session_health.session_health()` (decode JWT `exp` ตัวเดียวกับ driver)
    → รายงาน `EXPIRED` / `Session active` ตามจริง (ไม่ใช่ `os.path.exists` อีกต่อไป)
  - Click2Win (SIMULATION): ใช้ `click2win_session_status()` — presence + age + cookie count, ไม่มี ✅ ปลอม
  - Krungsri: ปิดช่องโหว่เดียวกันใน **`KSS-RCA-011`** ผ่าน
    `app.brokers.krungsri.session_health.session_file_info()` (presence + age + `needs_fresh_login`)
  - Regression tests: `tests/test_preflight_check.py` (render: expired/active/no-session/undeterminable +
    Krungsri expired/no-session/recent) — **22 passed**
  - หลักฐานสด (รันจริง 2026-10-06 22:5x): `⚠️ Liberator WebTrade: Saved session EXPIRED (~14413s ago)`

---

## 🧪 Live Verification Evidence (2026-10-05) — ยืนยันว่า Fix `LIB-RCA-006` ทำงานจริง

ทดสอบ Liberator WebTrade headed login ผ่าน harness แบบ checkpoint-gated
(`/tmp/liberator_stepwise_login.py`), headed Chrome บน `DISPLAY=:0`, หยุดยืนยันผู้ใช้ทุก gate — **ผ่านทุก gate**

| Gate | ผลลัพธ์ |
| :-- | :-- |
| Staleness (โหลด saved cookies → ยิง protected `/Portfolio`) | ถูก Redirect ไป `/login` → ยืนยัน `LIB-RCA-006` ปฏิเสธ JWT ที่หมดอายุ ~30 ชม. ถูกต้อง |
| Credentials → 2FA | `.../otp?telNo=061XXX6363`, Ref `JOXV` |
| OTP auto-capture (KDE) | `MASKED=84****` (ref ตรง) → submit → เด้งเข้า `.../Market` (dashboard) |
| Portfolio + persist | final `.../Portfolio`; เขียน `data/liberator_session.json` ใหม่; driver `saved_expired=False`, `token_exp=1791288007` |

* **ยืนยัน Symptom:** saved session JWT หมดอายุ (~24 ชม. TTL) และ guard `LIB-RCA-006` ทำงานตามออกแบบ
* **Zero-Contradiction:** `LIB-RCA-007` **ยังเปิดอยู่** — `scripts/preflight_check.py` ยังรายงาน
  `✅ Saved session exists` (เช็คแค่ไฟล์) ขณะที่ driver รายงาน EXPIRED ⇒ ต้อง reconcile ต่อไป
* **Non-Destructive (Invariant 8):** ไฟล์ stale ถูกเก็บสำรองไว้ที่ `data/liberator_session.stale.bak.json`
* **Anti-Mock:** ใช้ค่า credential จาก `.env` จริงเท่านั้น ไม่มี mock/ค่าปลอมใด ๆ ในขั้นตอนนี้

