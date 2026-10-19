# TASK-loop1-7 — TradeMan Order Ticket: DOM Probe + แก้ execute_order + Re-Witness (Cancel + Re-submit)

> **สถานะ:** PLAN (รออนุมัติเริ่ม)
> **Tier:** T1 (Jules 3.1 Pro)
> **Scope:** แก้เฉพาะ path สั่งซื้อ (Order Ticket) ของ TradeMan — ห้ามแตะ cancel path (ผ่านแล้ว), ห้ามแตะ quote path (ผ่านแล้ว)
> **Relates:** TASK-loop1-6 (guardrails C1–C7), KSS-RCA-006 (Anti-DW), KSS-RCA-018 (bypass_dry_run)

## 1. Root Cause (จาก witness จริง 2026-10-19 15:43)

| ขั้น | ผล |
|---|---|
| cancel #11020310 | ✅ PASS — `ORDER_CANCELLED` (15:43:46) |
| re-submit COVER 100 BCPG @6.75 | ❌ `CRITICAL Anti-DW Assertion Failed: Active symbol is 'BBL', expected exact 'BCPG'` |
| fallback @6.70 | ❌ โดนสกัดซ้ำ (symbol ยังเป็น BBL) |

**สาเหตุ:** `execute_order` Tier 1 คลิก `<td>` ที่มีข้อความ `BCPG` ในตารางพอร์ตสำเร็จ (เราถือ short BCPG อยู่) แต่ **การคลิกแถว holdings ไม่ได้ตั้ง symbol ใน ticket** — ticket ยังค้างค่า `BBL` (จากคุณกดดู quote BBL ก่อนหน้าใน browser ตัวเดียวกัน) → Tier 2 (search modal) ไม่ได้รันเพราะ Tier 1 "สำเร็จ" → Tier 3 จับได้และ abort

**ข้อดี:** Anti-DW ทำงานถูกต้อง — **ไม่เกิดคำสั่งผิดหุ้น** (fail-closed ตามออกแบบ)

**ช่องว่างที่แท้จริง:** เรา **ไม่เคย probe DOM ของ Order Ticket (ช่อง Buy/Sell) เลย** — probe ที่ผ่านมาครอบคลุมแค่ View Order + ปุ่ม Cancel + หน้า quote

## 2. ขั้นตอน (numbered)

### 1.1 PROBE — Order Ticket DOM (read-only, headed, ไม่ส่งคำสั่ง)

**File:** `scripts/krungsri/probe_order_ticket.py` (ใหม่, ตามแพทเทิร์น `probe_vieworder_actions.py`)
**รัน:** หลัง login สด, ตลาดเปิดหรือปิดก็ได้ (panel มีตลอด)

Dump ลง `docs/artifacts/`:

- [ ] Symbol box: element ที่แสดง symbol ปัจจุบัน (คาด `div` ที่ class มี `bg-[#2B313A]` ลูกของ label "Symbol") + innerText + outerHTML
- [ ] ทดสอบ: คลิกแถว `BCPG` ในตารางพอร์ต → อ่าน symbol box ซ้ำ → **บันทึกว่าเปลี่ยนหรือไม่** (ยืนยันสมมติฐาน root cause)
- [ ] ทดสอบ: คลิก symbol box → search modal (`.v-overlay--active`) เปิดไหม, มี filter `Stock`, มี input ค้นหา
- [ ] ทดสอบ: พิมพ์ `BCPG` ใน modal → list ผลลัพธ์, ตัวเลือก exact match (`BCPG` เป๊ะ) มีไหม, คลิกแล้ว modal ปิดและ symbol box เปลี่ยนเป็น BCPG ไหม
- [ ] Side buttons: `Buy / Sell / Short / Cover` — selector ที่ใช้ `span:text-is('COVER')` เจอจริงไหม (COVER ต้องมี short position ถึงจะ active)
- [ ] Inputs: `input[id$='-order-volume']`, `input[id$='-order-price']` มีค่า placeholder/ค่าค้างอะไร
- [ ] Send: `#send_order__btn` มี/ไม่มี; Order Confirm modal มี input `#pin` ไหม (ห้ามกด Send ใน probe)

**Done-when:** artifact แสดง DOM จริงของทั้ง 7 ข้อ + รู้ว่าคลิกแถว holdings ตั้ง symbol ได้หรือไม่

### 1.2 FIX — `execute_order` symbol selection (Tier 1 → Tier 2 fallthrough)

**File:** `app/browser/trademan_driver.py` (เฉพาะฟังก์ชัน `execute_order`)
**Rule ใหม่:**

- Tier 1 (คลิก td) หลังคลิก → **รัน Tier 3 assertion ทันที**; ถ้า symbol ไม่ตรง → **fallthrough ไป Tier 2** (ห้ามเชื่อว่า Tier 1 สำเร็จ)
- Tier 2 (search modal) → หลังคลิก exact match → รอ modal ปิด → **รัน Tier 3 อีกครั้ง**; ยังไม่ตรง → abort (`REJECTED`)
- Log ทุก tier: `T1 table_click=<bool> → T3=<sym> | T2 modal_open=<bool> exact_click=<bool> → T3=<sym>` (debug ได้โดยไม่ต้องเปิด trace)
- **ห้าม** ส่งคำสั่งถ้า Tier 3 ไม่ผ่าน (คงเดิม)

**Done-when:** diff ผ่าน review, `scripts/verify_changes.py app/browser/trademan_driver.py` ผ่าน

### 1.3 UNIT TESTS (FakePage)

**File:** `tests/test_trademan_driver.py` (เพิ่ม)
**Case:**

1. T1 คลิก td ได้ แต่ ticket ยัง `BBL` → T2 รัน → exact match `BCPG` → **ไม่ abort** (proceed)
2. T2 หา exact match ไม่เจอ → `REJECTED` (Anti-DW)
3. T2 คลิกแล้ว แต่ Tier 3 ยัง `BBL` → `REJECTED`
4. (regression) T1 คลิกแล้ว symbol เปลี่ยนเป็น BCPG → T2 ไม่ต้องรัน → proceed (เร็วขึ้น)

**Done-when:** `pytest tests/test_trademan_driver.py -q` ผ่านทั้งหมด

### 1.4 PRE-WITNESS DRY-EXEC (DOM จริง, ไม่ส่งจริง)

**วิธี:** `DRY_RUN_MODE=True` → `execute_order("BCPG","COVER",100,6.75)` ผ่านสคริปต์ในเครื่อง
→ ระบบจะ **กรอกฟอร์มจริงบน DOM จริง** แล้วหยุดก่อนกด Send (คืน `SIMULATED_SUCCESS`)
→ ใช้พิสูจน์ว่า chain T1→T3 ทำงานบนหน้าเว็บจริงโดยไม่มีความเสี่ยง

**รันได้:** หลัง login สด ตลาดเปิดหรือปิดก็ได้

**Success criteria:**
- log แสดง `T2 exact_click=True → T3=BCPG` (หรือ T1→T3=BCPG)
- result `SIMULATED_SUCCESS` และ **ไม่มี** log `Anti-DW Assertion Failed`

### 1.5 LIVE WITNESS (cancel + re-submit จริง — ต้องอนุมัติมนุษย์)

**Preconditions:**
- `TRADING_MODE=LIVE`, `DRY_RUN_MODE=false`, `KSS_AMEND_MODE=trademan_cancel_replace` (สถานะ .env ปัจจุบัน)
- login สด (OTP)
- **วางออเดอร์ทดสอบเอง:** `BUY BCPG 100 @ <bid − 1 tick>` (ไม้เดียว, ค้างไม่ fill)
- ⚠️ **ห้าม browse หุ้นอื่นใน browser ของ gateway** ก่อน witness (แม้ 1.2 จะทำให้ robust แล้ว แต่ลดตัวแปร)

**รัน:** `/nego kss <order_no>`

**Success criteria (ต้องครบทุกข้อ):**
1. การ์ดรายงาน `#old → #new @ <target>` + `ORDER_CANCELLED` ใน audit DB
2. `scrape_unmatched_orders` เห็น order ใหม่: symbol=BCPG, side=BUY, volume=100, price=target ที่ถูกต้อง (ไม่ใช่ BBL ไม่ใช่ราคาผิด)
3. `scrape_all_orders` เห็น old=Canceled และ new=Open (1 cancel + 1 submit เท่านั้น)
4. audit: `ORDER_SUBMITTED_LIVE` พร้อม order_no จริง (ห้ามมี `SUBMITTED_UNVERIFIED`)

### 1.6 FAILURE PLAYBOOK (ถ้าไม่สำเร็จ — ตรวจตามลำดับ)

| อาการ | ตรวจ |
|---|---|
| `Anti-DW Assertion Failed` | ดู tier log ใหม่ (1.2) → เปิด DOM ดู symbol box innerText → เทียบกับ artifact 1.1 |
| `Submit button not found` | `send_order__btn` มีไหม, panel Buy/Sell เปิดอยู่ไหม |
| `Order Confirm modal` ไม่ขึ้น | overlay text จริงคืออะไร (dump `.v-overlay--active` innerText) |
| PIN reject / toast error | อ่าน toast text เต็ม, เช็ค PIN ใน .env |
| `SUBMITTED_UNVERIFIED` | อ่าน ledger ด้วยมือ + MCP `current_open_orders` — ห้าม retry ทันที (กัน order ซ้ำ) |
| cancel สำเร็จแต่ resubmit fail | **ห้าม retry เองอัตโนมัติ** → แจ้งมนุษย์ + บันทึกหลักฐาน → กลับไป 1.1/1.2 |

## 3. Timeline เสนอ

- **คืนนี้/เช้า (ไม่ต้องรอตลาด):** 1.1 (probe หลัง login) → 1.2 (fix) → 1.3 (tests) → 1.4 (dry-exec บน DOM จริง)
- **พรุ่งนี้ 14:25–16:30:** 1.5 live witness (หรือ 09:55–12:30)

## 4. สถานะพอร์ตปัจจุบัน (บันทึก)

- short BCPG 100 (entry 6.80) ยังเปิดอยู่ — ไม่มีความเสียหายจาก witness วันนี้
- ไม่มี open orders ค้าง
- `#11020310` COVER ถูก cancel แล้ว (สำเร็จ)
