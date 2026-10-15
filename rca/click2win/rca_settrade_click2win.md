# Cumulative Root Cause Analysis (RCA) & Edge Case Knowledge Base: Settrade Click2Win Sandbox
**Broker Platform:** `CLICK2WIN` (Settrade Streaming Sandbox)  
**Main URL:** `https://click2win.settrade.com`  
**Target Accounts:** Equity Cash Balance (`CW32_E_7338419`), Derivatives TFEX (`CW32_D_7338419`)  
**Last Updated:** 2026-09-29  
**Lifecycle Methodology:** PDCA (Plan - Do - Check - Act) Continuous Annealing  

---

## 🧭 วัตถุประสงค์ของเอกสาร (Purpose & PDCA Policy)
เอกสารนี้ทำหน้าที่เป็น **Single Source of Truth (SSOT)** สำหรับองค์ความรู้เฉพาะทางของ **Settrade Click2Win (Streaming)** เพื่อ:
1. บันทึก Root Cause, Edge Cases, และวิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Verified Solutions) จากการทดสอบจริง
2. ป้องกันไม่ให้ Agent หรือ Developer ต้องแก้ปัญหาเดิมซ้ำๆ ในวันถัดไป ช่วยประหยัดเวลาและลดการใช้ Token
3. รวบรวม User Guidance และ Feedback เพื่อให้ระบบปรับตัวแบบ Self-Annealing ได้อย่างต่อเนื่อง

---

## 📋 สารบัญประวัติเหตุการณ์และการแก้ไข (PDCA Incident Registry)

| วันที่ | รหัสเหตุการณ์ | ปัญหาที่พบ (Symptom) | สาเหตุที่แท้จริง (Root Cause) | สถานะ |
| :---: | :---: | :--- | :--- | :---: |
| 2026-09-28 | `C2W-RCA-001` | ปุ่ม Action บน `/console` ถูกกดย้ำได้ หรือ Spinner หมุนหายไปเมื่อหน้าจอรีเฟรช | Client Polling ทุก 2s ดึง HTML มาเรนเดอร์ทับ DOM เดิม ล้างสถานะ Disable | 🟢 RESOLVED |
| 2026-09-28 | `C2W-RCA-002` | ส่งคำสั่งขาย (SELL) บน Equity ถูก Reject ทันที | Click2Win Equity ไม่รองรับ Naked Short Selling ต้องซื้อเข้าพอร์ตก่อนจึงจะขายได้ | 🟢 RESOLVED |
| 2026-09-28 | `C2W-RCA-003` | สั่ง `LONG SPALIU26 @ 16.05` ถูกปฏิเสธจากโบรกเกอร์ | ผิดกฎ Tick Size สเปรดราคาช่วง ฿10-25 ต้องลงท้ายด้วย 0.10 เสมอ | 🟢 RESOLVED |
| 2026-09-28 | `C2W-RCA-004` | ส่งคำสั่ง TFEX ผิดพลาด / Radio Button หลุด | การสลับบัญชีไป TFEX จะล้างค่า Radio (Long/Short) ต้องเลือกข้างใหม่อีกครั้งเสมอ | 🟢 RESOLVED |
| 2026-09-28 | `C2W-RCA-005` | Settrade Open API ส่งคืน `403 Forbidden` ไม่ส่ง Market Data | Developer Account หมดอายุเนื่องจากไม่มีกิจกรรม | 🟢 RESOLVED (Switch to Streaming Favourite Polling) |
| 2026-10-15 | `C2W-RCA-006` | รัน `scripts/verify_changes.py --full` แล้ว runbook ที่ git track ถูกเขียนทับทุกครั้ง (`click2win_order_submit.md`, `shared/test_anneal_wf.md`) — `Recorded At` เปลี่ยน + ข้อความ "(Self-Annealed: …)" ต่อท้ายซ้ำ (F-11 ×75) | เทสต์ annealing เรียก `WorkflowEngine.save_workflow_spec()`/`update_workflow_step()` ขณะที่ `workflow_engine.WORKFLOWS_DIR` ชี้ที่ repo `learned_workflows/` จริง | 🟢 RESOLVED (test isolation) |

---

## 🔬 รายละเอียดเชิงลึกรายเหตุการณ์ (Incident Deep Dives)

### 📌 Incident `C2W-RCA-001`: UI Concurrency Lock & Persistent Spinner
* **วันและเวลา:** 2026-09-28 03:20 น.
* **อาการ (Symptom):**  
  เมื่อผู้ใช้กดยืนยันคำสั่งซื้อขายบน Web Cockpit Console (`/console`) ปุ่มไม่มีสัญลักษณ์แสดงว่ากำลังประมวลผล และสามารถถูกคลิกซ้ำได้ หรือเมื่อใส่ `disabled` แบบ Ad-hoc ปุ่มจะหลุดจากการ disable ทุก 2 วินาที
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  หน้าเว็บคอนโซลมีฟังก์ชัน Background Polling ดึงข้อมูลใหม่ทุก 2 วินาทีมาเรนเดอร์ทับ DOM Element เดิม ทำให้ค่าแอตทริบิวต์ `disabled` หรือคลาส CSS ที่แทรกเข้าไปแบบชั่วคราวถูกล้างทิ้งทันที
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ใน [app/console.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/console.py):
  1. ใช้ **State-Driven Set (`inFlightHitlOrders = new Set()`)** เพื่อจำ Order ID ที่อยู่ระหว่างยิง API
  2. สร้าง Helper function `withButtonLock(btn, actionFn)`:
     - ใส่คลาส `.btn-locked` (`pointer-events: none; opacity: 0.6;`)
     - แทรก Animated Spinner `.btn-spinner` (หมุน 360°)
     - ปลดล็อกเมื่อ Network Request เสร็จสมบูรณ์แล้วเท่านั้น

---

### 📌 Incident `C2W-RCA-002`: Equity Naked Short Rejection & SBL Constraint
* **วันและเวลา:** 2026-09-28 04:10 น.
* **อาการ (Symptom):**  
  การทดสอบ Phase B เริ่มต้นด้วยการสั่ง `SELL 100 BDMS` ปรากฏว่าออเดอร์ถูก Settrade Click2Win ปฏิเสธ
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  บัญชี Equity บน Click2Win เป็นบัญชีจำลองแบบ Cash Balance ทั่วไป ไม่รองรับ Naked Short Selling หากในพอร์ตยังไม่มีหุ้นตัวนั้นอยู่ จะไม่สามารถส่งคำสั่งขายได้
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  จัดลำดับการทดสอบแบบ Full-Cycle ที่ถูกต้อง:
  1. **Step 1:** ส่งคำสั่งซื้อ `BUY 100 หุ้น @ Best Offer` เพื่อให้ Match ทันที
  2. **Step 2:** ตรวจสอบตาราง ReactVirtualized ใน Portfolio พบจำนวนหุ้นเพิ่มขึ้นจริง
  3. **Step 3:** ส่งคำสั่งขาย `SELL 100 หุ้น @ Best Bid` เพื่อปิดสถานะและบันทึก Realized P&L

---

### 📌 Incident `C2W-RCA-003`: SET Tick Size Strict Enforcement
* **วันและเวลา:** 2026-09-28 04:30 น.
* **อาการ (Symptom):**  
  คำสั่ง `LONG 1 SPALIU26 @ 16.05` ถูกปฏิเสธจากระบบ
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  กฎสเปรดราคา (Tick Size) ของตลาดหลักทรัพย์แห่งประเทศไทย:
  - ราคาต่ำกว่า ฿2.00: สเปรด 0.01
  - ราคา ฿2.00 - ฿4.98: สเปรด 0.02
  - ราคา ฿5.00 - ฿9.95: สเปรด 0.05
  - ราคา ฿10.00 - ฿24.90: สเปรด 0.10 (ราคา 16.05 จึงผิดกฎ ต้องเป็น 16.00 หรือ 16.10)
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ติดตั้ง Pre-Trade Risk Validator ใน [app/services/validator.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/validator.py) ให้ดักจับและคำนวณ Tick Size ก่อนส่งคำสั่งไปยังเบราว์เซอร์ หากผิดให้ปฏิเสธทันทีพร้อมแจ้งราคาที่ถูกต้อง

---

### 📌 Incident `C2W-RCA-004`: TFEX Radio State Clearing on Account Switch
* **วันและเวลา:** 2026-09-28 05:00 น.
* **อาการ (Symptom):**  
  เมื่อสลับบัญชีจาก Equity (`CW32_E_`) ไปเป็น Derivatives (`CW32_D_`) ฟอร์มส่งคำสั่งไม่ยอมเลือก Long/Short
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  Settrade Streaming ทำการ Reset สถานะของ Radio Form ทุกครั้งที่มีการสลับ Context ของบัญชี
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  ใน [app/browser/click2win_driver.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/click2win_driver.py):
  หลังจากคลิกสลับบัญชี ต้องสั่งเลือกข้างอย่างชัดเจนเสมอ:
  - `Long`: คลิก `label:has-text('Long'), input[value='B']`
  - `Short`: คลิก `label:has-text('Short'), input[value='S']`
  - เลือกประเภท Position: `Open` หรือ `Close` จาก Dropdown ด้านข้าง

---

### 📌 Incident `C2W-RCA-005`: Settrade Streaming Favourite Polling Sentinel
* **วันและเวลา:** 2026-09-28 06:15 น.
* **อาการ (Symptom):**  
  Settrade Open API v2 SDK ตอบกลับด้วยรหัส `403 Forbidden` ทำให้ไม่สามารถดึงข้อมูลราคาตลาด Bid/Offer ได้
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  Developer App ของ Settrade Open API ขาดกิจกรรมเป็นเวลานานจนถูกระงับสิทธิ์ชั่วคราว
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**  
  พักการใช้งาน Open API ชั่วคราว และเปลี่ยนมาใช้ฟังก์ชัน **Favourite Watchlist บน Settrade Streaming Click2Win** แทน:
  - ใช้ `Favourite 1` สำหรับ Equity (`BDMS`, `CPALL`)
  - ใช้ `Favourite 2` สำหรับ TFEX (`SPALIU26`)
  - สร้าง Background Worker ([app/monitoring/click2win_polling_worker.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/monitoring/click2win_polling_worker.py)) ดึงราคาแบบสลับรอบ (Odd=Fav 1, Even=Fav 2) ส่งเข้า `AlertEngine` และสตรีม SSE ขึ้นหน้าจอ Cockpit ได้อย่างเสถียร 100%
  - **UPDATE (2026-10-06):** worker นี้, `AlertEngine` และทั้งโฟลเดอร์ `app/monitoring/` ถูก **ลบออกทั้งหมด** พร้อมการถอดฟีเจอร์ Pillar 2 "Monitor & Alert" — การ polling Favourite และ SSE market/alert stream ถูกยกเลิกแล้ว
  - **หมายเหตุ:** SSE bus ยังคงอยู่ที่ `app/core/sse_broadcaster.py` และให้บริการผ่าน `GET /api/v1/cockpit/stream` สำหรับเหตุการณ์ HITL order pending / action-exit เท่านั้น

---

### 📌 Incident `C2W-RCA-006`: Annealing Tests Overwriting Tracked Runbooks (F-11)

* **วันและเวลา:** 2026-10-15 22:47 น.
* **อาการ (Symptom):**  
  หลังรัน `scripts/verify_changes.py --full` ทุกครั้ง `git status` แสดง 2 runbook ที่ git track ถูกแก้:
  `learned_workflows/click2win/click2win_order_submit.md` (`Recorded At` เปลี่ยนเป็นเวลาที่รัน + ต่อท้ายข้อความ
  `(Self-Annealed: …)` เพิ่มอีก 1 ชุด → สะสมถึง ×75) และ `learned_workflows/shared/test_anneal_wf.md`
  (เปลี่ยน `Recorded At` อย่างเดียว) → ต้อง `git checkout --` 2 ไฟล์นี้ทุกครั้งเป็น workaround
* **การสืบหาต้นตอ (Root Cause Analysis):**  
  `WorkflowEngine.save_workflow_spec()` / `update_workflow_step()` หา path ปลายทางจาก constant ระดับโมดูล
  `workflow_engine.WORKFLOWS_DIR` ซึ่งชี้ที่ repo `learned_workflows/` จริง (ไม่มีการแยก read/write) ทำให้:
  - `tests/test_click2win_driver.py::test_workflow_engine_self_annealing` — parse runbook จริง แล้วเรียก
    `update_workflow_step("click2win_order_submit", step_num=6, …)` → เขียนทับ runbook จริง (F-11 ×75)
  - `tests/test_escalation_and_annealing.py::test_workflow_engine_4step_self_annealing_and_escalation` —
    รับ `tmp_path` มาแล้ว **ไม่ได้ใช้เลย** → `save_workflow_spec("test_anneal_wf", …)` เขียน
    `learned_workflows/shared/test_anneal_wf.md` ใหม่ทุก run
  - (กลไกเดียวกัน) `tests/test_mcp_and_workflow_engine.py::test_mcp_handle_tool_call_buffered_recording`
    เขียน `learned_workflows/shared/tmp_test_workflow.md` ลง tree จริงแล้วลบท้ายเทสต์ (leak ถ้าเทสต์ fail กลางทาง)
* **ขอบเขตที่พบเพิ่ม (Edge cases):**
  - `app/services/self_annealing_engine.py` มี `WORKFLOWS_DIR` ของตัวเอง แต่ **อ่านเท่านั้น** (`rglob`/`read_text`)
    → ไม่ใช่ตัวเขียนไฟล์ (ไม่ต้อง patch)
  - เทสต์ที่ **อ่าน** runbook จริงต้องยังทำงานได้ (assert ว่า `click2win_order_submit` มี ≥6 steps)
    → sandbox ต้องเป็น **สำเนา** ของ tree ไม่ใช่โฟลเดอร์ว่าง
  - `workflow_list` ต้องเห็นไฟล์ที่เพิ่งเซฟในเทสต์ → ต้อง patch constant ที่ใช้ร่วมกัน ไม่ใช่ patch แค่ instance
* **วิธีแก้ปัญหาที่ผ่านการพิสูจน์แล้ว (Proven Working Solution):**
  1. `tests/conftest.py` — autouse fixture `isolate_learned_workflow_writes`: `shutil.copytree()` tree จริงไปที่
     `tmp_path/learned_workflows` แล้ว `monkeypatch.setattr(workflow_engine, "WORKFLOWS_DIR", str(sandbox))`
     → อ่าน runbook จริงได้ แต่ทุก write ลง tmp
  2. `tests/conftest.py` — session-scoped autouse fixture `guard_tracked_runbooks`: sha256 ทุกไฟล์ใต้
     `learned_workflows/` เทียบก่อน/หลัง session → fail ถ้ามี write หลุด (กันเทสต์ใหม่ในอนาคต)
  3. Regression test `tests/test_annealing_runbook_isolation.py` — รัน save + update + execute_workflow แล้ว
     assert hash ของ tracked runbooks ไม่เปลี่ยน และ write target อยู่ใต้ sandbox
  4. `scripts/verify_changes.py` — `conftest.py` ไม่ถูกใช้เป็น test target (เป็น fixture module) + mapping
     `tests/conftest.py` → 4 test files ที่เกี่ยวข้อง
* **หลักฐาน (Evidence):**
  - baseline (ก่อนแก้): รัน 3 ไฟล์เทสต์ที่เกี่ยวข้อง → `learned_workflows/click2win/click2win_order_submit.md`
    ถูกแก้ทันที (reproduce bug ได้)
  - mutation check: ปิด fixture → `tests/test_annealing_runbook_isolation.py` fail 2 เทสต์ และ runbook ทั้ง 2
    ถูกเขียนจริง (เทสต์ไม่ vacuous)
  - `.venv/bin/python scripts/verify_changes.py tests/conftest.py tests/test_annealing_runbook_isolation.py`
    → PASS (17 tests) และ `git status --porcelain` ว่างหลังรัน
* **⚠️ ความเสียหายที่ยังค้างอยู่ (Open item — ต้องใช้ live DOM/HITL):**
  เนื้อหาที่ commit ไปแล้ว (`9ed1f5a`) ถูก pollute: `## Description` ของ `click2win_order_submit.md` ถูกแทนด้วย
  `Self-annealed on …`, step 2 selector = `button.btn-buy-tailscale-test` (ค่าจาก MCP live),
  step 6 selector = `button.btn-submit-click2win-new` (ค่าจากเทสต์) — **ห้ามเดา selector กลับด้วย assumption**
  ต้องยืนยันจากจอจริงแล้วแก้ในงานแยก (Zero-Contradiction: runbook ต้องไม่ขัดกับ DOM จริง)
  `learned_workflows/shared/test_anneal_wf.md` เป็น test artifact ล้วน (ยัง track ใน git) → รอการตัดสินใจย้าย/ลบ

---

## 🔒 กฎเหล็กประจำตัว Click2Win (Strict Constraints & Guardrails)
1. **การแบ่งแยกประเภทสินทรัพย์ (Asset Segregation)**:
   - Equity (`CW32_E_`): อนุญาตเฉพาะ `BUY`, `SELL` (ห้ามส่ง `LONG`/`SHORT`)
   - TFEX (`CW32_D_`): อนุญาตเฉพาะ `LONG`, `SHORT` (ห้ามส่ง `BUY`/`SELL`)
2. **การยืนยันสถานะ Match 3 ชั้น (Triple-Check)**:
   - ตรวจสถานะ 'M' ในตาราง View Order
   - ตรวจความเปลี่ยนแปลงของจำนวนหุ้นในตาราง ReactVirtualized ใน Portfolio
   - ยิงแจ้งเตือนผ่าน KDE Connect ไปยัง Xiaomi Mi 10T
