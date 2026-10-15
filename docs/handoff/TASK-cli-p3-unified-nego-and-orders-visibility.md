# TASK-cli-p3-unified-nego-and-orders-visibility: รวมคำสั่ง /nego ข้าม KSS (QuickTrade) & LIB + แสดงสถานะต่อราคาบนการ์ด /orders (Round B Preparation)

- Created: 2026-10-14 by Antigravity (หลังจาก grill-me /plan สรุปความต้องการร่วมกับผู้ใช้)
- Broker: KSS (QuickTrade Native In-Place Change) และ LIB (Liberator Native In-Place Change)
- Priority: P3 (High — กลยุทธ์การต่อราคา Pillar 6)
- Status: SUPERSEDED (2026-10-15)

---

> ⚠️ **SUPERSEDED (2026-10-15) — ห้าม Cline เริ่มการ์ดนี้**
> งานของการ์ดนี้ถูกแตกและแทนที่ด้วยการ์ด Loop 1 แล้ว:
> - `/orders` visibility + MARGIN lock + `authenticated` flag + Anti-Mock → **`TASK-loop1-1-pillar2-orders-and-margin-lock.md`**
> - รวม `/nego kss` → QuickTrade **in-place** (เลิก Cancel+Replace) + G4/G5 + `list_open_orders` → **`TASK-loop1-2-unify-kss-nego-to-quicktrade-inplace.md`**
> - LIB quote ตรงตัว + `/nego lib` hardening (fail-closed) → **`TASK-loop1-3-liberator-quote-and-nego-hardening.md`**
> - Live witness verification (Round B) → **`TASK-loop1-4-live-round-b-witness-verification.md`**

---

## 1. Context & Decisions (Antigravity เขียน)
จากการพูดคุยออกแบบร่วมกับผู้ใช้ ได้ข้อสรุปสถาปัตยกรรมดังนี้:

| # | การตัดสินใจ (Locked Decisions) |
|---|---|
| **D1** | **รวมคำสั่งเป็นหนึ่งเดียว (Unified Command):** ใช้ `/nego` เป็นคำสั่งหลัก (และ `/negotiate` เป็น alias) ทั้ง 2 โบรกเกอร์ รองรับทั้ง `/nego kss [เป้าหมาย]`, `/nego lib [เป้าหมาย]`, และ `/nego <order_no>` เพื่อให้ผู้ใช้งานจำง่าย ไม่สับสน |
| **D2** | **เปลี่ยน Backend KSS เป็น QuickTrade Native:** ยกเลิกการเรียก TradeMan cancel+replace (`trademan_driver.modify_order_price`) อย่างถาวร และให้คำสั่งต่อราคา KSS วิ่งผ่าน **QuickTrade Native Change** (`quicktrade_negotiation_service.negotiate_order_price`) แก้ไขราคาในที่ ไม่หลุดคิว |
| **D3** | **นโยบายต่อราคาแบบ Passive เดียวกันทั้ง 2 โบรก:**<br>- BUY → Best Bid 1<br>- SELL / SHORT → Best Offer 1<br>- กฎ **SET Uptick Rule** สำหรับ SHORT SELL (`target_price = max(Best Offer 1, LastPrice)`, หาก Offer 1 < Last ให้ fail-closed ทันที ไม่ขยับราคาลง)<br>- ตรวจ Tick size (G4) และ Max ticks distance (G5, default 3 ticks) |
| **D4** | **Pre-negotiation Visibility บนการ์ด `/orders`:**<br>ในการ์ด `/orders <broker> sync` ออเดอร์ที่ค้างและสามารถต่อราคาได้ จะแสดงสัญลักษณ์และราคาเป้าหมายให้เห็นล่วงหน้าทันที เช่น `⚡ MTC ค้าง 1,700 @29.25 (⚡ ต่อได้ -> Offer1 29.50)` พร้อมปุ่ม Quick Action ที่ Footer |
| **D5** | **รูปแบบการ์ดผลลัพธ์ (Result Cards):**<br>- สั่งเจาะจงออเดอร์เดียว (`/nego kss 11008198`) → แสดงการ์ดละเอียด `negotiate_card`<br>- สั่งหลายออเดอร์หรือทั้งพอร์ต (`/nego kss`) → แสดงการ์ดสรุปรายการ `nego_card` |
| **D6** | **แผนการทำงาน:** Cline พัฒนาโค้ดและ Unit Tests ทั้งหมดให้เสร็จในคืนนี้ (Offline); ส่วนการทดสอบ Live (Round B) ในตลาดจริง Antigravity และผู้ใช้จะรันตาม Runbook ในเวลาตลาดเปิด |

---

## 2. Scope — ไฟล์ที่อนุญาตให้แก้
- `app/services/line_cli/parser.py` (Unified command parsing + alias)
- `app/services/line_cli/handlers.py` (`_broker_modify`, `_handle_nego`, `_live_card` for orders)
- `app/services/line_cli/cards.py` (`orders_card` rendering negotiation indicator)
- `learned_workflows/shared/round_b_negotiation_live_runbook.md` [NEW — คู่มือ Round B]
- `rca/shared/rca_line_cli.md` (บันทึกอัปเดตสถาปัตยกรรม /nego)
- `tests/test_line_cli_parser.py` (Unit tests สำหรับ parser)
- `tests/test_line_cli_flow.py` (Unit tests สำหรับ handler, cards, routing)
- `scripts/verify_changes.py` (mapping ถ้ามีไฟล์ใหม่)

---

## 3. Context Map & สิ่งที่ต้องทำ (Cline เริ่มจากตรงนี้)

### 3.1 `app/services/line_cli/parser.py`
- ใน `COMMAND_ALIASES`: ตรวจสอบว่า `"negotiate": "nego"` หรือทำให้ canonical cmd เป็น `"nego"`
- รองรับรูปแบบคำสั่ง:
  - `/nego <broker>` (เช่น `/nego kss`, `/nego lib`)
  - `/nego <broker> <target>` (เช่น `/nego kss PTT`, `/nego kss 11008198`)
  - `/nego <order_no>` (เช่น `/nego 11008198` — ถ้ามีแค่ตัวเลขออเดอร์ ให้ target=order_no และ broker=None เพื่อให้ handler ไป auto-match กับ open orders)
  - คำสั่ง `/negotiate ...` ทำงานเหมือน `/nego ...` ทุกประการ

### 3.2 `app/services/line_cli/handlers.py`
1. **ปรับปรุง `_broker_modify` (L159-182):**
   - สำหรับ `broker == "kss"`:
     - เลิกเรียก `trademan_driver.modify_order_price`
     - เรียก `quicktrade_negotiation_service.negotiate_order_price(order_no=order_no)`
   - สำหรับ `broker == "lib"`:
     - เรียก `liberator_plugin.change_order(order_no=order_no, new_price=new_price)`
2. **ปรับปรุง `_handle_nego` (L801-876):**
   - รองรับกรณีที่ `parsed.broker` เป็น None แต่มี `parsed.target` เป็น order_no: ให้ค้นหาว่า order_no นี้อยู่ใน open orders ของ KSS หรือ LIB แล้วเลือก broker นั้นอัตโนมัติ
   - เมื่อต่อราคาเสร็จ:
     - ถ้าคำสั่งระบุ target เป็น order_no เดียว (Single Order) → แสดงการ์ด `cards.negotiate_card`
     - ถ้าคำสั่งเป็น Batch / หุ้นหลายตัว → แสดงการ์ด `cards.nego_card`
3. **ปรับปรุง `_live_card("orders", ...)` (L575-600):**
   - สำหรับออเดอร์ที่ค้าง (`kind in ("open", "partial")`):
     - เรียกดู Quote ตลาดสด (Bid1/Offer1) สั้นๆ เพื่อคำนวณ `target_price`
     - ถ้าต่อราคาได้ (เช่น ราคาเดิม != target_price และไม่ติด Uptick): แนบข้อมูล `target_price` และ `can_nego=True` ไปใน dict ของแต่ละแถวเพื่อส่งให้ `cards.orders_card`

### 3.3 `app/services/line_cli/cards.py`
- ใน `orders_card`:
  - สำหรับแถวที่มี `can_nego=True`: แสดงแท็กบอกราคาเป้าหมายชัดเจน เช่น:
    - ถ้าเป็น BUY: `(⚡ ต่อได้ -> Bid1 {target_price:.2f})`
    - ถ้าเป็น SELL/SHORT: `(⚡ ต่อได้ -> Offer1 {target_price:.2f})`
  - หาก open orders มีเพียง 1 รายการ: ปุ่มที่ Footer ให้มี `⚡ ต่อราคา {symbol} #{order_no}` เพื่อกดคลิกเดียวได้เลย

### 3.4 `learned_workflows/shared/round_b_negotiation_live_runbook.md` [NEW]
สร้างคู่มือขั้นตอนการรัน Round B Live สำหรับ Antigravity และผู้ใช้ในวันพรุ่งนี้:
- แผนทดสอบ Pre-flight (Session, OTP Relay)
- การตั้งออเดอร์ทดสอบห่างตลาด 2-3 tick
- การทดสอบ `/orders <broker> sync` เพื่อดูแท็กต่อราคา
- การทดสอบ `/nego kss <order_no>` (QuickTrade)
- การทดสอบ `/nego lib <order_no>` (Liberator)
- การทดสอบ Safety Invariants (Uptick violation บน SHORT, Out of ticks)

---

## 4. Steps / Task Decomposition (Loop Engineering — บังคับ)
1. **Unit 1 (Parser & Routing):** ปรับ `parser.py` ให้รวม `/nego` & `/negotiate` + auto-detect broker + tests ใน `test_line_cli_parser.py` → `verify_changes.py` PASS
2. **Unit 2 (KSS Backend to QuickTrade):** เชื่อม `_broker_modify` เข้า `quicktrade_negotiation_service` + tests ใน `test_line_cli_flow.py` → `verify_changes.py` PASS
3. **Unit 3 (Pre-negotiation Visibility & Cards):** อัปเดต `_live_card` ของ orders และ `cards.py` แสดงแท็ก `⚡ ต่อได้` + tests → `verify_changes.py` PASS
4. **Unit 4 (Runbook & Verification):** เขียน `round_b_negotiation_live_runbook.md` + อัปเดต `rca_line_cli.md` + รัน `--full` verify → เขียน Cline Report

---

## 5. Safety & Invariants (ห้ามละเมิด)
- **ห้ามยิงคำสั่งซื้อขายจริง (No Live Orders):** งานนี้ทดสอบด้วย mock / unit test เท่านั้น การทดสอบตลาดจริง (Round B) เป็นของ Antigravity ในวันพรุ่งนี้
- **ห้ามส่ง SMS OTP หรือ Re-authenticate เด็ดขาด**
- **ห้ามรีสตาร์ท gateway ในระหว่างที่ทำ Unit test**
- **SET Uptick Rule ต้อง Fail-closed เสมอสำหรับ SHORT SELL**

---

## 6. Cline Report (Cline เขียนเมื่อเสร็จ)
- Files changed:
- Summary:
- Tests run + result:
- Open questions:
