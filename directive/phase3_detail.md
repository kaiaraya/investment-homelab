# Master Directive: 6-Pillars Modular Architecture & Hybrid Execution Gateway
**Investment Homelab: Hybrid High-Frequency Monitor & Runbook-Driven Browser Automation**

เอกสารนี้คือ **แม่บทข้อกำหนดสถาปัตยกรรมและการทำงาน (Master Directive - Single Source of Truth)** ของระบบ Investment Homelab ซึ่งผ่านการสังเคราะห์และปรับปรุงตามผลสรุปการออกแบบ `/grill-me` เพื่อให้ระบบมีความยืดหยุ่น รองรับโบรกเกอร์ที่หลากหลาย มีความเสถียรสูง และแยกสถาปัตยกรรมออกเป็นชั้นๆ (Layered Architecture) อย่างชัดเจน

---

## 🏛️ 1. ปรัชญาและโครงสร้างสถาปัตยกรรมระบบ (Architectural Philosophy)

ระบบถูกออกแบบภายใต้หลักการ 4 ประการ:

1. **สถาปัตยกรรมแบบผสมผสาน (Hybrid Division of Labor):**
   - **Settrade Open API (v2 SDK - MQTT WebSocket & REST)**: รับหน้าที่เฉพาะ **Monitor & Alert (การเฝ้าราคาความเร็วสูงระดับมิลลิวินาที)** ติดตาม Ticks, Bid/Offer แบบเรียลไทม์ โดยใช้ทรัพยากรต่ำมาก (~30MB RAM) และไม่รบกวนหน้าจอเบราว์เซอร์
   - **Playwright via Learned Workflows (`learned_workflows/*.md`)**: รับหน้าที่ **ส่วนงานปฏิบัติการของโบรกเกอร์ทั้งหมด** (การล็อกอิน, การสลับพอร์ต, การซิงก์พอร์ต, การยืม-คืนหุ้น SBL, และการส่งคำสั่งซื้อขาย) เพื่อแก้ปัญหาโบรกเกอร์ทั่วไปที่ไม่มี Open API รองรับ โดยควบคุมผ่าน Runbook ที่อ่านง่าย แก้ไขได้ และมีระบบ Self-Annealing
2. **การแยกหน้าที่ระหว่าง Engine และ Orchestrator (Decoupled Layering):**
   - Homelab Gateway ไม่มีการฝังตารางเวลาเทรดตายตัว (เช่น 10:15, 11:00, 15:30) หรือ Cron Loop ภายในตัวเซิร์ฟเวอร์
   - Homelab ทำหน้าที่เป็น **Pure Capability & Execution Engine** เปิดให้บริการเครื่องมือผ่านโปรโตคอล **Remote MCP (Model Context Protocol via SSE)** บนเครือข่าย Tailscale
   - การตัดสินใจเชิงกลยุทธ์, จังหวะเวลา (Timetable), หรือการกระจายงานรอบวัน จะถูกสั่งการมาจากภายนอกโดย **External AI Agent หรือ Google Apps Script** ยิงคำสั่งเข้ามาทาง MCP Tools ตามต้องการ
3. **การทดสอบบนบัญชีจำลองจริง (Virtual Sandbox Execution - ปลดล็อก DRY_RUN):**
   - ยกเลิกกลไก `DRY_RUN_MODE` ที่ต้องหยุดก่อนกรอก PIN
   - ระบบเชื่อมต่อกับบัญชีจำลอง (Click2Win / Settrade Sandbox) ที่มีวงเงินจำลอง ทำให้สามารถส่งคำสั่งและกดยืนยัน (Submit & Confirm) ได้แบบ End-to-End ในสภาพแวดล้อมตลาดเสมือน เพื่อทดสอบวงจรการจับคู่คำสั่งจริงโดยไม่มีความเสี่ยงทางการเงิน
4. **ความปลอดภัยระดับโครงสร้าง (Pre-Trade Guardrails & Instant Notifications):**
   - มี Guardrails สกัดกั้นคำสั่งผิดพลาดก่อนส่งออกเสมอ: ตรวจสอบ Board Lot (`Volume % 100 == 0`), ตรวจสอบวงเงินเพดานสูงสุด (Max Value Limit), ตรวจสอบประเภทบัญชี (Equity vs Derivatives vs Margin)
   - ทุกการกระทำและผลลัพธ์คำสั่งจะถูกส่งสรุปและแจ้งเตือนเข้า LINE Messaging API ทันที

---

## 🧩 2. แผนภาพสถาปัตยกรรมรวม (System Architecture Overview)

```mermaid
graph TD
    subgraph External_Orchestration_Layer ["1. External Orchestration & Tactical Layer (ผู้สั่งการภายนอก)"]
        ExternalAgent["🤖 External AI Agent (Antigravity IDE / Cline)"]
        AppsScript["⏰ Google Apps Script / External Cron"]
        UserLINE["📱 User LINE Commands / Webhooks"]
    end

    subgraph Tailscale_Network ["Tailscale Encrypted Mesh (100.88.217.33)"]
        SSEBridge["Remote MCP Gateway (/sse)"]
    end

    subgraph Homelab_Capability_Engine ["2. Homelab Modular Gateway (Core 6-Pillars Engine)"]
        MCPRouter["app/mcp/server.py (FastMCP Router)"]
        
        P1["🔐 Pillar 1: Session Sentinel<br/>(Login, OTP, Session Health)"]
### 🏛️ เสาหลักที่ 2: Account & Portfolio (`pillar2_portfolio.py`)
* **หน้าที่**: ศูนย์กลางข้อมูลบัญชีและพอร์ตโฟลิโอของทุกโบรกเกอร์เป็นมาตรฐานเดียว (Unified Snapshot)
* **กฎเหล็ก (Business Rules)**:
  - **Account Capability Matrix**: สลับ/ตรวจสอบสิทธิ์บัญชีตามประเภทสินทรัพย์ (EQUITY / DERIVATIVES / CASH / MARGIN)
  - **Single-Account Clamp**: Liberator มีบัญชี CASH เดียว (คำขอ MARGIN/DERIVATIVES จะถูก clamp พร้อมแจ้งเตือนตามจริง)
* **เครื่องมือ MCP**:
  - `portfolio_list_accounts(platform)`
  - `switch_account(platform, account_type)`
  - `portfolio_get_balances(platform, account_type)`
  - `portfolio_holdings(platform, account_type)`
  - `current_open_orders(platform, account_type)`
  - `portfolio_sync_db()`
* **NOTE (2026-10-06)**: ฟีเจอร์ "Monitor & Alert" (intraday monitor, alert rules, watchlist, `app/monitoring/`) ถูก **ลบออกทั้งหมด** แล้ว

### 🏛️ Pillar 3: Trade Execution Engine (`pillar3_trade.py`)
* **วัตถุประสงค์**: ดำเนินการส่งคำสั่งซื้อขายจริงบนกระดานจำลอง (Sandbox) ผ่าน **Playwright Learned Workflows**
* **หน้าที่หลัก**:
  - รันคำสั่งตามสเปก Markdown Runbook เช่น [learned_workflows/click2win_order_submit.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/click2win_order_submit.md) หรือ TradeMan Long/Short
  - ส่งคำสั่งซื้อขายแบบ End-to-End: กรอก Symbol, Volume, Price, PIN และ **กดปุ่ม Submit/Confirm จริง** บนบัญชีเสมือน
  - **Pre-trade Guardrails**:
    - ป้องกันเศษหุ้น (Odd-lot): ตรวจสอบ `Volume % 100 == 0` เสมอ
    - ป้องกันความเสียหายจากวงเงินเกิน: สกัดกั้นหาก Order Value เกินเพดานที่กำหนด
    - TypeSafe Multi-Account Guard: แยกเส้นทางชัดเจนระหว่างบัญชีหุ้น (Cash/Cash Balance) และบัญชีอนุพันธ์ (TFEX)
  - แจ้งผลการส่งคำสั่งและ Order ID ที่ได้รับกลับไปยังผู้สั่งและ LINE ทันที

### 🏛️ Pillar 4: SBL Intelligence Center (`pillar4_sbl.py`)
* **วัตถุประสงค์**: บริหารจัดการการยืมและคืนหุ้นสำหรับกลยุทธ์ Short Selling ผ่านหน้าเว็บโบรกเกอร์ (Krungsri TradeMan)
* **หน้าที่หลัก**:
  - ตรวจสอบโควตาคลังหุ้นยืม (`sbl_get_inventory`): กวาดหน้าจอคลัง SBL เพื่อเช็คว่ามีหุ้นให้ยืมหรือไม่ ก่อนส่งสัญญาณ Short
  - ขอยืมหุ้นอัตโนมัติ (`sbl_borrow_stock`): ดำเนินการกดยืมหุ้น บันทึก Broker Transaction No., วันที่ยืม, และคิดดอกเบี้ยยืม (5.5%/ปี)
  - คืนหุ้นอัตโนมัติ (`sbl_return_stock`): จับคู่ Lot ที่ยืมมา และสั่งคืนหุ้นเข้าคลัง SBL ทันทีหลังปิดสถานะ Cover เรียบร้อย
  - ตรวจสอบความเสี่ยงสิทธิประโยชน์ (`sbl_check_corporate_actions`): แจ้งเตือนหุ้นยืมที่ใกล้ขึ้นเครื่องหมาย XD/XR เพื่อป้องกันค่าใช้จ่ายชดเชยเงินปันผล

### 🏛️ Pillar 5: Portfolio Intelligence & Risk Center (`pillar5_portfolio.py`)
* **วัตถุประสงค์**: ศูนย์กลางตรวจสอบสถานะพอร์ต ทรัพย์สินคงเหลือ และความเสี่ยง
* **หน้าที่หลัก**:
  - สลับบัญชีเทรด (`portfolio_switch_account`): เปลี่ยนแท็บระหว่าง Equity Cash Balance, Credit Balance (Margin), และ Derivatives
  - กวาดข้อมูลพอร์ต (`portfolio_get_holdings`): ดึง Ticker, Volume, Avg Cost, Market Price, Unrealized PnL ด้วย Playwright
  - ตรวจสอบวงเงิน (`portfolio_get_balances`): ดึง Cash Balance, Line Available, Excess Equity (EE)
  - ตรวจสอบคำสั่งค้าง (`portfolio_get_open_orders`): ดึงรายการคำสั่งสถานะ `Queuing`, `Pending`, `Unmatched`
  - บันทึกลงฐานข้อมูล SQLite (`portfolio_sync_db`): ซิงก์ข้อมูลทั้งหมดลงตาราง `positions` และ `orders`

### 🏛️ Pillar 6: Tactical Strategy Tools (`pillar6_strategy.py`)
* **วัตถุประสงค์**: อุปกรณ์เครื่องมือเชิงกลยุทธ์สำหรับให้ External Orchestrator สั่งทำงานตามรอบ
* **หน้าที่หลัก**:
  - **กลยุทธ์ต่อราคา (Price Negotiation - `strategy_negotiate_unmatched_orders`)**:
    - สแกนหาคำสั่งที่ยัง Unmatched ในกระดาน
    - ดึงราคา Best Bid 1 และ Best Offer 1 ล่าสุด
    - หากเป็นคำสั่ง Buy/Cover ให้ขยับมาที่ Bid 1, หากเป็นคำสั่ง Sell/Short ให้ขยับมาที่ Offer 1 (ล่อตลาด ไม่รีบ)
    - ส่งคำสั่งแก้ไขราคา (Change Price) หรือยกเลิกแล้วส่งใหม่
  - **กลยุทธ์ปิดคำสั่งค้างสิ้นวัน (EOD Cleanup - `strategy_eod_order_cleanup`)**:
    - สั่งยกเลิกคำสั่งที่ค้างอยู่ในระบบทั้งหมดก่อนตลาดปิด เพื่อป้องกันออเดอร์ค้างข้ามคืนโดยไม่ได้ตั้งใจ

---

## 📖 4. ระบบการเรียนรู้และซ่อมแซมตัวเอง (Self-Annealing Runbook Protocol)

เพื่อให้การทำงานผ่าน Playwright มีความทนทาน ไม่พังง่ายเมื่อหน้าเว็บเปลี่ยน DOM:
1. ทุกการกระทำของโบรกเกอร์ถูกบันทึกเป็นตารางขั้นตอนใน `learned_workflows/<name>.md`
2. หากขั้นตอนใดคลิกไม่สำเร็จ หรือเว็บเปลี่ยน UI ตัว Driver จะส่ง Error Snapshot กลับมา
3. ผู้ใช้หรือ Remote AI สามารถส่ง Selector ที่ถูกต้องกลับมาผ่าน MCP Tool `report_feedback_and_correct`
4. ระบบ `WorkflowEngine` จะทำการอัปเดตไฟล์ Markdown Runbook อัตโนมัติทันที ทำให้ระบบฉลาดขึ้นและไม่เกิดข้อผิดพลาดซ้ำ

---

## 🚀 5. แนวทางการผสานงานกับ External Orchestrator (Google Apps Script / External AI)

เนื่องจากระบบไม่มี Cron ภายใน ตัวอย่างการสั่งการจากภายนอกสามารถทำได้ดังนี้:
* **ช่วงเช้า (เช่น 09:30 น.)**: Google Apps Script ยิงเรียก `session_get_health` และ `portfolio_sync_db`
* **ช่วงระหว่างวัน**: ~~External AI สั่ง `monitor_register_position` สำหรับหุ้นที่ต้องการเฝ้าราคา เมื่อ Open API ตรวจพบราคาชนเป้า AI สั่งเรียก `trade_place_order`~~ → **ถอดออกแล้ว (2026-10-06)**: ฟีเจอร์ Monitor & Alert (`monitor_*` / `alert_*` tools + Alert Center) ถูกลบทั้งระบบ ตาม `docs/handoff/TASK-pillar2-portfolio-refactor.md`
* **ช่วงรอบต่อราคา (เช่น 12:00 น. หรือ 15:30 น.)**: Apps Script หรือ AI สั่งเรียก `strategy_negotiate_unmatched_orders`
* **ช่วงสิ้นวัน (เช่น 16:30 น.)**: Apps Script สั่งเรียก `strategy_eod_order_cleanup` และ `session_logout_all`

---
*เอกสารนี้มีผลบังคับใช้เป็นมาตรฐานหลักแทนข้อกำหนดเดิมทั้งหมด*
