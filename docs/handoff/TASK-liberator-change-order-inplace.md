# TASK-liberator-change-order-inplace: Liberator ต่อราคาแบบกด Change ในที่ (ไม่ cancel+replace)

- Created: 2026-10-09 by Antigravity (continued by Cline)
- Broker: Liberator (WebTrade) — account `7055932 (C)` = **CASH only** (Buy/Sell เท่านั้น, ไม่มี Short/Cover)
- Status: IN_PROGRESS
- ไฟล์ RCA ที่เกี่ยวข้อง: `rca/liberator/rca_liberator.md` (LIB-RCA-006/007 ที่มีอยู่)

## Context

**ปัญหา:** `LiberatorDriver.negotiate_price()` (driver.py ~L1013) ทำ **cancel + re-place** เพื่อ "ต่อราคา"
→ ได้ **order number ใหม่** เสียคิว (queue priority), เสี่ยง lost queue และ audit trail ไม่ตรงกับที่ user เห็นบนมือถือ

**เป้าหมาย:** เปลี่ยนเป็นกดปุ่ม **Change** บนแถว order เดิมใน `#OrderTableList`
→ **แก้ราคาในที่ (in-place)** คง order number เดิม ไม่มีการส่งคำสั่งใหม่

**User feedback (2026-10-09):** "ต่อราคา = กด Change บน order ที่มีอยู่ — order number เดิมไม่เปลี่ยน"
user จะเป็นคนวาง order ค้างเองจากมือถือ, โปรแกรมมีหน้าที่แค่ **กด Change**

### ข้อเท็จจริงที่พิสูจน์แล้ว (อัปเดต 2026-10-09 10:03-10:10 — มี order ค้างจริง)

> ⚠️ **Zero-Contradiction correction:** ข้อความเดิมที่ว่า *"ตารางว่าง rows=0 ... ไม่มี markup Change/Cancel ทั้งหน้า"*
> ถูก **ลบล้างแล้วด้วยหลักฐานสด** — ปุ่ม action render ต่อแถวก็จริง แต่เมื่อมี order จริง **markup โผล่ครบ**
> (recon รอบ 08:30 เจอตารางว่างเพราะยังไม่มี order ในคิวเท่านั้น) · งานที่เหลือ: อัปเดต runbook §5 ให้ตรงกับโค้ดใหม่

- Session `data/liberator_session.json` valid → เข้า `/Portfolio` ได้ (ไม่ต้อง OTP) · acct `7055932 (C)` CASH only
- ตาราง order = `#OrderTableList` (Vue, `data-v-6c619cd0`), **11 `<td>`**: `Order# | Time | Symbol | Side | Price | Volume | Matched | Balance | Cancelled | Status | <action>`
- **Order ค้างจริงที่ใช้ทดสอบ:** `#11894 | 10:03:21 | BCH | SELL | 12.00 | 4,000 | Matched 0 | Balance 4,000 | Cancelled 0 | Open`

#### Action cell จริง (ไม่มี id/role/title/aria เลย — text เท่านั้น)
```html
<td class="text-end"><div class="flex items-center justify-center gap-x-1 ms:gap-x-2 2xl:gap-x-3 mx:gap-x-4 text-equal">
  <div data-v-6c619cd0="" class="cursor-pointer"> Change </div>
  <div data-v-6c619cd0="" class="cursor-pointer"> Detail </div>
  <div data-v-6c619cd0="" class="cursor-pointer"> Cancel </div>
</div></td>
```

#### Selector matrix ที่พิสูจน์ด้วย `diag_change_locator.py` (empirical, ไม่เดา)
| Strategy | count |
| :--- | :--- |
| `td:last-child div.cursor-pointer` + `filter(has_text="Change")` (str) | **1 ✅** |
| `filter(has_text=re.compile(r"^Change$"))` | 0 ❌ |
| `filter(has_text=re.compile(r"^\s*Change\s*$"))` | **1 ✅** |
| `div:text-is("Change")` / `get_by_text(exact=True)` / `xpath normalize-space` | **1 ✅** |

#### 🪤 TRAP 1 — row anchor ห้ามใช้ `\b` regex
`textContent` ของ `<tr>` **ไม่มีช่องว่างระหว่าง cell**: `'1189410:03:21BCHSELL12.004,00004,0000Open Change  Detail  Cancel '`
⇒ `has_text=rb"\b11894\b"` = **0** (เพราะ `11894` ติดกับ `1` ของ `10:03:21` → ไม่มี word boundary)
✅ ใช้แทน: `#OrderTableList tbody tr:has(input[id='11894'])` (checkbox id = order number, exact) — resolver นี้ได้ row resolved=1

#### 🪤 TRAP 2 — duplicate ID `#volume` / `#price` / `#pin`
ใน DOM มี **สองชุด** (footer Buy/Sell panel **มาก่อน** → `page.locator("#price")` ไปโดน **ตัวผิด**)
| ตำแหน่งใน DOM | id | value | หมายเหตุ |
| :--- | :--- | :--- | :--- |
| แรก = footer | `#price` | `''` (ph=`Price ...`) | ❌ คนละฟอร์ม |
| หลัง = overlay | `#price` | `'12.00'` | ✅ ฟอร์ม amend |
⇒ **ต้อง scope ด้วย `div.overlay` เสมอ**

#### Amend overlay UI (path: กด Change → modal ไม่ใช่ footer)
```
div.overlay (class="overlay animate-slide-y p-2")  >  div.dialog  >  form
   h2 "Change Order Confirmation" · Symbol : BCH
   input#volume = '4000'  (disabled=False)
   input#price  = '12.00' (disabled=False)
   input#pin    = ''      (ต้องกรอก PIN = ยืนยันตัวตน)
   button (no id, class "rounded-[20px] bg-less-than ...") text='Cancel'
   button#confirmDialogActiveButton (class "rounded-[20px] bg-gradient-1 ...") text='Confirm'
```
- XHR ตอนกด Change: `POST /vb/stock/info` ×3, `POST /vb/stock/bid-offer`, `POST /vb/chart`, `POST /va/order`
- **หลักฐานว่า "กด Change" ไม่มี side-effect:** re-probe หลังคลิก 2 รอบ → order ยังเป็น `11894 BCH SELL 12.00 ×4,000 Open` เป๊ะ (ไม่ถูก cancel/แก้)

#### 🔴 บั๊กที่พบ (ต้องบันทึก RCA + ยังไม่แก้)
- `cancel_order()` (driver.py L999) ใช้ `button:has-text('Cancel'), [role='button']:has-text('Cancel'), svg.text-sell`
  → DOM จริงเป็น `<div class="cursor-pointer">` ⇒ **ไม่ match ตลอดกาล** = cancel ไม่เคยทำงาน (`svg.text-sell` ยังผิด Broker Knowledge Isolation)
- `LiberatorDriver` **ไม่มี `get_market_bid_offer()`** (มี 17 methods เท่านั้น) แต่ `pillar6_strategy`/`price_negotiation_service` เรียกผ่าน base → Liberator gap


#### 📈 API จริงของ Liberator (ค้นพบ 2026-10-09 10:20) — ใช้แทน scraping ได้
- `POST /vb/stock/info` body `{"orderBookIds":[65566]}` → ข้อมูลหุ้นเต็ม (last/prior/bid/offer/hi/lo/hi52/lo52)
- `POST /vb/stock/bid-offer` body `{"orderBookId":65566}` → **book 10 ระดับ** (`bp[]`/`bv[]`/`op[]`/`ov[]`)
- `POST /va/order` body `{"accountNo":"70559382"}` → list order ของบัญชี (ตอนกด Change) — **ไม่ใช่ write** (ยืนยัน: order ยัง `Open` ราคาเดิม)
- `POST /vb/chart` body `{"isLightweight":false,"orderBookId":65566,"resolution":"1D"}`
- **BCH orderBookId = 65566** · Board 2026-10-09 10:20: **Bid1 11.60 (258,200) / Offer1 11.70 (345,700)**
  · order #11894 ตั้ง SELL 12.00 = อยู่ Offer level 4 ซึ่ง**มี 2,943,000 หุ้นรอข้างหน้า** ⇒ แทบไม่ถูก fill
- ⚠️ ตาราง `Vol Bid Offer Vol` บน `/Portfolio` = board ของ symbol อื่น (อ่านได้ 1.15/1.94) **ห้ามใช้กับ order ในตาราง** (Anti-Mock)
- 💡 แนวทางปิดช่องว่าง `get_market_bid_offer()` ของ Liberator (Out of scope วันนี้): ใช้ 2 endpoint ข้างบนผ่าน `page.request.post` (cookie ติดไปเอง)



| Call-site | พฤติกรรมปัจจุบัน | สิ่งที่ต้องแก้ |
| :--- | :--- | :--- |
| `LiberatorDriver.negotiate_price()` (driver.py L1013) | scrape → `cancel_order()` → `execute_order()` ใหม่ | → กด Change in-place (step 6) |
| `LiberatorBrokerPlugin.negotiate_price()` (plugin.py L263) | passthrough + docstring "Adjusts unmatched order price" | แก้ docstring (step 8) |
| `app/brokers/liberator/cli.py::cmd_negotiate` (L117) | พิมพ์ `old_order_no` / `new_order_no` | แก้ output (step 9) |
| `app/services/action_exit_dispatcher.py::_run_autonomous_negotiation` (L171-188) | เช็ค `action == "RE_PEGGED"` + อ่าน `old_order_no`/`new_order_no` | **ต้องแก้** ไม่งั้นแจ้งเตือนอัตโนมัติเงียบหาย (step 7) |
| `app/mcp/pillars/pillar6_strategy.py::strategy_negotiate_unmatched_orders` | เรียก `trade_modify_price()` ซึ่งรองรับ **CLICK2WIN เท่านั้น** (Liberator ตกหล่น) | Open question — gap เดิม ไม่ใช่ของวันนี้ |

## Scope — ไฟล์ที่อนุญาตให้แก้

- `app/brokers/liberator/driver.py` (เพิ่ม `change_order()`, แก้ `negotiate_price()`, verify `cancel_order()`)
- `app/brokers/liberator/plugin.py` (เพิ่ม passthrough + แก้ docstring)
- `app/brokers/liberator/cli.py` (เพิ่ม subcommand + แก้ output)
- `app/services/action_exit_dispatcher.py` (ผู้บริโภค `action == "RE_PEGGED"` — ต้องแก้ตาม action ใหม่)
- `tests/test_liberator_change_order.py` (ใหม่)
- `scripts/verify_changes.py` (เพิ่ม `MODULE_TEST_MAP` สำหรับ plugin.py + cli.py)
- `learned_workflows/liberator/liberator_portfolio.md` (§5), `rca/liberator/rca_liberator.md`, `docs/daily/2026-10-09.md`
- `scripts/liberator/probe_order_change_button.py` (probe read-only รอบแรก)
- `scripts/liberator/probe_order_change_ui.py` (row actions + amend overlay; `--click-change` = เปิดฟอร์ม **ไม่ submit**)
- `scripts/liberator/diag_change_locator.py` (strategy matrix — พิสูจน์ selector ไม่เดา)

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome (จะเห็น/ตรวจอะไร) | Verify (test / หลักฐาน) | Status |
|---|----------------------------|------------------------------------|--------------------------|--------|
| 1 | Live DOM probe บน order ค้างจริง (#11894 BCH SELL 12.00 ×4,000) — **read-only** | log โชว์ control ต่อแถว: selector จริงของ Change + Cancel + row outerHTML | ✅ `/tmp/lib_probe4.log`, `/tmp/ui_readonly.log`, `data/liberator_order_row_11894.html` (+diag `/tmp/diag_loc.log`) | ✅ |
| 2 | Probe amend UI: **คลิก Change (ยังไม่ submit)** → dump สิ่งที่โผล่ + ต้องใส่ PIN ไหม | log โชว์โครง amend + selectors + ต้อง human confirm ก่อนคลิก | ✅ `/tmp/ui_click2.log`, `/tmp/ui_click3.log`, `data/liberator_amend_overlay.html`, `data/screenshots/liberator_amend_ui_probe.png` — user สั่ง "ลองต่อราคาได้เลย" | ✅ |
| 3 | เขียน `tests/test_liberator_change_order.py` (unit: resolver หา control ในแถว + flow `change_order` ด้วย page จำลอง) | `pytest` ผ่าน | `verify_changes.py --tests tests/test_liberator_change_order.py` | ⬜ |
| 4 | Implement `LiberatorDriver.change_order(order_no, new_price, new_volume=None)` ใช้ selector จริงจาก step 1-2 + resolver | method ใหม่ + unit test ผ่าน | `verify_changes.py app/brokers/liberator/driver.py` | ⬜ |
| 5 | เพิ่ม `MODULE_TEST_MAP` ของ `plugin.py` + `cli.py` (ชี้ `tests/test_liberator_change_order.py`) | verify_changes ไม่ขึ้น UNMAPPED อีก | `verify_changes.py --dry-run app/brokers/liberator/plugin.py app/brokers/liberator/cli.py` | ⬜ |
| 6 | Rewrite `negotiate_price()` → เรียก `change_order()` in-place (action=`AMENDED_IN_PLACE`, order_no เดิม) ตัด cancel+re-place | ไม่มีการเรียก `cancel_order` ในเส้นทางนี้ | `verify_changes.py app/brokers/liberator/driver.py` | ⬜ |
| 7 | แก้ `action_exit_dispatcher._run_autonomous_negotiation()` รองรับ `AMENDED_IN_PLACE` (เลิกอ่าน old/new order_no) | ไม่มี call-site ค้างเช็ค `RE_PEGGED` | `verify_changes.py --tests tests/test_krungsri_pdca_guardrails.py` | ⬜ |
| 8 | `plugin.py` เพิ่ม `change_order()` + แก้ docstring `negotiate_price` | plugin expose method ใหม่ | `verify_changes.py app/brokers/liberator/plugin.py` | ⬜ |
| 9 | `cli.py` เพิ่ม subcommand `change` + แก้ `negotiate` output (ไม่มี old/new order no แล้ว) | CLI พิมพ์ "amended in place #<เดิม>" | `verify_changes.py app/brokers/liberator/cli.py` | ⬜ |
|10 | **Live E2E**: กด Change บน order ค้างของ user → order id เดิม + ราคาใหม่ | หลักฐาน DOM + Order tab ของ broker + user เป็นพยาน | ✅ **2026-10-09 ~10:35** — `change_order("11894", 11.70)` → `success=true · action=AMENDED_IN_PLACE · status="Changed" · old ฿12.00 → new ฿11.70 · new_volume 4000` (`/tmp/live_amend.log`) · verify อิสระด้วย read-only probe (คนละโค้ด path, `/tmp/ui_after_amend.log`): `['11894','10:03:21','BCH','SELL','11.70','4,000','0','4,000','0','Changed','Change Detail Cancel']` · screenshot `data/screenshots/liberator_order_row_only.png` | ✅ |
|11 | Docs: อัปเดต runbook §5 (Zero-Contradiction), เพิ่ม `LIB-RCA-0xx`, สร้าง `docs/daily/2026-10-09.md` | ไม่มีขั้นตอน cancel+replace ค้างใน runbook | อ่านเทียบโค้ด (report-only) | ⬜ |
|12 | ปิดงาน: full suite **ครั้งเดียว** | ทุก test ผ่าน | ⚠️ **BLOCKED (known issue)** — `verify_changes.py --full` ค้างที่ **83%** (81% + 11 dots) นาน **6+ นาที** และ log **ไม่ขยับเลย** (331 bytes, mtime `10:31:04`) = SQLite lock บน `test_homelab.db` (`docs/handoff/TASK-verify-loop-hook.md`) → **kill ตามกฎ** `loop_engineering.md` §3 · หลักฐานทดแทน: targeted verify **89 passed** ครอบคลุมไฟล์ที่แก้ครบทั้ง 5 + live E2E ผ่าน | ⚠️ |

## Acceptance / Tests ที่ต้องผ่าน

- `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q`
- `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/brokers/liberator/cli.py`
- `.venv/bin/python scripts/verify_changes.py --full` (ครั้งเดียวตอนปิดงาน)
- หลักฐานสด: กด Change แล้ว **order number เดิม** ยังอยู่ + ราคาเปลี่ยน (DOM + broker Order tab) + user ยืนยัน

## Out of scope / ห้ามแตะ

- Logic การส่ง order ใหม่ / tick size / price-volume validation
- `execute_order()` การสร้าง order number ปลอม `f"LIB-{int(time.time())}"` (Anti-Mock violation) → บันทึกเป็น Open question เท่านั้น
- Krungsri / Click2Win / Settrade Open API
- Plaintext OTP logging (`driver.py`, `auth_driver.py:466`)
- Hardcoded credentials ใน `scripts/liberator/inspect_liberator_post_login.py` → Open question (security)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `app/brokers/liberator/driver.py` — เพิ่ม `change_order()` + `_amend_order_in_place()` + `_order_action_locator()` + `_parse_order_row_cells()` + `_amend_guard()` + class constants (`LIB_ORDER_TABLE`/`LIB_AMEND_ACTION`/`LIB_AMEND_OVERLAY`/`LIB_CONFIRM_BUTTON`/`LIB_AMENDABLE_STATUSES`); rewrite `negotiate_price()` ให้ amend in-place (action `AMENDED_IN_PLACE`, no-op guard `NONE`, ตัด `cancel_order()`+`execute_order()` ออก); แก้ `cancel_order()` ให้ใช้ `_order_action_locator()` (LIB-RCA-018)
  - `app/brokers/liberator/plugin.py` — เพิ่ม `change_order()` passthrough + แก้ docstring `negotiate_price()`
  - `app/brokers/liberator/cli.py` — เพิ่ม subcommand `change` (`cmd_change`) + แก้ output ของ `cmd_negotiate` (เลิกอ่าน `old_order_no`/`new_order_no`)
  - `app/services/action_exit_dispatcher.py` — `_run_autonomous_negotiation()` รองรับ `AMENDED_IN_PLACE` + `NONE` (เลิกเช็ค `RE_PEGGED`)
  - `tests/test_liberator_change_order.py` — **ใหม่** (20 tests)
  - `scripts/verify_changes.py` — `MODULE_TEST_MAP` เพิ่ม `driver.py`(+test ใหม่)/`plugin.py`/`cli.py`/`action_exit_dispatcher.py`
  - `scripts/liberator/probe_order_change_ui.py` — **ใหม่** (probe row actions + amend overlay + market depth + API capture; `--click-change` เปิดฟอร์มแต่ไม่ submit)
  - `scripts/liberator/diag_change_locator.py` — **ใหม่** (selector strategy matrix)
  - `scripts/liberator/run_change_order_live.py` — **ใหม่** (live E2E runner, มี `--dry-run`)
  - `learned_workflows/liberator/liberator_portfolio.md` — §5 เขียนใหม่ (in-place + selectors + 2 traps)
  - `rca/liberator/rca_liberator.md` — เพิ่ม `LIB-RCA-016` / `LIB-RCA-017` / `LIB-RCA-018`
  - `docs/handoff/TASK-liberator-change-order-inplace.md` — อัปเดต facts/steps/evidence
  - `docs/daily/2026-10-09.md` — **ใหม่**
  - หลักฐาน: `data/liberator_order_row_11894.html`, `data/liberator_amend_overlay.html`, `data/screenshots/liberator_amend_ui_probe.png`, `data/screenshots/liberator_order_row_only.png`
- Summary:
  - "ต่อราคา" เปลี่ยนจาก **cancel + re-place** (ได้ order number ใหม่) → **กดปุ่ม Change ของโบรกเกอร์ = แก้ในที่** (order number + คิวเดิมคงอยู่)
  - Success ต้องผ่านการ **re-read `#OrderTableList` แล้วยืนยันราคาใหม่บน order number เดิม** เท่านั้น (Anti-Mock: ไม่งั้นคืน `AMEND_UNVERIFIED`)
  - 2 กับดักที่บันทึกเป็น RCA: row anchor ห้ามใช้ `\b`-regex (LIB-RCA-016), ฟิลด์ `#price`/`#volume`/`#pin` ซ้ำ 2 ชุดต้อง scope `div.overlay` (LIB-RCA-017)
- Tests run + result:
  - `.venv/bin/python scripts/verify_changes.py app/brokers/liberator/driver.py app/brokers/liberator/plugin.py app/brokers/liberator/cli.py app/services/action_exit_dispatcher.py scripts/verify_changes.py` → **PASS (89 passed in 42.6s)**
  - `.venv/bin/python -m pytest tests/test_liberator_change_order.py -q` → **17 passed** (ก่อนเพิ่ม test ของ `negotiate_price`; รวมเป็น 20)
  - **Live E2E:** `change_order("11894", 11.70)` → `success=true · action=AMENDED_IN_PLACE · status=Changed · ฿12.00 → ฿11.70` (order number เดิม) — log `/tmp/live_amend.log`
  - **Independent verify** (read-only probe คนละโค้ด path): `['11894','10:03:21','BCH','SELL','11.70','4,000','0','4,000','0','Changed','Change Detail Cancel']` — `Order #` และ `Time` เดิมทั้งคู่ ⇒ ยืนยันว่าไม่ได้ส่งคำสั่งใหม่ — log `/tmp/ui_after_amend.log`
  - **Live smoke (zero submission):** `negotiate_price(target_price=11.70)` → `action=NONE` — log `/tmp/live_neg.log`
  - Step 12: `.venv/bin/python scripts/verify_changes.py --full` → ⚠️ **ค้างที่ 83% นาน 6+ นาที** (log 331 bytes ไม่ขยับ, mtime `10:31:04`) = known issue SQLite lock → kill ตามกฎ `loop_engineering.md` §3 · ทดแทนด้วย targeted verify (**89 passed**) ซึ่งครอบคลุมไฟล์ที่แก้ครบทั้ง 5 ไฟล์
- Open questions:
  1. `LiberatorDriver` **ไม่มี `get_market_bid_offer()`** (17 methods) แต่ `pillar6_strategy.py` / `price_negotiation_service.py` เรียกผ่าน base → รันบน Liberator จะล้ม แนะนำ implement ด้วย `POST /vb/stock/bid-offer` (`{"orderBookId":65566}`) ผ่าน `page.request.post` (cookie ติดไปเอง) — **นอก scope วันนี้**
  2. `cancel_order()` แก้ selector แล้ว (LIB-RCA-018) แต่ **ยังไม่ live-test** เพราะต้องมี order ที่ user ยอมให้ยกเลิกจริง → ต้องทำ HITL test แยก
  3. Anti-Mock เดิมยังอยู่: `driver.py` `execute_order()` สร้าง `broker_order_no = f"LIB-{int(time.time())}"` เมื่อหา order ในตารางไม่เจอ (บรรทัด ~L911) — ควรเปลี่ยนเป็น error/PENDING status
  4. `scripts/liberator/inspect_liberator_post_login.py` ยังมี credential ฮาร์ดโค้ด (security)
  5. Plaintext OTP logging (`driver.py`, `auth_driver.py:466`) ยังไม่แก้ (parked ตามข้อตกลง)
  6. `--full` เคยค้าง ~87% จาก SQLite lock (`docs/handoff/TASK-verify-loop-hook.md`) — งานนี้รันแล้วดูผลในหัวข้อ Tests
  7. ยังไม่มี `EventBus`/SSE broadcast สำหรับ amend (runbook §5 ข้อ 7 เขียนว่ามี log + push เท่านั้น) — ถ้าต้องการ Cockpit SSE ต้องเพิ่มเป็นงานถัดไป

---

## Antigravity Review
- Verdict: PASS / CHANGES_REQUESTED
- Notes:
