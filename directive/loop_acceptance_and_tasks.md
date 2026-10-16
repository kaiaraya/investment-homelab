# Loop 1 Acceptance Scorecard & Task Breakdown (KSS Margin + LIB Cash · LINE CLI Pillar 1–3)

**วัตถุประสงค์เอกสาร:** ใช้เป็น **(1) เกณฑ์ตรวจรับงาน (Definition of Done)** สำหรับเปรียบเทียบกับ `## Cline Report` / `## Verification & Stepwise Approval` และ **(2) แผนแตกการ์ดงาน (Task Breakdown)** แยกงานที่เสร็จแล้วกับงานที่ยังค้างอยู่เพื่อส่งต่อให้ Cline (T0/T1) / Flash 3.8 (T2) ทำทีละใบจนจบ Development Loop นี้

## 1. ตัวชี้วัดความสำเร็จของ Development Loop นี้ (Loop Acceptance Scorecard)

Loop นี้จะถือว่า **สำเร็จบริบูรณ์ (DONE)** เมื่อผ่านตัวชี้วัดทั้ง **4 หมวด (16 ข้อ)** ด้านล่างครบทั้งในระดับ **Unit Test (`verify_changes.py`)** และระดับ **Live Market Verification (Human Witness บน LINE + หน้าจอโบรกเกอร์จริง)**:

### หมวด A: ความพร้อมของระบบและขอบเขตที่ปิดไว้ (Slim Gateway & Dormant Isolation)
| รหัส | ตัวชี้วัด (Metric / Criterion) | วิธีตรวจสอบเทียบกับ Handoff ของ Cline | สถานะปัจจุบัน |
| :--- | :--- | :--- | :---: |
| **A1** | **Slim Gateway Boot**: รัน `app.main:app` แล้วไม่มี Background Scheduler (`phase3_scheduler`), Action Exit (`action_exit_dispatcher`), Agentic AI (`master_orchestrator`), หรือ Click2Win Polling ทำงานเบื้องหลัง | ตรวจ `app/core/config.py` ว่า Flag ทั้ง 4 ตัวเป็น `False` และไม่มี Task นอกขอบเขตถูกปลุกใน Log | ✅ ผ่านแล้ว |
| **A2** | **No Console Dependency**: การใช้งานจริงตั้งแต่ต้นจนจบไม่ต้องเปิดหน้าเว็บ `/console` เลย (สั่งผ่าน LINE 100%) | ตรวจใน `## Verification & Stepwise Approval` ว่าไม่มีขั้นตอนที่บังคับให้กดผ่าน `/console` | ✅ ผ่านแล้ว |
| **A3** | **Account Scope Lock**: `kss` ทำงานบนบัญชี **`MARGIN (3024959)`** เป็นค่าเริ่มต้นเสมอ และ `lib` ทำงานบนบัญชี **`CASH`** เท่านั้น ไม่มีการหลุดไปดึงข้อมูล `Click2Win` (`else: CLICK2WIN`) | ตรวจโค้ดใน `pillar2_portfolio.py` และ `trademan_driver.py` ว่าไม่มี `else: CLICK2WIN` ค้างอยู่ และล็อกบัญชี `3024959` | ✅ ผ่านระดับ Unit (`7bc4bf2` · `TASK-loop1-1`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |

### หมวด B: Pillar 1 — การล็อกอินและการรักษา Session ผ่าน LINE (`/status`, `/login`, `/logout`)
| รหัส | ตัวชี้วัด (Metric / Criterion) | วิธีตรวจสอบเทียบกับ Handoff ของ Cline | สถานะปัจจุบัน |
| :--- | :--- | :--- | :---: |
| **B1** | **Zero-OTP Gate (Invariant 9)**: ถ้า `otp_relay_readiness.check().ready == False` คำสั่ง `/login` ต้องหยุดทันทีและแจ้งเตือนใน LINE โดยไม่กดขอ SMS OTP จากโบรกเกอร์ | ตรวจผลเทสต์ `tests/test_otp_relay_readiness.py` และ `tests/test_line_cli_flow.py` | ✅ ผ่านแล้ว |
| **B2** | **Sequential Multi-Broker OTP**: สั่ง `/login kss` และ `/login lib` (หรือ `/login all`) แล้วรับ SMS OTP 6 หลักทาง LINE เข้าถูกโบรกเกอร์ (`otp_relay_registry.py` บน `AsyncSessionLocal`) | ทดสอบสด `/login kss` และ `/login lib` ยืนยันเข้าสู่ระบบสำเร็จ (`🟢 alive`) | ✅ ผ่านแล้ว |
| **B3** | **True Session Drop Detection (`CLI-RCA-008`)**: หากคุกกี้หมดอายุหรือหน้าเว็บเด้งไป `/SignIn` หรือ `/login` คำสั่ง `/status` ต้องรายงาน `🔴 หลุด` (ห้ามรายงาน `🟢 alive` ปลอม) | ตรวจผลเทสต์ `tests/test_auth_session_nondestructive.py` + ทดสอบตอน Session หมดอายุ | ✅ ผ่านแล้ว |
| **B4** | **Zero Secret/OTP Leak (`F-5` / `F-8`)**: ไม่มีรหัส OTP 6 หลัก, PIN, หรือ `?token=eyJ...` ปรากฏในไฟล์ Log ของ Gateway | รัน `grep -E "OTP|token=" data/logs/*.log` หลังทดสอบต้องไม่พบข้อมูลลับเปลือย | ✅ ผ่านแล้ว |

### หมวด C: Pillar 2 — ความถูกต้องของพอร์ต วงเงิน และออเดอร์ค้าง (`/port`, `/cash`, `/orders`)
| รหัส | ตัวชี้วัด (Metric / Criterion) | วิธีตรวจสอบเทียบกับ Handoff ของ Cline | สถานะปัจจุบัน |
| :--- | :--- | :--- | :---: |
| **C1** | **Read/Sync Never Triggers Login (Invariant 7)**: สั่ง `/port sync`, `/cash sync`, `/orders sync` ตอน Session หลุด ต้องตอบกลับให้ไป `/login` ก่อน ห้ามสั่ง Login/ขอ OTP เอง | ตรวจผลเทสต์ใน `tests/test_line_cli_flow.py` | ✅ ผ่านแล้ว |
| **C2** | **Honest `/port kss sync` & `/port lib sync` (`CLI-RCA-002/006/010/012/013`)**: แสดง `Amount` + `Unrealized P/L` ตรงกับหน้าเว็บจริง, คำนวณ `%P/L` ฝั่ง `(S)` ถูกทิศทาง, แยกแถว `หุ้นยืมคงเหลือ (B)` เฉพาะ `kss`, และแบ่งหน้า Carousel ครบทุกตัว | ยืนยันผล Live Test P1.6 เมื่อ `2026-10-14 06:43` (KSS) + ทดสอบคู่กับ `/port lib sync` | ✅ ผ่านแล้ว (KSS + Unit LIB `7bc4bf2`)<br>⏳ รอตรวจเลขบัญชีบนหัวการ์ด LIB สด (`TASK-loop1-4`) |
| **C3** | **Honest `/cash kss sync` & `/cash lib sync` (`CLI-RCA-007/009/011`)**: `kss` แสดง `Line Available (PP)`, `Excess Equity (EE)`, และ `Cash balance` ของบัญชี `MARGIN (3024959)` ตรงกับแอป; `lib` แสดงเงินสด/กำลังซื้อของ Liberator จริง; ถ้าอ่านไม่ได้ต้องขึ้นการ์ด `⚠️ อ่านไม่ได้` | ยืนยันผล Live Test P2b เมื่อ `2026-10-14 11:10` (`CLI-RCA-011 CLOSED`) | ✅ ผ่านแล้ว |
| **C4** | **Honest `/orders kss sync` & `/orders lib sync`**: แสดงรายการออเดอร์วันนี้ครบถ้วน แยกสถานะ `ค้าง (balance > 0)` vs `ครบ (Matched)` vs `ยกเลิก (Cancelled)` ชัดเจน อ่านชื่อหุ้นบนมือถือไม่ตกขอบ (`CLI-RCA-004`) และถ้า Session หลุดต้องขึ้น `⚠️ อ่านไม่ได้` (ห้ามขึ้น `🟢 live` ปลอม) | ตรวจว่า `current_orders` ส่ง flag `authenticated` มาให้ `handlers.py` และปรับ Layout แถวออเดอร์บนการ์ด | ✅ ผ่านระดับ Unit (`7bc4bf2` · `TASK-loop1-1`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |

### หมวด D: Pillar 3 — การต่อราคาออเดอร์ค้างในที่ (`/nego` — เป้าหมายสูงสุดของ Loop นี้)
| รหัส | ตัวชี้วัด (Metric / Criterion) | วิธีตรวจสอบเทียบกับ Handoff ของ Cline | สถานะปัจจุบัน |
| :--- | :--- | :--- | :---: |
| **D1** | **In-Place Amendment Only (ห้าม Cancel + Replace เด็ดขาด)**: ทั้ง `/nego kss` และ `/nego lib` ต้องแก้ราคาบน **Order Number เดิม** เท่านั้น ห้ามยกเลิกแล้วส่งคำสั่งใหม่ | `handlers.py` (`_broker_modify` ของ `/nego kss`) วิ่งเข้า `quicktrade_negotiation_service` (`QUICKTRADE_INPLACE`) แล้ว | ✅ ผ่านระดับ Unit (`d7bde41` · `TASK-loop1-2`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |
| **D2** | **Unified `/nego` Command & Guardrails G1–G6**: คำสั่ง `/nego kss [SYM\|order_no]` และ `/nego lib [SYM\|order_no]` บังคับใช้ครบทั้ง 6 Guardrails: G1 (Kill-switch), G2 (`LINE_NEGO_WINDOWS`), G3 (Session alive), G4 (SET tick size), **G5 (ห่างไม่เกิน `LINE_NEGO_MAX_TICKS = 3` ช่อง)**, และ **G6 (Short Uptick Rule: `Best Offer 1 > LastPrice` strict)** | เส้นทาง QuickTrade ของ `kss` และ WebTrade ของ `lib` ตรวจ G1–G6 ครบทุกข้อก่อนกด Submit | ✅ ผ่านระดับ Unit (`d7bde41` & `9ed1f5a`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |
| **D3** | **Accurate Target Symbol Quote on Liberator**: `liberator_driver.get_market_bid_offer(symbol)` ดึงราคา `Bid 1 / Offer 1 / Last` ของหุ้นตัวที่ต้องการต่อราคาได้ตรงตัวจริง (ผ่าน `/vb/config` + `/vb/stock/info` gate `n == symbol`) | ตรวจโค้ด + `scripts/liberator/live_check_quote_gate.py` PASS บน broker สด | ✅ ผ่านระดับ Unit + Live Quote API (`9ed1f5a` · `TASK-loop1-3`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |
| **D4** | **Post-Submit DOM Verification (Anti-Mock)**: หลังกดยืนยันแก้ราคาทั้งบน `kss` (QuickTrade) และ `lib` (WebTrade) ตัว Driver ต้องอ่านตารางออเดอร์ซ้ำเพื่อยืนยันว่า **Order No. เดิมเปลี่ยนเป็นราคาใหม่จริง** ก่อนรายงาน `✅` บนการ์ด LINE | `lib` ทำแล้วใน `change_order()`; `kss` ทำแล้วใน `quicktrade_driver.amend_price` (`d7bde41`) รอ Live Test ตอนตลาดเปิด | ✅ ผ่านระดับ Unit (`d7bde41` & `9ed1f5a`)<br>⏳ รอ Live Witness (`TASK-loop1-4`) |
| **D5** | **End-to-End Live Market Witness Test (Round B)**: ผู้ใช้ส่งออเดอร์ตั้งรอไว้เองบนแอปทั้ง `kss` (MARGIN) และ `lib` (CASH) แล้วพิมพ์ `/orders sync` → `/nego kss` → `/nego lib` ผ่าน LINE ในเวลาตลาดเปิด ผลลัพธ์ตรงกับหน้าจอโบรกเกอร์ 100% | มนุษย์ (Witness) ยืนยันผลบนหน้าจอมือถือและหน้าเว็บโบรกเกอร์จริง | ⏳ พร้อมรัน (`Status: READY` · `TASK-loop1-4`) |

## 2. สรุปงานที่ทำเสร็จแล้ว (Completed Tasks Baseline)

รายการด้านล่างคือการ์ดที่พัฒนาและตรวจทานผ่านแล้วในรอบก่อนหน้า (**ห้าม Cline รื้อหรือเขียนทับตรรกะที่ผ่านแล้ว**):

1. **`TASK-line-otp-group-relay.md` & `TASK-otp-channel-authoritative.md` (DONE ✅)**:
   * ย้ายระบบรับ OTP มาใช้ LINE (`otp_relay_readiness.py` + `otp_relay_registry.py` บน `AsyncSessionLocal`) และปิด KDE Connect เป็น Dormant
2. **`TASK-line-cli.md` (DONE ✅ — โครงสร้างพื้นฐาน)**:
   * สร้าง `app/services/line_cli/{parser,handlers,cards}.py` รองรับไวยากรณ์ `/help`, `/status`, `/login`, `/logout`, `/port`, `/cash`, `/orders`, `/nego`
3. **`TASK-cli-p0-data-integrity.md` (DONE ✅)**:
   * แก้ `CLI-RCA-006/007/008/009`: แก้ Selector สลับบัญชีและดึงตารางพอร์ตจริงของ TradeMan, แก้ `/cash lib sync` ไม่ให้หลุดไปดึงข้อมูล Click2Win, และตรวจจับหน้า `/SignIn` ตอน Session หมดอายุ
4. **`TASK-cli-p1-display-and-redaction.md`, `TASK-cli-p1_5`, `TASK-cli-p1_6-borrowed-row.md` (DONE & LIVE VERIFIED ✅)**:
   * แก้เครื่องหมาย `%P/L` ของสถานะ `SHORT (S)`, แบ่งหน้า Carousel ของ `/port`, ปิดการรั่วไหลของ OTP/Token ใน Log (`redaction.py`), แสดง `Amount` + `Unrealized P/L` และแยกหมวด `หุ้นยืมคงเหลือ (B)` ของ Krungsri
5. **`TASK-cli-p2a`, `TASK-cli-p2a_1`, `TASK-cli-p2b-real-account-info-selectors.md` (DONE & LIVE VERIFIED ✅)**:
   * ปิด `CLI-RCA-011`: อัปเดต Selector จริงของแถบล่าง `div.bg-darkGray` และตาราง Account Info บน TradeMan ทำให้ `/cash kss sync` แสดง `Line Available`, `Excess Equity`, และ `Cash balance` ของบัญชี Margin ได้ตรงกับแอป 100%
6. **`TASK-liberator-change-order-inplace.md` (DONE — Driver Level ✅)**:
   * สร้าง `liberator_driver.change_order()` กดปุ่ม `Change` ในที่บน `#OrderTableList` (แก้ `LIB-RCA-016` row anchor `input[id='<order_no>']` และ `LIB-RCA-017` scope `div.overlay`) พร้อมทดสอบสดบนออเดอร์จริง `#11894` สำเร็จ
7. **`TASK-krungsri-quicktrade-passive-negotiate.md` (DONE — Unit Level ✅)**:
   * สร้าง `app/brokers/krungsri/quicktrade_driver.py` และ `app/services/quicktrade_negotiation_service.py` สำหรับเข้าหน้า Quick Trade SSO เพื่อกด `Change Price& Volume` แก้ราคาในที่โดยไม่เสียคิว

## 3. แผนแตก Task งานที่ยังไม่เสร็จ (Remaining Tasks สำหรับส่งให้ Cline)

เพื่อให้บรรลุเป้าหมายสูงสุดของ Loop นี้ครบทุกข้อโดยไม่ให้ Context ของ Cline บวม แนะนำให้แบ่งงานที่เหลือออกเป็น **4 การ์ดย่อยเรียงตามลำดับความสำคัญ** ดังนี้ครับ:

### การ์ดใบที่ 1: `TASK-loop1-1-pillar2-orders-and-margin-lock`
* **เป้าหมาย**: เก็บตกช่องโหว่ที่ค้างอยู่ใน Pillar 2 เพื่อให้ `/orders` และ `/port` ของ `kss` (MARGIN `3024959`) และ `lib` (CASH) สมบูรณ์ 100% ก่อนเริ่มต่อราคา
* **สิ่งที่ Cline ต้องทำ (Scope & Context Map)**:
  1. **`app/mcp/pillars/pillar2_portfolio.py` (`portfolio_holdings` L210–340 และ `current_orders` / `current_open_orders` L450–620)**:
     * ลบ `else: CLICK2WIN` ที่ยังตกค้างอยู่ออกทั้งหมด (ตาม Open Question ข้อ 2 ของ `TASK-cli-p0`) หากส่งชื่อ Platform ที่ไม่รู้จักต้อง `raise ValueError`
     * ส่งค่า `"authenticated": bool(...)` ออกมาจาก `current_orders()` เหมือนที่ทำใน `portfolio_get_balances()` และล็อกให้ `KRUNGSRI` ใช้บัญชี `MARGIN (3024959)` เป็นค่าเริ่มต้นใน Loop นี้
     * ใน `portfolio_holdings` ของ `LIBERATOR` ให้ส่ง `account_no` จริงออกมาด้วย เพื่อให้หัวการ์ด `/port lib sync` แสดงเลขบัญชีแทนคำว่า `"LIVE"` (Open Question ข้อ 3 ของ `TASK-cli-p0`)
  2. **`app/browser/trademan_driver.py` (`switch_account` L294–417)**:
     * แก้ Branch `"browser not active"` ที่เคยคืนค่าปลอม `{"success": True, "status": "SIMULATED_SWITCH"}` ให้คืน `{"success": False, "status": "BROWSER_NOT_ACTIVE"}` ตามกฎ Anti-Mock (Open Question ข้อ 1 ของ `TASK-cli-p0`)
  3. **`app/services/line_cli/handlers.py` (`_live_card` ส่วน `orders` L607–618) & `cards.py` (`orders_card`)**:
     * ถ้า `res.get("authenticated") is False` ให้คืน `cards.unavailable_card()` ทันที (ห้ามแสดงการ์ดออเดอร์ว่างพร้อมป้าย `🟢 live`)
     * ปรับการแสดงผลแต่ละแถวใน `orders_card` เป็น 2 บรรทัด (ชื่อหุ้นตัวหนาขนาด `md`) แก้ปัญหาชื่อหุ้นถูกตัดขอบบนจอมือถือ (`CLI-RCA-004`)
* **คำสั่ง Verify**:
  * `.venv/bin/python scripts/verify_changes.py app/mcp/pillars/pillar2_portfolio.py app/browser/trademan_driver.py app/services/line_cli/handlers.py app/services/line_cli/cards.py`

### การ์ดใบที่ 2: `TASK-loop1-2-unify-kss-nego-to-quicktrade-inplace`
* **เป้าหมาย**: รวมศูนย์คำสั่ง `/nego kss [SYMBOL|order_no]` ให้ใช้กลไก **In-Place Change ผ่าน Quick Trade (`quicktrade_driver`)** แทน `trademan_driver.modify_order_price` (ซึ่งเป็น Cancel+Replace ที่ผิดกฎเหล็ก) และบังคับใช้ Guardrails G1–G6 ให้ครบทุกข้อ
* **สิ่งที่ Cline ต้องทำ (Scope & Context Map)**:
  1. **`app/services/quicktrade_negotiation_service.py` (`plan_negotiation` & `negotiate_order_price` L128–239)**:
     * เพิ่มการตรวจ **G4 (`validator.validate_tick_size`)** และ **G5 (`_tick_distance_exceeds` ไม่เกิน `settings.LINE_NEGO_MAX_TICKS = 3` ช่อง)** เข้าไปใน `plan_negotiation()` (หากเกิน 3 ช่องให้คืน `NegotiationOutcome.MAX_TICKS_EXCEEDED` พร้อมเหตุผลว่าห่างกี่ช่อง)
     * ล็อกให้ค้นหาและทำงานเฉพาะบัญชี **`MARGIN (3024959)`** (`settings.TRADEMAN_ACCOUNT_NO_MARGIN`) เป็นหลักตามขอบเขต Loop นี้
  2. **`app/brokers/krungsri/quicktrade_driver.py`**:
     * เพิ่มเมธอด `list_open_orders(account_no=settings.TRADEMAN_ACCOUNT_NO_MARGIN, symbol=None)` เพื่อดึงรายการออเดอร์ค้าง (`balance > 0`) ทั้งหมดจากตาราง `#orderBodyEq` ของบัญชี Margin สำหรับกรณีผู้ใช้พิมพ์ `/nego kss` (ไม่ระบุเลขคำสั่ง) หรือ `/nego kss PTT` (ระบุชื่อหุ้น)
  3. **`app/services/line_cli/handlers.py` (`_handle_nego` L801–876 และ `_broker_modify` L159–182)**:
     * เปลี่ยนเส้นทางของ `/nego kss [SYMBOL|order_no]` ให้เรียกใช้ `quicktrade_negotiation_service` (In-Place Change) ทั้งหมด **ห้ามเรียก `trademan_driver.modify_order_price` (Cancel+Replace) ในเส้นทาง LIVE อีกต่อไป**
     * ให้ `/negotiate <order_no>` เป็น Alias ที่ชี้เข้า Flow เดียวกันกับ `/nego kss <order_no>` เพื่อไม่ให้มีโค้ดซ้ำซ้อน 2 เส้นทาง
* **คำสั่ง Verify**:
  * `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`

### การ์ดใบที่ 3: `TASK-loop1-3-liberator-quote-and-nego-hardening`
* **เป้าหมาย**: ทำความสะอาดและรับประกันว่า `/nego lib [SYMBOL|order_no]` ดึงราคา `Bid 1 / Offer 1` ของหุ้นเป้าหมายได้ตรงตัวจริง 100% และต่อราคาในที่ (`change_order`) ผ่าน LINE CLI ได้อย่างปลอดภัย
* **สิ่งที่ Cline ต้องทำ (Scope & Context Map)**:
  1. **`app/brokers/liberator/driver.py` (`get_market_bid_offer` L766–860)**:
     * แก้ปัญหาที่ตาราง Bid/Offer บนหน้า `/Portfolio` อาจแสดงราคาของหุ้นตัวอื่นค้างอยู่ (`TASK-liberator-change-order-inplace.md` L85): หลังกรอก `clean_sym` ใน `#SearchSymbolList-setBuySellFooter` และกด `Enter` ต้องตรวจสอบจาก DOM (หรือดึงจาก Response ของ `POST /vb/stock/info` และ `POST /vb/stock/bid-offer`) ว่า Quote ที่อ่านได้เป็นของ `clean_sym` จริง หากชื่อหุ้นบนหัวกระดานไม่ตรงกับ `clean_sym` ต้องคืน `_unknown_quote` (Fail-Closed ตามกฎ Anti-Mock)
  2. **`app/services/line_cli/handlers.py` (`_handle_nego` สำหรับ `broker == "lib"`)**:
     * ตรวจสอบการเชื่อมโยงระหว่าง `_broker_open_orders("lib")` → `_plan_nego("lib", ...)` → `liberator_plugin.change_order()` ว่าเมื่อ `change_order` คืน `action="AMENDED_IN_PLACE"` และยืนยันราคาใหม่บน `#OrderTableList` แล้ว การ์ด `cards.nego_card` แสดงผล `✅ #order_no BUY/SELL SYM old -> new` ถูกต้องครบถ้วน
  3. **`tests/test_line_cli_flow.py` & `tests/test_liberator_change_order.py`**:
     * เพิ่ม Unit Test ทดสอบ End-to-End Flow ของคำสั่ง `/nego lib`, `/nego lib BCH`, และ `/nego lib 11894` (ทั้งกรณีสำเร็จ, กรณีห่างเกิน 3 Ticks, และกรณีอ่าน Quote ไม่ได้)
* **คำสั่ง Verify**:
  * `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/services/line_cli/handlers.py`

### การ์ดใบที่ 4: `TASK-loop1-4-live-round-b-witness-verification` (รันช่วงตลาดเปิด 09:55–12:30 / 14:25–16:30)
* **เป้าหมาย**: ทดสอบสดในเวลาตลาดเปิด (Stepwise Approval Stage C ร่วมกับคุณในฐานะ Witness) เพื่อปิด Loop 1 อย่างสมบูรณ์
* **ขั้นตอนทดสอบสด (Live Checklist)**:
  1. สั่ง `/status` และ `/login kss`, `/login lib` ผ่าน LINE (ยืนยัน OTP ผ่าน LINE สำเร็จทั้งคู่)
  2. สั่ง `/port kss sync`, `/cash kss sync`, `/orders kss sync` และ `/port lib sync`, `/cash lib sync`, `/orders lib sync` เทียบตัวเลขกับหน้าจอจริง
  3. คุณวางออเดอร์ตั้งรอไว้ในตลาดจริง (ห่างจาก Bid 1 / Offer 1 ไม่เกิน 3 ช่อง และอีกออเดอร์ตั้งห่างเกิน 3 ช่องเพื่อทดสอบ Guardrail G5)
  4. สั่ง `/nego kss <order_no>` และ `/nego lib <order_no>` ผ่าน LINE:
     * ยืนยันว่าออเดอร์ที่ห่างเกิน 3 ช่องถูกข้าม (`⏭️ ห่างเกิน 3 tick`)
     * ยืนยันว่าออเดอร์ที่อยู่ในเกณฑ์ถูกแก้ราคาในที่สำเร็จ (`✅`) โดย **Order Number เดิมไม่เปลี่ยน** ทั้งบน Quick Trade (`kss`) และ WebTrade (`lib`)
     * บันทึกผลยืนยันการคลิก Submit จริงลงใน `quicktrade_driver.py` และปิดการ์ดทั้งหมดเป็น `DONE`
