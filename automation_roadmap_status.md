# ภาพรวมสถานะระบบอัตโนมัติ (Master Roadmap & 6-Pillars Feature Tracking Matrix)
**Investment Homelab: Hybrid High-Frequency Monitor & Runbook-Driven Browser Automation**

เอกสารนี้รวบรวมสถานะฟีเจอร์และเครื่องมือทั้งหมดของระบบ Investment Homelab ตามข้อกำหนดสถาปัตยกรรม 6 เสาหลัก (6-Pillars Modular Architecture) ใน [directive/phase3_detail.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/directive/phase3_detail.md) โดยสะท้อนสถานะโค้ดปัจจุบันในระบบ, การเชื่อมโยงเครื่องมือ Remote MCP, การตรวจสอบบนบัญชีจำลอง (Sandbox Verified), และการอนุมัติใช้งานจริง

---

## 🧭 สัญลักษณ์และความหมาย (Status Legend)

| หมวดหมู่ | สัญลักษณ์ | ความหมาย |
| :--- | :---: | :--- |
| **สถานะโค้ด (Dev Status)** | 🟢 **Done** | พัฒนาเสร็จสมบูรณ์ มีฟังก์ชันการทำงานพร้อม Error Handling และ Type Hints ครบถ้วน |
| | 🟡 **In Progress** | เขียนโค้ดแล้วบางส่วน / อยู่ระหว่างเชื่อมต่อเพิ่มเติม |
| | ⚪ **Pending** | อยู่ในแผนงานตามข้อกำหนด |
| **Sandbox Verified** | ✅ | ผ่านการทดสอบบนกระดานจำลอง (Click2Win / Settrade Sandbox) หรือ Unit Test ครบ 100% |
| | ⏳ | รอการทดสอบเพิ่มเติมบน Sandbox |
| **สถาปัตยกรรม & เทคโนโลยี** | ⚡ **Open API (MQTT)** | ดึงราคาความเร็วสูงและส่งสตรีมข้อมูลผ่าน Settrade Open API v2 SDK (ความเร็ว <50ms, RAM ~30MB) |
| | 🌐 **Playwright Runbook** | ทำงานผ่านเบราว์เซอร์อัตโนมัติ ควบคุมด้วยสเปก Markdown ใน `learned_workflows/*.md` |
| | 🛡️ **MCP Tool** | เปิดให้บริการเป็นฟังก์ชันเรียกใช้งานผ่าน Remote MCP Server (`/sse`) บนเครือข่าย Tailscale |

---

## 📊 ตารางสรุปสถานะฟีเจอร์ตาม 6 เสาหลัก (The 6-Pillars Feature Matrix)

### 🏛️ Pillar 1: Session Sentinel (ระบบความปลอดภัยและการจัดการ Session)
ดูแลการเชื่อมต่อ, การตรวจสอบสิทธิ์, การล็อกอิน, และการรับ OTP สำหรับโบรกเกอร์และ Open API

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P1.1** | `session_get_health` | ตรวจสอบสถานะการเชื่อมต่อของทั้งสองระบบ (Settrade Token Status, Browser DOM Status, Last Heartbeat) | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/pillar1_session.py` |
| **P1.2** | `session_login_broker` | สั่งเปิดเบราว์เซอร์และล็อกอินเข้าเว็บโบรกเกอร์ (รองรับทั้ง Krungsri KSS และ Click2Win) จัดการ Popup อัตโนมัติ | 🌐 Playwright | 🟢 Done | ✅ | `app/browser/click2win_auth_driver.py`<br>`app/browser/auth_driver.py` |
| **P1.3** | `session_submit_otp` | รับรหัส 2FA SMS OTP 6 หลัก เพื่อส่งต่อไปยังฟอร์มล็อกอิน (รองรับ KDE Connect D-Bus อัตโนมัติ และ Manual ผ่าน MCP) | 🌐 Playwright | 🟢 Done | ✅ | `app/services/kdeconnect_service.py`<br>`app/browser/auth_driver.py` |
| **P1.4** | `session_logout_all` | สั่ง Logout ออกจากระบบทั้งหมด เคลียร์ Token และปิด Chromium Context อย่างสะอาดและปลอดภัย | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/pillar1_session.py` |

---

### 🏛️ Pillar 2: Real-time Monitor & Alert (ศูนย์เฝ้าราคาความเร็วสูงและการแจ้งเตือน)
เฝ้ามองราคาแบบ Real-time ด้วยความเร็วสูงผ่าน MQTT WebSocket โดยไม่กินสเปกเครื่อง และส่งแจ้งเตือนเข้า LINE

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P2.1** | `monitor_register_position` | ลงทะเบียน Ticker หุ้น/สัญญาที่ต้องการเฝ้าระวัง พร้อมกำหนดระดับ Take Profit (TP) และ Stop Loss (SL) | ⚡ Open API | 🔴 Removed | ❌ | (ถอดฟีเจอร์ Monitor & Alert 2026-10-06) |
| **P2.2** | `monitor_get_realtime_quote` | ดึงข้อมูลราคาตลาด Bid/Offer สด และค่าสถิติประจำวันแบบความเร็วสูงระดับมิลลิวินาที | ⚡ Open API | 🔴 Removed | ❌ | (ถอดฟีเจอร์ Monitor & Alert 2026-10-06) |
| **P2.3** | `monitor_list_active` | ตรวจสอบรายการ Ticker ทั้งหมดที่กำลังเฝ้าระวังอยู่ในระบบ พร้อมค่า Threshold ปัจจุบัน | 🛡️ MCP | 🔴 Removed | ❌ | (ถอดฟีเจอร์ Monitor & Alert 2026-10-06) |
| **P2.4** | `monitor_cancel` | ยกเลิกการเฝ้าระวัง Ticker รายตัว ปลดการเชื่อมต่อ Stream เมื่อปิดสถานะเรียบร้อย | ⚡ Open API | 🔴 Removed | ❌ | (ถอดฟีเจอร์ Monitor & Alert 2026-10-06) |
| **P2.5** | **Abnormal Price Alert (+/-3%)** | ตรวจจับการแกว่งตัวของราคาผิดปกติเกิน +/-3% และส่ง Alert Card เข้า LINE ทันที | ⚡ Open API | 🔴 Removed | ❌ | (ถอดฟีเจอร์ Alert Center 2026-10-06) |

---

### 🏛️ Pillar 3: Trade Execution Engine (ศูนย์ส่งคำสั่งซื้อขายผ่านระบบจำลองจริง)
ส่งคำสั่งซื้อขายจริงบนกระดานจำลอง (Click2Win / Settrade Sandbox) ผ่าน Playwright Runbook โดยปลดล็อก DRY_RUN

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P3.1** | `trade_place_order` | ส่งคำสั่งซื้อหรือขาย (BUY / SELL / LONG / SHORT) แบบ End-to-End กด Submit จริงบน Sandbox | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar3_trade.py`<br>`app/browser/click2win_driver.py` |
| **P3.2** | `trade_cancel_order` | สั่งยกเลิกคำสั่งซื้อขายที่ค้างอยู่บนหน้าจอ View Order ตาม Order No. | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar3_trade.py` |
| **P3.3** | `trade_modify_price` | ปรับปรุงราคาคำสั่งเดิมบนกระดาน (Change Price) ไปยังราคาเป้าหมายใหม่ | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar3_trade.py` |
| **P3.4** | **Pre-trade Odd-lot Guard** | สกัดกั้นคำสั่งเศษหุ้น (`Volume % 100 != 0`) ไม่ให้หลุดไปที่โบรกเกอร์ | 🛡️ Core | 🟢 Done | ✅ | `app/services/validator.py` |
| **P3.5** | **Multi-Account Capability Guard** | ตรวจสอบความถูกต้องของประเภทบัญชีก่อนส่งคำสั่ง (Cash Balance vs TFEX Margin) | 🛡️ Core | 🟢 Done | ✅ | `app/services/validator.py` |
| **P3.6** | **Runbook Workflow Execution** | เอนจินรันคำสั่งอัตโนมัติตามตารางขั้นตอนในไฟล์ `learned_workflows/<name>.md` | 🌐 Playwright | 🟢 Done | ✅ | `app/services/workflow_engine.py` |
| **P3.7** | **Krungsri SBL Auto-Borrow (JIT)** | ยื่นขอยืมหุ้นอัตโนมัติบน SSO SBL Real Time (`#MainCenter_lbBorrow`) เมื่อมีสัญญาณ Short | 🌐 Playwright | 🟡 Pending Market Open | ⏳ | `learned_workflows/krungsri_market_open_operational_runbook.md` |
| **P3.8** | **Krungsri SBL Bulk Return (16:30)** | คืนหุ้นที่ Cover ครบแล้วรอบเดียวตอน 16:30 น. บน SSO SBL Real Time | 🌐 Playwright | 🟡 Pending Market Open | ⏳ | `learned_workflows/krungsri_market_open_operational_runbook.md` |

---

### 🏛️ Pillar 4: SBL Intelligence Center (ศูนย์บริหารจัดการยืม-คืนหุ้น SBL)
บริหารวงจรชีวิตการยืมและคืนหุ้นสำหรับกลยุทธ์ Short Selling ผ่านหน้าเว็บ Krungsri TradeMan

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P4.1** | `sbl_get_inventory` | กวาดตรวจสอบสต็อกหุ้นคงเหลือในคลัง SBL (Available Inventory) ก่อนตัดสินใจยิง Short | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar4_sbl.py`<br>`app/services/sbl_intelligence_service.py` |
| **P4.2** | `sbl_borrow_stock` | ดำเนินการกดยืมหุ้น SBL บนหน้าเว็บ บันทึก Broker Lot Transaction No. และเริ่มคิดดอกเบี้ย | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar4_sbl.py`<br>`app/browser/trademan_driver.py` |
| **P4.3** | `sbl_return_stock` | เข้าเมนูคืนหุ้น ค้นหา Lot เดิม และกดยืนยันการคืนหุ้นเพื่อหยุดคิดดอกเบี้ยยืม | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar4_sbl.py`<br>`app/browser/trademan_driver.py` |
| **P4.4** | `sbl_check_corporate_actions` | ตรวจสอบปฏิทินวันขึ้นเครื่องหมาย XD/XR ของหุ้นที่ยืม ป้องกันการเสียเงินปันผลชดเชย | 🛡️ Core | 🟢 Done | ✅ | `app/services/sbl_intelligence_service.py` |
| **P4.5** | **Hold Unmatched Short Shares** | หากยืม SBL สำเร็จแต่ออเดอร์ Short ไม่จับคู่ ระบบจะพักหุ้นไว้และแจ้งเตือนถาม ไม่คืนทันที | 🛡️ Core | 🟢 Done | ✅ | `app/services/trade_center_service.py` |

---

### 🏛️ Pillar 5: Portfolio Intelligence & Risk Center (ศูนย์ตรวจสอบพอร์ตและความเสี่ยง)
ตรวจสอบและรายงานสถานะพอร์ตการลงทุนแบบ Multi-Account ซิงก์ประวัติลงฐานข้อมูล SQLite

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P2.1** | `switch_account` | สลับบัญชีเทรดบนหน้าจอ (ระหว่าง Cash Balance, Credit Balance SBL, และ TFEX) | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar2_portfolio.py`<br>`app/browser/broker_factory.py` |
| **P2.2** | `portfolio_get_balances` | ดึงยอดเงินสด (Cash Balance), วงเงินซื้อ (Line Available), และ Excess Equity (EE) | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar2_portfolio.py` |
| **P2.3** | `portfolio_get_holdings` | กวาดข้อมูลหุ้น/สัญญาที่ถือครอง (Symbol, Volume, Avg Cost, Market Price, Unrealized PnL) | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar2_portfolio.py` |
| **P2.4** | `current_open_orders` | ดึงรายการคำสั่งที่ยังค้างอยู่ในตลาด (Open, Queuing, Partially Matched) | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/pillars/pillar2_portfolio.py` |
| **P2.5** | `portfolio_sync_db` | นำข้อมูลจริงจากหน้าเว็บมาทับลงในฐานข้อมูล SQLite (`positions`, `orders`) ให้ตรงกันเสมอ | 🛡️ Core | 🟢 Done | ✅ | `app/db/session.py`<br>`app/services/portfolio_overview_service.py` |

---

### 🏛️ Pillar 6: Tactical Strategy Tools (เครื่องมือเชิงกลยุทธ์ตามรอบการทำงาน)
เปิดให้ External Orchestrator (AI Agent / Google Apps Script) สั่งการกลยุทธ์คำสั่งตามจังหวะเวลา

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **P6.1** | `strategy_negotiate_unmatched_orders` | สแกนหาคำสั่งค้างท่อ ดึงราคา Best Bid 1 / Offer 1 แล้วปรับราคาล่อตลาดใหม่ให้อัตโนมัติ | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/pillar6_strategy.py`<br>`app/services/price_negotiation_service.py` |
| **P6.2** | `strategy_eod_order_cleanup` | คำสั่งยกเลิกคำสั่งซื้อขายที่ยังค้างอยู่ในระบบทั้งหมดก่อนตลาดปิด ป้องกันออเดอร์ค้างข้ามคืน | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/pillar6_strategy.py` |
| **P6.3** | `strategy_list_active` | รายงานสรุปสถานะการทำงานของกลยุทธ์ต่อราคาและผลการแก้ไขคำสั่งล่าสุด | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/pillar6_strategy.py` |
| **P6.4** | **TradeMan Passive Price Negotiation** | ตรวจสอบออเดอร์ค้างใน TradeMan รอบ 11:00/15:30 ปรับราคาเกาะหัวแถว (Bid 1/Offer 1/Uptick) | 🌐 Playwright | 🟡 Pending Market Open | ⏳ | `learned_workflows/krungsri_market_open_operational_runbook.md` |
| **P6.5** | **Action Entry Multi-Window Dispatcher** | ส่งคำสั่งเข้าสถานะตามหน้าต่างเวลา (10:05 / 14:35) พร้อมเชื่อมระบบ JIT SBL Auto-Borrow | 🛡️ Core | 🟡 Pending Market Open | ⏳ | `learned_workflows/krungsri_market_open_operational_runbook.md` |

---

## 🔌 ระบบโบรกเกอร์แบบเสียบปลั๊ก (Pluggable Broker Engines)

ระบบแยกส่วนการเชื่อมต่อโบรกเกอร์ออกจากโค้ดหลักเพื่อรองรับการเพิ่มโบรกเกอร์ใหม่ได้อย่างอิสระ ไม่เกิดปัญหา Regression:

| โบรกเกอร์ | โปรโตคอลหลัก | ตลาดที่รองรับ | บัญชีเทรด | SBL | Direct API | CLI Test Tool | โฟลเดอร์โมดูล |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Krungsri (TradeMan)** | 🌐 Playwright SSO + OTP | SET | Cash Balance (3024952), Margin (3024959) | ✅ | ❌ | `python -m app.brokers.krungsri.cli full-test` | `app/brokers/krungsri/` |
| **Click2Win (Sandbox)** | 🌐 Playwright SSO | SET, TFEX | Equity, Derivatives | ❌ | ❌ | `python -m app.brokers.click2win.cli` | `app/brokers/click2win/` |
| **Settrade Open API** | ⚡ REST + MQTT WebSocket | SET, TFEX | Sandbox Equity/TFEX | ❌ | ✅ | `.venv/bin/python test` | `app/brokers/settrade_openapi/` |
| **Liberator Securities** | 🌐 Playwright WebTrade | SET | Cash Balance (<liberator-acct>) | ❌ | ❌ | `python -m app.brokers.liberator.cli` | `app/brokers/liberator/` |

---

## 🧠 ระบบเรียนรู้และซ่อมแซมหน้าจออัตโนมัติ (Self-Annealing & Remote Studio)

| รหัส | ชื่อฟีเจอร์ / Tool | รายละเอียดการทำงาน | เทคโนโลยี | สถานะโค้ด | Sandbox Verified | โมดูลต้นทาง / ไฟล์ |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **SYS.1** | `mcp_get_6pillars_overview` | รายงานพิมพ์เขียวสถาปัตยกรรม 6 เสาหลัก สถานะโบรกเกอร์ และ Guardrails แก่ AI Agent | 🛡️ MCP | 🟢 Done | ✅ | `app/mcp/pillars/overview.py` |
| **SA.1** | `report_feedback_and_correct` | รับ Feedback จาก Remote AI แล้วอัปเดต Selector ในไฟล์ Runbook Markdown อัตโนมัติ | 🧠 Self-Annealing | 🟢 Done | ✅ | `app/mcp/remote_server.py`<br>`app/services/workflow_engine.py` |
| **SA.2** | `browser_snapshot` | อ่านโครงสร้าง DOM Tree และ CSS Selectors ของหน้าจอเพื่อใช้วิเคราะห์การคลิก | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/remote_server.py` |
| **SA.3** | `browser_screenshot` | ถ่ายภาพหน้าจอส่งกลับเป็น Base64 และ URL เพื่อให้ Remote AI ตรวจสอบผลงาน | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/remote_server.py` |
| **SA.4** | `browser_click` / `browser_type` | เครื่องมือ Interactive คลิกและพิมพ์แบบเฉพาะกิจสำหรับกู้วิกฤตหน้าจอติดขัด | 🌐 Playwright | 🟢 Done | ✅ | `app/mcp/remote_server.py` |

---

## ❌ รายการฟีเจอร์ที่ถูกปลดระวาง / ถอดออกจากโค้ดภายใน (Deprecated / Decoupled Features)

ตามมติการสัมภาษณ์ `/grill-me` รายการต่อไปนี้ได้รับการถอดออกจาก Core Gateway เพื่อรักษาความเป็น Clean Architecture:

1. **`DRY_RUN_MODE` (หยุดก่อนกดส่ง PIN):**
   * *สถานะ*: **ถอดออก (Deprecated)**
   * *เหตุผล*: ระบบเปลี่ยนไปเชื่อมต่อบัญชีจำลอง (Click2Win / Settrade Sandbox) ซึ่งมีวงเงินจำลองอยู่แล้ว จึงส่งคำสั่งจริงบน Sandbox ได้อย่างปลอดภัย 100%
2. **Hardcoded Market Regimes & Cron Schedulers ภายใน Homelab:**
   * *สถานะ*: **แยกส่วน (Decoupled to External Layer)**
   * *เหตุผล*: ย้ายการควบคุมรอบเวลา (เช่น 10:15, 11:00, 15:30) ออกไปให้ External AI Agent หรือ Google Apps Script เป็นผู้สั่งการผ่าน Remote MCP แทน เพื่อให้โค้ดฝั่ง Gateway ทำหน้าที่เป็น Capability Provider ที่เรียบง่าย
3. **Blocking Human Approval Dialogs บนทุกคำสั่ง:**
   * *สถานะ*: **ปรับเป็น Autonomous Execution with Instant LINE Reporting**
   * *เหตุผล*: คำสั่งที่ส่งมาจาก External Agent จะดำเนินการทันที พร้อมระบบ Guardrails คุ้มกัน และส่งรายงานสรุปผลเข้า LINE อัตโนมัติ

---
*ตาราง Matrix นี้สอดคล้องกับ [directive/phase3_detail.md](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/directive/phase3_detail.md) และใช้เป็นเกณฑ์ตรวจรับงานระบบหลัก*
