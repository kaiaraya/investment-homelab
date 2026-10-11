# 📑 Krungsri Broker PDCA Retrospective & Standard Operating Procedure (SOP)

**Broker Module:** `app/brokers/krungsri/`  
**Target Platform:** Krungsri Securities (TradeMan Pro / Nuxt SPA)  
**Target Accounts:** Cash `3024952`, Margin `3024959`  
**Cycle Execution Date:** 2026-09-29  
**Review Standard:** PDCA (Plan - Do - Check - Act) Continuous Improvement  
**Status:** 🟢 Standardized & Verified in Production  

---

## 🧭 Executive Summary

เอกสารฉบับนี้คือบันทึกการถอดบทเรียน (Retrospective) เชิงวิศวกรรมการเงินและการควบคุมระบบอัตโนมัติ (Automated Trading Engineering) สำหรับโบรกเกอร์ **Krungsri Securities (TradeMan Pro)** เพื่อบันทึกปัญหาที่ตรวจพบในการส่งคำสั่งจริงด้วยเงินสด (Real Money Live Trading) และกำหนดมาตรฐานการป้องกันความผิดพลาดซ้ำ (Zero-Recurrence Guardrails) อย่างถาวร

---

## 🔄 1. Plan (P) — แผนงานและข้อกำหนดทางยุทธวิธี

| ข้อกำหนด (Requirement) | วัตถุประสงค์ (Objective) | กติกาการควบคุม (Rules & Constraints) |
| :--- | :--- | :--- |
| **Tactical Action Exit (Pillar 6)** | นำเข้าคำสั่งปิดไม้ประจำวันจาก Briefing ภาษาไทย | ตรวจจับหัวข้อ `[พอร์ต Krungsri Margin - KSS]` แมปเข้าบัญชี `3024959` |
| **Tactical Windows Allocation** | ป้องกันความผันผวนของราคาช่วงตลาดเปิด | • **ไม้กำไร (P&L >= 0%)**: ยิงช่วง `10:00 - 10:30` (Jitter 1-5 นาที) เพื่อรีบปลดล็อก Purchasing Power<br/>• **ไม้ขาดทุน (P&L < 0%)**: ยิงช่วง `10:30 - 12:00` (Jitter 3-15 นาที) เพื่อรอแรงขายตลาดเปิดสะเด็ดน้ำ |
| **Passive Limit Order Pricing** | หลีกเลี่ยงการเคาะขวากิน Bid (Slippage) | • ฝั่ง `SELL`: วางคิวที่ **Best Offer 1** (Best Ask)<br/>• ฝั่ง `COVER`: วางคิวที่ **Best Bid 1** (Best Bid) |
| **Pre-Trade Risk Validator** | ป้องกันคำสั่งผิดเงื่อนไขตลาดหลักทรัพย์ฯ | ตรวจสอบ SET Tick Size (0.01 / 0.02 / 0.05 / 0.10 / 0.25 / 0.50) และ Board Lot (100 หุ้น) |
| **Safety Gate (HITL)** | ป้องกันบอทส่งคำสั่งโดยพลการ | จัดเก็บสถานะเริ่มต้นในฐานข้อมูล SQLite พร้อมแจ้งเตือนเข้ามือถือ Xiaomi Mi 10T |

---

## ⚙️ 2. Do (D) — ผลการปฏิบัติการจริงในตลาดสด (Live Execution)

การทดสอบภาคสนามเมื่อวันที่ 2026-09-29 ดำเนินการผ่าน Playwright Browser Automation (`/usr/bin/google-chrome`) ด้วยเงินจริงในบัญชี Margin `3024959`:

1. **SAWAD**: ส่งคำสั่ง `SELL 2,200 หุ้น @ 22.50`
   - เลขที่คำสั่ง: `11011353`
   - สถานะ: 🟢 **`M` (100% MATCHED)**
   - มูลค่าเงินสดที่ได้รับ: **`49,500` บาท** (ล็อกกำไร +1.18%)
2. **COCOCO**: ส่งคำสั่ง `SELL 8,800 หุ้น @ 5.65`
   - เลขที่คำสั่ง: `11012119`
   - สถานะ: 🟢 **`M` (100% MATCHED)**
   - มูลค่าเงินสดที่ได้รับ: **`49,720` บาท** (จำกัดขาดทุนเหลือ -0.17%)
3. **AAV**: ส่งคำสั่ง `SELL 57,000 หุ้น @ 0.84`
   - เลขที่คำสั่ง: `11012916`
   - สถานะ: 🟢 **`M` (100% MATCHED)** (เข้าคิว Best Offer 1 แล้วจับคู่ครบ)
   - มูลค่าเงินสดที่ได้รับ: **`47,880` บาท**
4. **กำลังซื้อสุทธิ (Purchasing Power - PP)**:
   - เพิ่มขึ้นจาก `2,254.94` บาท สู่ **`120,982.59` บาท** พร้อมสำหรับการ Rebalance ไม้ถัดไป

---

## 🔍 3. Check (C) — การตรวจสอบข้อผิดพลาดและต้นตอ (Root Cause Analysis)

ระหว่างการทดลองและการยิงคำสั่งสด พบจุดบกพร่องและ Edge Cases ทั้งหมด 5 ประการ:

### ⚠️ Incident 1: ความเสี่ยงชน Derivative Warrant (DW) ในช่องค้นหา (`KSS-RCA-006`)
* **ปัญหาที่พบ:** เมื่อเปิดโมดอล Symbol Search แล้วกรอก `SAWAD` ระบบดึง `SAWAD01C2612A` (DW Call) ขึ้นมาเป็นตัวเลือกแรก หากโค้ดเลือกด้วย `.first` หรือคำค้น Substring หุ้นจะกลายเป็น DW ทันที
* **ต้นตอ:** แท็บเริ่มต้นของ TradeMan คือ `All` ซึ่งรวมทั้ง Stock, ETF, DW และอัลกอริทึมของโบรกเกอร์เรียงผลลัพธ์ตามรหัสหลักทรัพย์ย่อ
* **ระดับความรุนแรง:** 🔴 **CRITICAL** (อาจเกิด Fat-Finger ขาดทุนมหาศาลจากการซื้อขายอนุพันธ์แทนหุ้นแม่)

### ⚠️ Incident 2: ช่องกรอก PIN และปุ่มยืนยันใน Order Confirm Modal (`KSS-RCA-007`)
* **ปัญหาที่พบ:** ไดรเวอร์ดั้งเดิมค้นหา `input[type='password']` ไม่พบในโมดอลยืนยันคำสั่ง
* **ต้นตอ:** TradeMan พัฒนาบน Nuxt/Vuetify ช่อง PIN ใช้ ID เจาะจงคือ `input#pin` และซ่อนรหัสผ่านด้วย CSS `style="font-family: password;"` ไม่ได้ใช้ Attribute `type='password'` นอกจากนี้ยังมี Checkbox `input#savepin` และปุ่มยืนยันที่เป็นปุ่มสีแดง/เขียวระบุคำว่า `Sell` หรือ `Buy` ใน `span`
* **ระดับความรุนแรง:** 🟠 **HIGH** (คำสั่งค้างหน้าโมดอล ไม่ถูกยิงเข้าตลาด)

### ⚠️ Incident 3: การใช้รหัส PIN รวมปนกันระหว่างโบรกเกอร์ (`KSS-RCA-007`)
* **ปัญหาที่พบ:** ไฟล์ `.env` มีตัวแปร `TRADING_PIN` ตัวเดียว ทำให้เสี่ยงนำ PIN ของ Click2Win หรือ Liberator มาใช้สลับกับ Krungsri
* **ต้นตอ:** โครงสร้าง Config ขาด Broker-Specific Isolation
* **ระดับความรุนแรง:** 🟡 **MEDIUM** (เสี่ยง PIN Lock จากการกรอกผิด 3 ครั้ง)

### ⚠️ Incident 4: ช่องว่างของระบบยิงคำสั่งอัตโนมัติ (Missing Autonomous Dispatcher - `KSS-RCA-008`)
* **ปัญหาที่พบ:** คำสั่งที่ได้รับการอนุมัติมีสถานะ `SCHEDULED` แต่ไม่มี Background Worker คอยตรวจสอบเวลาและยิงคำสั่งออกไปอัตโนมัติ ต้องพึ่งพานักพัฒนามากดสั่งรันสคริปต์
* **ต้นตอ:** ยังไม่มีการติดตั้ง Scheduler Loop สำหรับ Action Exit แยกเฉพาะใน FastAPI Lifespan
* **ระดับความรุนแรง:** 🟠 **HIGH** (พลาดช่วงเวลายุทธวิธีตอนเปิดตลาด)

### ⚠️ Incident 5: ความเสี่ยงเซสชัน TradeMan หลุดข้ามคืน (`KSS-RCA-009`)
* **ปัญหาที่พบ:** หากตลาดปิดข้ามคืน เซสชัน SSO ของ TradeMan อาจหมดอายุ หากมารันตอน 10:00 น. พอดีแล้วติด SMS OTP จะทำให้ส่งคำสั่งไม่ทัน
* **ต้นตอ:** ขาดการรัน Pre-Flight Health Check ในช่วงก่อนตลาดเปิด (Pre-Market)
* **ระดับความรุนแรง:** 🟠 **HIGH** (พลาดโอกาสขายราคาเปิดที่ดีที่สุด)

---

## 🛠️ 4. Act (A) — การกำหนดมาตรฐานและเกราะป้องกันถาวร (Standardization)

เพื่อขจัดปัญหาทั้งหมดข้างต้น ได้มีการปรับแก้โค้ดและสร้างมาตรฐานถาวร (Codified Guardrails) ดังนี้:

### 🛡️ มาตรการที่ 1: เกราะป้องกัน DW 3 ชั้น (3-Tier Anti-DW Protocol)
1. **Tier 1 (Direct Table Selection - ปลอดภัย 100%):**  
   สำหรับการขายหุ้นที่มีในพอร์ต ให้เลือกล็อตหุ้นโดยการคลิกเซลล์ตาราง Portfolio โดยตรงผ่าน `td:text-is('{symbol}')` หลีกเลี่ยงการเปิดโมดอลค้นหาโดยสิ้นเชิง
2. **Tier 2 (Stock Filter Enforcement):**  
   หากจำเป็นต้องเปิดโมดอลค้นหา ระบบต้องบังคับคลิกปุ่มกรอง `Stock` (`.v-overlay--active button:text-is('Stock')`) ก่อนพิมพ์ค้นหาเสมอ เพื่อตัด DW และ ETF ทิ้ง
3. **Tier 3 (Post-Selection Verification & On-Hand Assertion):**  
   - ตรวจสอบกล่อง Symbol ให้ตรงกับชื่อหุ้นแบบ Exact Length
   - สำหรับฝั่ง `SELL` ต้อง Assert ค่า `On Hand` ว่าตรงกับจำนวนที่มีจริงในพอร์ตก่อนอนุญาตให้คลิกปุ่ม `#send_order__btn`

### 🛡️ มาตรการที่ 2: การแยก PIN เฉพาะโบรกเกอร์ (Isolated Broker PIN Standard)
- เพิ่ม `KRUNGSRI_PIN="<redacted>"` ใน `.env` และ `app/core/config.py`
- ไดรเวอร์ `trademan_driver.py` รองรับโมดอล:
  - กรอก `input#pin`
  - ติ๊ก `input#savepin`
  - คลิกปุ่มยืนยัน: `.v-overlay--active button:has(span:text-is('{side}'))`

### 🛡️ มาตรการที่ 3: ระบบยิงคำสั่งอัตโนมัติ `ActionExitDispatcher` Daemon
- สร้าง [`app/services/action_exit_dispatcher.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/action_exit_dispatcher.py) รันเป็น Background Task (รอบตรวจทุก 15 วินาที) ใน `app/main.py`
- **Dynamic Pricing**: ฝั่ง `SELL` ตามราคา Best Offer 1 / ฝั่ง `COVER` ตามราคา Best Bid 1
- **Continuous Polling**: สแกนตารางคำสั่ง TradeMan ตรวจสอบสถานะ Open (`O`) -> Matched (`M`) และส่งการแจ้งเตือนความสำเร็จเข้า KDE Connect CLI

### 🛡️ มาตรการที่ 4: การตรวจสอบระบบล่วงหน้าเวลา 09:45 น. (09:45 Pre-Flight Sentinel)
- ตรวจสอบความถูกต้องของเซสชัน TradeMan (บัญชี `3024959`) ทุกวันจันทร์-ศุกร์ เวลา 09:45 - 09:55 น.
- หากเซสชันหลุด จะพยายามล็อกอินใหม่อัตโนมัติ และหากติด SMS OTP จะยิงแจ้งเตือนด่วนเข้ามือถือ Xiaomi Mi 10T ทันทีเพื่อให้เตรียมตัวก่อน 10:00 น.

### 🛡️ มาตรการที่ 5: การควบคุมผ่าน Automated Unit Tests
- สร้าง [`tests/test_krungsri_pdca_guardrails.py`](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_krungsri_pdca_guardrails.py) ครอบคลุม 6 การทดสอบ:
  1. `test_krungsri_pin_isolation`
  2. `test_anti_dw_guardrail_exact_matching`
  3. `test_action_exit_parsing_and_tactical_windows`
  4. `test_action_exit_auto_schedule_db_status`
  5. `test_offer1_bid1_pricing_strategy`
  6. `test_preflight_0945_time_window_logic`
- ผลการรัน: **PASSED 6/6 (100%)**

---

## 📋 5. สรุป Checklist ประจำวันสำหรับ Operator / Agent

- [ ] **09:45 น.**: ได้รับแจ้งเตือน `✅ [TradeMan Pre-Flight 09:45] Session Ready` บนมือถือ
- [ ] **09:50 น.**: วางข้อความ Action Exit Briefing ลงใน `/console` แล้วกดปุ่ม `Parse & Auto-Schedule`
- [ ] **10:00 - 10:30 น.**: ไม้กำไรถูกยิงอัตโนมัติที่ Best Offer 1 (ตรวจดูแจ้งเตือนบนมือถือ)
- [ ] **10:30 - 12:00 น.**: ไม้ขาดทุน/คัดทิ้งถูกยิงอัตโนมัติที่ Best Offer 1 / Best Bid 1
- [ ] **เมื่อคำสั่งจับคู่ครบ**: ได้รับแจ้งเตือน `🎉 [Action Exit MATCHED]` พร้อมยอดเงินสดที่ปลดล็อก
