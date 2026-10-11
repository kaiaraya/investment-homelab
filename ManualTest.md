# 📖 คู่มือการเปิด-ปิด Service และแนวทางการทดสอบระบบแบบ Manual
## (Investment Homelab Gateway - Manual Testing Playbook)

เอกสารนี้รวบรวมคำสั่งและขั้นตอนสำหรับการ **เปิด-ปิด Service** ตลอดจนวิธีการ **ทดสอบระบบด้วยตนเอง (Manual Testing)** ทั้งผ่าน Web Console, CLI Scripts, LINE Chat, และ REST API

---

## 📌 สารบัญ (Table of Contents)
1. [โครงสร้าง Service ในระบบ](#1-โครงสร้าง-service-ในระบบ)
2. [วิธีการ "เปิด" Service (Start Commands)](#2-วิธีการ-เปิด-service-start-commands)
3. [วิธีการ "ปิด" Service (Stop Commands)](#3-วิธีการ-ปิด-service-stop-commands)
4. [คู่มือการทดสอบแบบ Manual (4 ช่องทาง)](#4-คู่มือการทดสอบแบบ-manual-4-ช่องทาง)
   - [ช่องทางที่ 1: ผ่าน Web Test Console (แนะนำ - 1-Click UI)](#ช่องทางที่-1-ผ่าน-web-test-console-แนะนำ-1-click-ui)
   - [ช่องทางที่ 2: ผ่าน CLI Scripts ใน Terminal](#ช่องทางที่-2-ผ่าน-cli-scripts-ใน-terminal)
   - [ช่องทางที่ 3: ทดสอบโต้ตอบผ่าน LINE Chat (HITL)](#ช่องทางที่-3-ทดสอบโต้ตอบผ่าน-line-chat-hitl)
   - [ช่องทางที่ 4: ทดสอบผ่าน Swagger REST API Docs](#ช่องทางที่-4-ทดสอบผ่าน-swagger-rest-api-docs)
5. [การตรวจสอบความปลอดภัย (Zero Financial Risk Guard)](#5-การตรวจสอบความปลอดภัย-zero-financial-risk-guard)
6. [การดู Logs และการแก้ปัญหาเบื้องต้น (Troubleshooting)](#6-การดู-logs-และการแก้ปัญหาเบื้องต้น-troubleshooting)

---

## 1. โครงสร้าง Service ในระบบ

เมื่อเปิดตัว Gateway หลัก (FastAPI บน Uvicorn) ระบบจะเริ่มต้น 3 การทำงานหลักพร้อมกันในโปรเซสเดียว:
* **FastAPI Backend & Webhook Server**: รองรับ Webhook จาก LINE, เปิดหน้า Web Test Console (`/console`), และ API Docs (`/docs`)
* **Session Sentinel (Heartbeat Loop)**: ลูปตรวจสอบความมีชีวิตของ Session TradeMan ทุก 3 นาที (180 วินาที)
* **Phase 3 Scheduler**: ตัวคุมจังหวะเวลาอัตโนมัติตามรอบตลาด (10:15, 11:00, 12:00, 15:30, 16:35)

---

## 2. วิธีการ "เปิด" Service (Start Commands)

### แบบที่ 1: รันผ่าน Terminal ปกติ (แนะนำสำหรับการทดสอบ Manual เพื่อดู Log สด)
เปิด Terminal ที่โฟลเดอร์โปรเจกต์:
```bash
cd /home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
* **URL เข้าใช้งาน**:
  * Web Test Console: [http://localhost:8000/console](http://localhost:8000/console)
  * Swagger API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
  * ตรวจสอบ Health: [http://localhost:8000/health](http://localhost:8000/health)

---

### แบบที่ 2: รันเป็น Background Service (ไม่ล็อกหน้าต่าง Terminal)
```bash
cd /home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > homelab.log 2>&1 &
```
* **ดู Log แบบสด**:
  ```bash
  tail -f homelab.log
  ```

---

## 3. วิธีการ "ปิด" Service (Stop Commands)

### กรณีรันแบบที่ 1 (Terminal ปกติ):
* ไปที่หน้าต่าง Terminal นั้นแล้วกด: **`Ctrl + C`**
* ระบบจะสั่ง Graceful Shutdown อัตโนมัติ:
  1. หยุด Scheduler (`phase3_scheduler.stop()`)
  2. หยุด Sentinel Heartbeat (`session_sentinel.stop()`)
  3. ปิด Browser Driver สะอาดเรียบร้อย (`auth_driver.close()`)

---

### กรณีรันแบบที่ 2 (Background) หรือต้องการ Force Stop ทั้งหมด:
ใช้คำสั่งผ่าน Terminal:
```bash
# 1. ปิด Uvicorn Web Server
pkill -f "uvicorn app.main:app"

# 2. ปิด Chrome Browser ที่ระบบเปิดค้างไว้ (กรณีต้องการปิดหน้าจอเบราว์เซอร์ด้วย)
pkill -f "chrome.*--remote-debugging-port"
```

* **คำสั่งตรวจสอบว่ายังมีโปรเซสค้างอยู่หรือไม่**:
```bash
pgrep -fl uvicorn
pgrep -fl chrome
```

---

## 4. คู่มือการทดสอบแบบ Manual (4 ช่องทาง)

### ช่องทางที่ 1: ผ่าน Web Test Console (แนะนำ - 1-Click UI) 🌟
เปิดเบราว์เซอร์ไปที่: **[http://localhost:8000/console](http://localhost:8000/console)**

หน้าจอนี้ออกแบบมาเพื่อทดสอบฟังก์ชันสำคัญด้วยการกดปุ่มเพียงคลิกเดียว:
1. **Live On-Demand Probes (กวาดข้อมูลสดจากหน้าเว็บ TradeMan จริง - Zero Risk)**:
   - `[Scrape Live Portfolio]` ➜ ดึง Symbol, Vol, Cost, Market Price, Unrealized PnL จากพอร์ตจริง
   - `[Scrape Account Summary]` ➜ ดึงวงเงินคงเหลือ, Cash Balance, และ Excess Equity
   - `[Scrape SBL Stock]` ➜ ค้นหาโควตายืมหุ้น SBL คงเหลือ (เช่น หุ้น CPALL)
   - `[Scrape Unmatched Orders]` ➜ กวาดดูรายการคำสั่งซื้อขายที่ยังค้างอยู่ในตาราง Order Status
2. **Manual Triggers (บังคับยิงแจ้งเตือนเข้า LINE ทันที ไม่ต้องรอตามเวลาจริง)**:
   - `[Trigger 10:15 Overview]` ➜ ยิงสรุปพอร์ตและปุ่มตั้ง TP/SL เข้า LINE ทันที
   - `[Trigger 11:00 Negotiation]` ➜ ยิงสรุปคำสั่งต่อราคาเข้า LINE ทันที
   - `[Trigger 16:35 EOD Report]` ➜ ยิงสรุปผลการเทรดสิ้นวัน (EOD) เข้า LINE ทันที
3. **Time Warp Simulator (ทดสอบระบบเร่งเวลา)**:
   - เลือกทดสอบสถานการณ์ Scenario 1 ถึง 5 หรือเร่งเวลาตลาดได้ทันที

---

### ช่องทางที่ 2: ผ่าน CLI Scripts ใน Terminal

รันสคริปต์แยกตามจุดประสงค์การทดสอบ:

#### 1. ทดสอบ Login เข้าหน้า TradeMan จริง (Headed Mode ให้เห็นเบราว์เซอร์บนจอ):
```bash
.venv/bin/python scripts/run_phase2_login.py
```
* ระบบจะเปิด Google Chrome ขึ้นมาบนหน้าจอ กรอก Username / Password และรอรับ OTP เพื่อล็อกอินเข้า TradeMan
* มีระบบตรวจจับ Checkbox *"ไม่ต้องแสดงอีก"* ของ Popup ข่าวสารโดยอัตโนมัติ

#### 2. ทดสอบกวาดข้อมูลสดบนหน้าจอ TradeMan จริง (Zero Risk Read-Only DOM):
```bash
.venv/bin/python scripts/run_live_scraping_test.py
```
* เชื่อมต่อแท็บ TradeMan เดิมที่เปิดอยู่แล้ว
* ดึงข้อมูลพอร์ต, บัญชีเงินสด, สต็อกหุ้นยืม SBL, และคำสั่งค้างบนกระดาน โดยไม่มีการคลิกส่งคำสั่งเทรดใดๆ

#### 3. ทดสอบจำลองตลาดเร่งเวลา (Time Warp Engine - 5 สถานการณ์):
```bash
# รัน Scenario 1 (Normal Execution & Matched)
.venv/bin/python scripts/run_time_warp_sim.py --scenario 1

# รัน Scenario 2 (Take Profit / Stop Loss Triggers)
.venv/bin/python scripts/run_time_warp_sim.py --scenario 2

# รันครบทุก Scenario (1 - 5)
.venv/bin/python scripts/run_time_warp_sim.py --scenario all
```

#### 4. ทดสอบความพร้อมครบวงจรในโหมด DRY-RUN:
```bash
.venv/bin/python scripts/run_phase3_dryrun.py
```

---

### ช่องทางที่ 3: ทดสอบโต้ตอบผ่าน LINE Chat (HITL)

เมื่อเปิด Gateway ไว้ คุณสามารถใช้สมาร์ทโฟนเปิดห้องแชท LINE เพื่อทดสอบความสามารถเหล่านี้ได้ทันที:

1. **เรียกดู Action Center รวมคำสั่งรออนุมัติ**:
   - พิมพ์คำว่า: **`action`** หรือ **`รออนุมัติ`** หรือ **`pending`**
   - ระบบจะตอบกลับด้วย **Action Center Flex Card**:
     - แสดงรายการหุ้นที่แตะจุด TP / SL หรือสัญญาณผิดปกติ
     - มีปุ่ม **`[✅ อนุมัติทั้งหมด]`** และ **`[❌ ยกเลิกทั้งหมด]`**
     - มีปุ่มกดอนุมัติหรือยกเลิกแยกรายตัว
2. **เรียกดูข้อมูลดัชนีตลาด SET สด**:
   - พิมพ์คำว่า: **`set`** หรือ **`ตลาด`** หรือ **`ดัชนี`**
   - ระบบจะตอบกลับข้อความดัชนีล่าสุด: Current SET, %Change, High, Low, Volume, Value
3. **ตรวจสอบตาราง 8 ช่วงเวลาตลาดและจุดเวลาสุ่มวันนี้**:
   - พิมพ์คำว่า: **`schedule`** หรือ **`รอบเวลา`** หรือ **`ตารางเวลา`**
   - ระบบจะแจงตาราง 8 ช่วงเวลา พร้อมแสดง 3 จุดเวลาสุ่มรอบเช้าและรอบบ่ายของวันนี้
4. **ส่งรหัส 2FA SMS OTP ผ่าน LINE**:
   - เมื่อหน้าเว็บถาม OTP คุณสามารถพิมพ์รหัส **6 หลัก** (เช่น `456789`) ส่งเข้าแชท LINE
   - Gateway จะจับคู่กับ Ref Code และนำไปกรอกลงหน้าจอเว็บให้โดยอัตโนมัติ
5. **ตรวจสอบสถานะบอท**:
   - พิมพ์คำว่า: **`status`**

---

### ช่องทางที่ 4: ทดสอบผ่าน Swagger REST API Docs
เปิดเบราว์เซอร์ไปที่: **[http://localhost:8000/docs](http://localhost:8000/docs)**
- มี UI แสดง Endpoint ทั้งหมดของระบบ
- สามารถกดปุ่ม **`Try it out`** เพื่อทดสอบยิง Request พร้อมดู Response ได้ทันที
- ตัวอย่างคำสั่ง cURL ผ่าน Terminal:
  ```bash
  # ตรวจสอบ Health
  curl http://localhost:8000/health

  # ตรวจสอบรอบเวลาและจุดสุ่มวันนี้
  curl http://localhost:8000/api/v1/simulation/schedule

  # สั่งกวาดข้อมูลดัชนี SET สดพร้อมส่งเข้า LINE
  curl -X POST "http://localhost:8000/api/v1/simulation/live/probe/set-summary?period_label=LIVE"

  # สั่งรันรอบอัตโนมัติ (Alerts -> Trades -> Nego) ทันที
  curl -X POST "http://localhost:8000/api/v1/simulation/live/trigger/random-point?round_time=MANUAL"
  ```

---

## 5. การตรวจสอบความปลอดภัย (Zero Financial Risk Guard)

ระบบถูกออกแบบโดยยึดหลัก **Zero Financial Risk** ในระหว่างการทดสอบ:
1. **`DRY_RUN_MODE=true` (ค่าตั้งต้น)**:
   - ระบบจะสลับแท็บ, กรอกชื่อหุ้น, ระบุจำนวนหุ้น, ระบุราคา, และตรวจจับหน้าจอเพื่อความถูกต้อง
   - **ระบบจะหยุดก่อนกดส่ง PIN เสมอ** ไม่มีการส่งคำสั่งเทรดจริงไปที่กระดาน SET
2. **Persistent Single-Tab Session**:
   - การเปิด-ปิด หรือรันสคริปต์ทดสอบหลายรอบ จะนำแท็บ TradeMan เดิมมาใช้ต่อเสมอ
   - **ไม่ทำให้ SMS OTP เด้งเข้ามือถือซ้ำซาก** (ป้องกันปัญหาขอ OTP พร่ำเพรื่อ)
3. **Live Probes เป็นแบบ Read-Only DOM**:
   - โมดูลกวาดพอร์ต, เช็คเงินสด, เช็ค SBL, และเช็ค Order Status เป็นการอ่าน DOM ล้วนๆ ไม่มีการแตะต้องเงินในบัญชี

---

## 6. การดู Logs และการแก้ปัญหาเบื้องต้น (Troubleshooting)

### ตรวจสอบการทำงานของระบบ:
```bash
# ดู log การทำงานล่าสุดแบบ real-time
tail -n 100 -f homelab.log
```

### ปัญหาที่พบบ่อยและวิธีแก้ไข:

| อาการที่พบ | สาเหตุ | วิธีแก้ไข |
| :--- | :--- | :--- |
| `Port 8000 is already in use` | มี instance ของ uvicorn หรือ service อื่นรันค้างอยู่ | รัน `pkill -f "uvicorn app.main:app"` แล้วลองเปิดใหม่อีกครั้ง |
| `Browser is already open` | เบราว์เซอร์เดิมเปิดค้างไว้จากรอบก่อน | ปล่อยให้ระบบใช้ Session เดิมต่อได้เลย หรือรัน `pkill -f chrome` หากต้องการเริ่มเปิดหน้าต่างใหม่ |
| LINE ไม่ตอบกลับข้อความ | Webhook URL บน LINE Developers ยังไม่ได้ชี้มาที่เซิร์ฟเวอร์ | ตรวจสอบ ngrok/cloudflare tunnel หรือทดสอบผ่านหน้า Web Console (`/console`) แทน |
| Checkbox "ไม่ต้องแสดงอีก" ไม่ถูกติ๊ก | Popup โหลดช้าหรือใช้ id ที่แตกต่าง | ระบบมี Rule Selector สำรองและ fallback อัตโนมัติ สามารถดู log `popup_manager` เพื่อตรวจจับ modal ได้ |

---

## 7. Interactive Playwright Inspection & "Grill-Me" Feedback Loop 🕵️‍♂️

เมื่อโปรแกรมทดสอบทำข้อผิดพลาดบ่อยครั้ง (เช่น หา Selector ไม่เจอ, Popup โผล่มาขัดจังหวะ, หรือหน้าเว็บโหลดช้า) คุณสามารถเปิดระบบ **Direct Human-in-the-Loop Feedback Loop** คล้ายกับคำสั่ง `/grill-me` เพื่อหยุดการทำงานเฉพาะจุดและตรวจสอบได้ทันที:

### 7.1 วิธีเปิดใช้งานผ่าน Grill-Me Runner CLI
เราได้เตรียมสคริปต์ [playwright_grill_runner.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/playwright_grill_runner.py) ไว้ให้ทดสอบทั้งหน้า Web Console และ TradeMan:

```bash
# 1. รันแบบ Step-by-Step (ถามคุณก่อนทำทุก Action ให้ feedback ได้ทันที)
.venv/bin/python scripts/playwright_grill_runner.py --target console --mode step

# 2. รันแบบ On-Failure (ปล่อยให้รันปกติ แต่ถ้ามี Error หรือ Selector พลาด จะหยุดและ Grill ทันที!)
.venv/bin/python scripts/playwright_grill_runner.py --target console --mode on-failure

# 3. ทดสอบหน้า TradeMan สดแบบ Read-Only DOM (Zero Risk)
.venv/bin/python scripts/playwright_grill_runner.py --target trademan --mode step

# 4. ทดสอบ Playground กับ URL ใดก็ได้ พร้อมเปิด DevTools อัตโนมัติ
.venv/bin/python scripts/playwright_grill_runner.py --target inspect --url http://localhost:8000/console --devtools
```

#### เมนูคำสั่งใน Interactive Grill Console:
* `[Enter]` หรือ `[c]`: ทำงานต่อไปตามปกติ (Continue)
* `[p]`: เรียกเปิด **Playwright Inspector GUI (`page.pause()`)** บนหน้าจอทันที สามารถคลิก Explore ชี้หา Selector ในหน้าเว็บได้แบบสดๆ
* `[i]`: **Probe / Test Locator**: พิมพ์ Selector ใดๆ (CSS / XPath / `text=...`) เพื่อตรวจนับจำนวน element และไฮไลท์สีเขียวเรืองแสงบนหน้าต่างเบราว์เซอร์จริง
* `[e]`: **Eval JavaScript**: รันโค้ด JS ในคอนโซลของหน้าเว็บสดๆ เช่น `document.querySelector('button').innerText`
* `[s]`: บันทึกภาพหน้าจอ Screenshot + Dump HTML DOM เก็บไว้ที่ `data/diagnostics/` ทันที
* `[u]`: **Update & Retry**: กรอก Selector ตัวใหม่หน้างาน แล้วสั่งให้โปรแกรมลองใหม่อีกครั้งทันทีโดยไม่ต้องเริ่มรันสคริปต์ใหม่
* `[r]`: ลอง Action เดิมใหม่อีกครั้ง (Retry)
* `[k]`: ข้าม Action นี้ (Skip)
* `[q]`: ยกเลิกและปิดเบราว์เซอร์อย่างปลอดภัย (Quit)

---

### 7.2 การใช้ Playwright Native Inspection (`PWDEBUG=1`)
คุณสามารถรันสคริปต์หรือ Pytest ใดๆ ร่วมกับตัวแปรสภาพแวดล้อม Playwright ดังนี้:

```bash
# เปิด Playwright Inspector ควบคู่กับ Pytest
PWDEBUG=1 .venv/bin/pytest tests/test_browser_driver.py -s

# เปิด Playwright Inspector กับสคริปต์ทดสอบที่มีอยู่เดิม
PWDEBUG=1 .venv/bin/python scripts/browser_test_console.py

# ใช้ Playwright Codegen เพื่อคลิกสำรวจและ Generate Selector สดๆ
.venv/bin/playwright codegen http://localhost:8000/console
```

---
*เอกสารนี้สร้างขึ้นสำหรับระบบ Investment Homelab Gateway - พร้อมสำหรับการทดสอบ Manual ทุกรูปแบบ*
