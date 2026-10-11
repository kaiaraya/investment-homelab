# คู่มือการเชื่อมต่อ 6 เสาหลัก (6 Pillars) กับ Remote MCP สำหรับ AI Agent & Developer
**Investment Homelab: Pluggable Multi-Broker Architecture & Autonomous MCP Integration**

---

## 1. แนวคิดและเป้าหมายของ 6 เสาหลัก (Why 6 Pillars?)

ในการพัฒนาระบบเทรดกึ่งอัตโนมัติ (Semi-Automated Trading) ที่ต้องเชื่อมต่อหลายโบรกเกอร์ (Krungsri, Click2Win, Settrade Open API, Liberator) และหลายอุปกรณ์ (Tailscale, KDE Connect Hardware Bridge, มือถือ 2FA OTP) การรวมโค้ดทุกอย่างไว้ในไฟล์เดียวมักทำให้เกิดปัญหา:
- **Coupling & Regressions**: เพิ่มโบรกเกอร์ใหม่แล้วโค้ดเดิมพัง
- **Cognitive Overload**: AI Agent สับสนเครื่องมือ ไม่รู้ว่าควรเช็กยอดเงินก่อนหรือยิงคำสั่งก่อน
- **Risk Inconsistency**: ไม่มีมาตรฐานกลางในการตรวจเช็กเศษหุ้น (Odd-lot) หรือความเข้ากันได้ของบัญชี

**แนวคิด 6 เสาหลัก (The 6 Pillars)** แก้ปัญหานี้โดยแบ่งขอบเขตความรับผิดชอบ (Domain Separation) ออกเป็น 6 ส่วนอิสระที่ชัดเจน:

```
                        🤖 Remote AI Agent (Claude / Cursor / Antigravity)
                                             │
                        ┌────────────────────▼────────────────────┐
                        │   Remote MCP Gateway (/sse on port 8000) │
                        └────────────────────┬────────────────────┘
                                             │
      ┌──────────────┬──────────────┬────────┴─────┬──────────────┬──────────────┐
      │              │              │              │              │              │
┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
│  Pillar 1  │ │  Pillar 2  │ │  Pillar 3  │ │  Pillar 4  │ │  Pillar 5  │ │  Pillar 6  │
│  Session   │ │  Monitor   │ │   Trade    │ │    SBL     │ │ Portfolio  │ │ Tactical   │
│  Sentinel  │ │  & Alert   │ │ Execution  │ │Intel Center│ │& Risk Audit│ │  Strategy  │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      │              │              │              │              │              │
      └──────────────┼──────────────┼──────────────┼──────────────┴──────────────┘
                     ▼              ▼              ▼
     ┌────────────────────────────────────────────────────────────┐
     │          Central Broker Registry (Pluggable Plugins)        │
     ├─────────────┬─────────────┬─────────────────┬──────────────┤
     │  Krungsri   │  Click2Win  │ Settrade OpenAPi│  Liberator   │
     │ (TradeMan)  │  (Sandbox)  │  (Direct M2M)   │  (WebTrade)  │
     └─────────────┴─────────────┴─────────────────┴──────────────┘
```

---

## 2. เจาะลึกโครงสร้าง 6 เสาหลัก (The 6 Domain Pillars)

### 🏛️ เสาหลักที่ 1: Session Sentinel (`pillar1_session.py`)
* **หน้าที่**: ดูแลการยืนยันตัวตน (Authentication), ความพร้อมในการเชื่อมต่อ (Health), และการรับรหัส 2FA SMS OTP จากมือถือ
* **จุดเด่น**:
  - รองรับฮาร์ดแวร์บริดจ์ **KDE Connect** ทั้งผ่าน Tailscale IP (`100.119.166.62:1716`) และ WiFi ในบ้าน (`192.168.1.187:1716`)
  - รักษาสถานะเบราว์เซอร์ Multi-tab ไม่ต้องล็อกอินใหม่ซ้ำซ้อน
* **เครื่องมือ MCP**:
  - `session_get_health()`: ตรวจสอบสถานะทุกโบรกเกอร์ในคลิกเดียว
  - `session_connect_all()`: สั่งเชื่อมต่อและเตรียมพร้อมทุกโบรกเกอร์ในคำสั่งเดียว
  - `session_login_broker(platform)`: ล็อกอินรายโบรกเกอร์ (`KRUNGSRI`, `CLICK2WIN`, `LIBERATOR`, `SETTRADE_OPENAPI`)
  - `session_submit_otp(otp_code, ref_code)`: ป้อนรหัส OTP ฉุกเฉิน
  - `session_logout_all()`: ปิดทุก Session อย่างสะอาด

---

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

### 🏛️ เสาหลักที่ 3: Trade Execution (`pillar3_trade.py`)
* **หน้าที่**: ส่งคำสั่งซื้อขาย ยกเลิก และแก้ไขราคา โดยมีระบบ Guardrails ตรวจสอบก่อนส่งจริง
* **ระบบความปลอดภัย (Safety Guardrails)**:
  - **Odd-lot Guard**: ปฏิเสธคำสั่งเศษหุ้นทันที (`Volume % 100 != 0`)
  - **Account Capability Matrix**:
    - หุ้น SET ส่งได้เฉพาะบัญชี `EQUITY` หรือ `CASH`
    - สัญญา TFEX ส่งได้เฉพาะบัญชี `DERIVATIVES`
    - SBL ส่งได้เฉพาะบัญชี `MARGIN` ของ Krungsri เท่านั้น
* **เครื่องมือ MCP**:
  - `trade_place_order(symbol, side, volume, price, price_type, platform, account_type)`
  - `trade_cancel_order(order_no, platform)`
  - `trade_modify_price(order_no, new_price, platform)`

---

### 🏛️ เสาหลักที่ 4: SBL Intelligence Center (`pillar4_sbl.py`)
* **หน้าที่**: บริหารวงจรชีวิตการยืมและคืนหุ้นสำหรับกลยุทธ์ Short Selling (เอกสิทธิ์เฉพาะ Krungsri TradeMan Pro)
* **จุดเด่น**: กวาดหน้าค้นหาแบบ Multi-page, บันทึก Lot Transaction No. เพื่อติดตามดอกเบี้ย และเช็กเครื่องหมายสิทธิประโยชน์
* **เครื่องมือ MCP**:
  - `sbl_get_inventory(symbols)`: ตรวจสอบจำนวนหุ้นที่มีให้ยืมในคลัง
  - `sbl_borrow_stock(symbol, volume, dry_run)`: ส่งคำสั่งขอยืมหุ้น
  - `sbl_return_stock(symbol, volume, dry_run)`: ส่งคำสั่งคืนหุ้นเพื่อหยุดคิดดอกเบี้ย
  - `sbl_check_corporate_actions(symbol)`: เช็ก XD/XM ป้องกันเงินปันผลชดเชย

---

### 🏛️ เสาหลักที่ 5: Portfolio Intelligence & Risk Center (`pillar5_portfolio.py`)
* **หน้าที่**: รวมข้อมูลพอร์ตการลงทุนแบบ Multi-Broker และตรวจสอบความเสี่ยงคงเหลือ
* **จุดเด่น**: แปลงข้อมูลจากทุกโบรกเกอร์เป็นมาตรฐานเดียวกัน (Unified Snapshot) ทั้ง Cash Balance, Line Available, Excess Equity, และ Unrealized P/L
* **เครื่องมือ MCP**:
  - `portfolio_list_accounts(platform)`: ดูสารบัญบัญชีทั้งหมดพร้อมตาราง Markdown
  - `switch_account(platform, account_type)`: สลับบัญชีที่ Active
  - `portfolio_get_balances(platform, account_type)`: ตรวจสอบวงเงินและอำนาจซื้อ
  - `portfolio_holdings(platform, account_type)`: ดูรายการหุ้นที่ถือครอง
  - `current_open_orders(platform, account_type)`: ดึงคำสั่งที่ยังค้างอยู่ในกระดาน (Queuing)
  - `portfolio_sync_db()`: ซิงก์ประวัติลงฐานข้อมูล SQLite

---

### 🏛️ เสาหลักที่ 6: Tactical Strategy Center (`pillar6_strategy.py`)
* **หน้าที่**: ดำเนินกลยุทธ์เชิงรอบเวลาอัตโนมัติ (Tactical Schedule Execution)
* **กลยุทธ์หลัก**:
  1. **Passive Price Negotiation**: รันเวลา **11:00 น.** และ **15:30 น.** เพื่อตรวจออเดอร์ค้าง ดึง Best Bid 1 / Best Offer 1 มาตั้งราคาใหม่เพื่อเพิ่มโอกาสจับคู่
  2. **End-of-Day Order Cleanup**: รันเวลา **16:35 น.** สั่งยกเลิกออเดอร์ค้างท่อทั้งหมด ป้องกันคำสั่งข้ามคืน
* **เครื่องมือ MCP**:
  - `strategy_negotiate_unmatched_orders(round_name)`
  - `strategy_eod_order_cleanup()`
  - `strategy_list_active()`

---

## 3. การเชื่อมต่อ Remote MCP ผ่าน Tailscale

### 3.1 การตั้งค่าใน Claude Desktop / Cursor / Antigravity IDE

ในไฟล์ `mcp_config.json` หรือการตั้งค่า Remote MCP Server:

```json
{
  "mcpServers": {
    "investment-homelab": {
      "url": "http://100.88.217.33:8000/sse"
    }
  }
}
```
*(กรณีรันบนเครื่อง Homelab เดียวกัน สามารถใช้ `http://localhost:8000/sse`)*

### 3.2 เครื่องมือเริ่มต้นสำหรับ AI Agent: `mcp_get_6pillars_overview`

เมื่อ AI Agent เริ่มบทสนทนา สามารถเรียกคำสั่ง:
```json
{
  "name": "mcp_get_6pillars_overview",
  "arguments": {}
}
```
ระบบจะส่งคืนพิมพ์เขียวสถาปัตยกรรม 6 เสาหลัก รายชื่อโบรกเกอร์ที่เชื่อมต่ออยู่ และกฎความปลอดภัย ทำให้ AI Agent สามารถวางแผนและแนะนำขั้นตอนที่ถูกต้องได้ทันที

---

## 4. ตัวอย่างคำสั่ง Prompt สำหรับผู้ใช้งานกับ AI Agent

### ตัวอย่างที่ 1: ตรวจสุขภาพระบบตอนเช้า
> **User Prompt**: "ตรวจเช็กสุขภาพโบรกเกอร์ทั้งหมด และรายงานยอดเงินคงเหลือในพอร์ตให้หน่อย"  
> **Workflow ของ AI**:
> 1. เรียก `session_get_health()` เพื่อยืนยันสถานะ Session
> 2. เรียก `portfolio_list_accounts()` เพื่อระบุบัญชี
> 3. เรียก `portfolio_get_balances()` เพื่อสรุปยอดเงินและอำนาจซื้อ

### ตัวอย่างที่ 2: ตรวจสอบความปลอดภัยและตั้งเกราะป้องกัน TP/SL
> **User Prompt**: "ตรวจสอบพอร์ตว่ามีหุ้นตัวไหนยังไม่ได้ตั้ง Stop Loss ไหม และตั้ง TP/SL ให้ CPALL ด้วย"  
> **Workflow ของ AI**:
> 1. เรียก `portfolio_holdings()` เพื่อดูสถานะพอร์ตและตรวจว่ามีเกราะ TP/SL ครบหรือไม่
> 2. ปรับระดับ TP/SL บน position record ให้ครบทุกตัว (ฟีเจอร์ Monitor & Alert เดิมถูกถอดออกแล้ว)

### ตัวอย่างที่ 3: ส่งคำสั่งซื้อหุ้นบน Sandbox
> **User Prompt**: "ซื้อหุ้น TRUE 500 หุ้นที่ราคา 13.20 บน Click2Win"  
> **Workflow ของ AI**:
> 1. ตรวจสอบ Odd-lot (`500 % 100 == 0` -> ผ่าน)
> 2. เรียก `trade_place_order(symbol="TRUE", side="BUY", volume=500, price=13.20, platform="CLICK2WIN")`
> 3. ส่งผลลัพธ์ Order No. กลับมาให้ผู้ใช้

### ตัวอย่างที่ 4: เคลียร์คำสั่งค้างก่อนตลาดปิด
> **User Prompt**: "ตอนนี้ 16:35 น. แล้ว ช่วยตรวจและเคลียร์คำสั่งที่ยังไม่ Match ทั้งหมด"  
> **Workflow ของ AI**:
> 1. เรียก `strategy_eod_order_cleanup()`
> 2. สรุปรายการคำสั่งที่ยกเลิกสำเร็จ

---

## 5. การเพิ่มโบรกเกอร์ใหม่เข้าสู่ระบบ (Extending Pluggable Brokers)

การเพิ่มโบรกเกอร์ใหม่ทำได้โดยสร้างโฟลเดอร์ใน `app/brokers/<broker_name>/` และสืบทอดคลาส `BaseBrokerPlugin`:

```python
from app.brokers.base import BaseBrokerPlugin, BrokerMetadata, TransportType

class NewBrokerPlugin(BaseBrokerPlugin):
    @property
    def metadata(self) -> BrokerMetadata:
        return BrokerMetadata(
            name="new_broker",
            display_name="New Broker Securities",
            transport=TransportType.PLAYWRIGHT,
            supported_markets=["SET"],
            supports_sbl=False
        )

    # Implement: get_health, get_account_summary, get_portfolio, place_order, cancel_order
```

จากนั้นลงทะเบียนใน `app/brokers/__init__.py` ด้วยคำสั่ง:
```python
broker_registry.register(new_broker_plugin)
```
ระบบทั้ง 6 เสาหลัก (Pillar 1 ถึง Pillar 6) จะมองเห็นและสามารถสั่งงานโบรกเกอร์ใหม่ผ่าน MCP ได้ทันทีโดยไม่ต้องแก้ไขไฟล์หลักอื่นๆ!
