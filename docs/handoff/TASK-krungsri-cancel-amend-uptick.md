# TASK-krungsri-cancel-amend-uptick: Real Cancel/Amend + Strict SHORT Uptick (Krungsri TradeMan)

- Created: 2026-10-09 by Antigravity (in-chat plan; ไฟล์ handoff นี้สร้างตอนปิดงานเพื่อบันทึกตาม Handoff protocol)
- Broker: Krungsri (TradeMan) — **Broker Knowledge Isolation**: ทุกอย่างในไฟล์นี้ใช้กับ TradeMan เท่านั้น
- Status: DONE (ยกเว้น end-to-end live browser verify — ดู Open questions)

## Context (Antigravity เขียน)
- `trademan_driver.execute_order()` คืน `order_id` **สังเคราะห์** รูป `ORD-<epoch>` → cancel/amend อ้างอิงได้ไม่จริง (Anti-Mock violation)
- TradeMan **ไม่มีปุ่ม "Change"** → amend ต้อง = Cancel + Re-submit (พิสูจน์สด 2026-10-09)
- กฎ SET Short Uptick ใน repo **หลวม** (`>= last`) และ `price_negotiation_service` **ปั้น `last`** จากราคาคำสั่งตัวเอง
- RCA: [`KSS-RCA-016` / `KSS-RCA-017`](../../rca/krungsri/rca_krungsri_trademan.md)

## Scope — ไฟล์ที่อนุญาตให้แก้
- `app/browser/trademan_driver.py`, `app/brokers/krungsri/plugin.py`
- `app/services/validator.py`, `app/services/price_negotiation_service.py`
- `tests/test_validator.py`, `tests/test_trade_negotiation.py`
- `scripts/verify_changes.py` (MODULE_TEST_MAP)
- runbook + RCA (`learned_workflows/krungsri/*.md`, `rca/krungsri/rca_krungsri_trademan.md`)

## Steps / Task Decomposition (Loop Engineering — บังคับ)

| # | Atomic Step (หนึ่ง action) | Expected Outcome | Verify | Status |
|---|----------------------------|------------------|--------|--------|
| 1 | `execute_order` อ่าน `Order No.` จริงกลับ (ลบ `ORD-<epoch>`) | คืน id จริงจาก ledger / ไม่มี id สังเคราะห์ | อ่านซอร์ส + `verify_changes.py app/browser/trademan_driver.py` | ✅ |
| 2 | `plugin.py` ต่อสาย `cancel_order` / `modify_order_price` | plugin เรียก driver ได้จริง | `verify_changes.py app/brokers/krungsri/plugin.py` → PASS | ✅ |
| 3 | `validator.validate_short_uptick` → strict (`price <= last` = reject) | `8.20 == 8.20` → `ok is False`; min = `get_next_tick(last,1)` | `tests/test_validator.py::test_short_uptick_rule` | ✅ |
| 4 | อัปเดตเทสต์ validator (equality → False) | เทสต์สะท้อนกฎ strict ใหม่ | `verify_changes.py app/services/validator.py` → PASS | ✅ |
| 5 | แก้ comment + `minimum_price` ใน driver | comment = "strictly above, ไม่มี zero-plus tick"; payload min = last+1 tick | อ่านซอร์ส 1467–1500 | ✅ |
| 6 | negotiation SHORT: ห้ามปั้น `last` + fail-closed | `last` หาย → `needs_review=True`, ไม่เสนอปรับราคา | 5 เทสต์ใหม่ใน `tests/test_trade_negotiation.py` | ✅ |
| 7 | negotiation SHORT: skip เมื่อราคาอยู่ที่ best offer / +1 tick | `current <= offer_1 + 1 tick` → `needs_adjustment=False` | เทสต์ skip ×2 | ✅ |
| 8 | negotiation SHORT: `target = max(offer_1, last + 1 tick)` + re-validate SSOT | target ผ่าน `validate_short_uptick` เสมอ | เทสต์ floor / reprice | ✅ |
| 9 | เพิ่ม `MODULE_TEST_MAP` สำหรับ 4 ไฟล์ที่แก้ | `verify_changes.py` ไม่คืน `UNMAPPED` | `verify_changes.py --dry-run` | ✅ |
| 10 | อัปเดต runbook §C (Zero-Contradiction) | runbook ตรงกับโค้ด | อ่านเทียบโค้ด | ✅ |
| 11 | บันทึก RCA/PDCA + guardrail ใหม่ | `KSS-RCA-016` / `KSS-RCA-017` + กฎเหล็กข้อ 13/14 | อ่านไฟล์ RCA | ✅ |

## Acceptance / Tests ที่ต้องผ่าน
- `.venv/bin/python scripts/verify_changes.py app/services/validator.py app/services/price_negotiation_service.py app/browser/trademan_driver.py app/brokers/krungsri/plugin.py` → exit 0
- `.venv/bin/python -m pytest tests/test_validator.py tests/test_trade_negotiation.py -q`

## Out of scope / ห้ามแตะ
- Order placement logic อื่น / tick-size table / price-volume validation นอกเหนือ uptick
- BUY/COVER Bid-1 & SELL Offer-1 pegs ของ TradeMan **ไม่มี depth จริง** (out of scope — depth ต้องมาจาก realtime hub)
- Click2Win / Liberator (Broker Knowledge Isolation)

---

## Cline Report (Cline เขียน)
- Files changed:
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/validator.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_validator.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/trademan_driver.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/brokers/krungsri/plugin.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/price_negotiation_service.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_trade_negotiation.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/verify_changes.py`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/learned_workflows/krungsri/krungsri_market_open_operational_runbook.md`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/krungsri/rca_krungsri_trademan.md`
  - `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-verify-loop-hook.md`
- Summary:
  - **Cancel/Amend จริง**: `execute_order` คืน `Order No.` จริง (read-back), amend = cancel + re-submit (row-scoped บน `Order No.`, PIN-confirmed), plugin ฝั่ง Krungsri ต่อสายครบ
  - **Strict SHORT Uptick (SSOT เดียว)**: `validate_short_uptick` reject `price <= last`; minimum = `get_next_tick(last, 1)`; driver delegate ไปที่ SSOT และรายงาน `minimum_price` ใน reject payload
  - **SHORT Negotiation ปลอด Anti-Mock**: ไม่ปั้น `last` (fail-closed → `needs_review`), skip เมื่อคำสั่งอยู่ที่ best offer หรือ +1 tick (ตามที่ผู้ใช้ยืนยัน), target = `max(offer_1, last + 1 tick)` แล้ว re-validate ผ่าน SSOT
  - **Zero-Contradiction**: runbook §C, RCA `KSS-RCA-016/017`, กฎเหล็กข้อ 13/14
- Tests run + result:
  - `scripts/verify_changes.py app/services/validator.py app/services/price_negotiation_service.py app/browser/trademan_driver.py app/brokers/krungsri/plugin.py` → **PASS (exit 0)** · `29 passed in 11.72s` (targeted: test_validator, test_trade_negotiation, test_tpsl_overview_negotiate_api, test_trademan_view_order_scraper, test_pillar2_order_ledger, test_broker_registry) · `compileall: OK`
  - `scripts/verify_changes.py --full` → **ค้างที่ ~83% (561.9s) → kill -9** = known issue (SQLite lock บน `test_homelab.db`; fd ค้าง 2 ตัว + `wchan=ep_poll`) บันทึกเพิ่มใน `TASK-verify-loop-hook.md` Open questions #1 (run #3)
- Open questions:
  1. **End-to-end live browser verify ยังไม่ได้ทำ** (DRY_RUN cancel + amend บน TradeMan จริง) — ต้องมี human confirm + session/PIN สด (Invariant 4/9) → ยังไม่นับว่า "เสร็จ" ระดับ hardware
  2. `--full` ยังค้าง (known issue เดิม ยังไม่แก้) — ใช้ targeted mode เป็นหลัก
  3. TradeMan quote API ไม่มี bid/offer depth → BUY/COVER (Bid 1) และ SELL (Offer 1) pegs เป็น no-op บนโบรกเกอร์นี้ (นอก scope)
  4. กฎ strict uptick นี้ **เฉพาะ Krungsri TradeMan** — Liberator/Click2Win มี SSOT คนละไฟล์ ยังไม่ตรวจ (Broker Knowledge Isolation; ห้าม assume ตาม)

---

## Live E2E Verification — Gate Log (2026-10-09, LIVE TradeMan amend)

> เป้าหมาย: ปิด **Open question #1** — พิสูจน์ amend จริง (Cancel + Re-submit + PIN) บน TradeMan สด
> แผน **L2** (6 gates) · Broker: Krungsri TradeMan เท่านั้น (**Broker Knowledge Isolation**)

### Gate 0 — Preflight & OTP Relay Readiness ✅ PASS (2026-10-09 12:17 BKK)

| การตรวจ | ผล | หลักฐาน |
|---|---|---|
| `scripts/preflight_check.py` | **EXIT=0 (GO)** | ข้อ 1 Backend RUNNING · ข้อ 5 Liberator active |
| OTP relay (`otp_relay_readiness.check()`) | **ready=True** | `channel=line_direct` · `line_direct_reachable=True` · `line_direct_probe='reachable'` · target `U93d3…4bd2` · `gateway_up=True` |
| KDE Connect phone | not reachable | 🔴 **ไม่กระทบ** — gate ใช้ `allow_kde_fallback=False` (LINE authoritative, `LINE-RCA-009`) |
| `data/session_state.json` | **MISSING** | ต้อง fresh login + SMS OTP |
| Effective settings (`import app.core.config.settings`) | `TRADING_PLATFORM=CLICK2WIN` (ต้องสลับเป็น `TRADEMAN`) · `TRADING_MODE=TEST` · `DRY_RUN_MODE=True` · `PLAYWRIGHT_HEADLESS=False` · `LIVE_ORDER_VALUE_LIMIT_THB=50000` · `OTP_TIMEOUT_SECONDS=180` | creds: `KRUNGSRI_USER/PASS/PIN set=True` · `TRADING_PIN set=True` |

**ยืนยันจากโค้ดจริง (Zero-Contradiction):**
- `auth_driver.login()` L365–398: gate = `otp_relay_readiness.check(allow_kde_fallback=False)` → relay ready ⇒ เดินต่อได้ (ไม่ abort `BRIDGE_DOWN`)
- login push คำขอ OTP เข้า LINE 1:1 อัตโนมัติ (มี ref) → **ต้องมีคนส่งรหัสจาก SMS ลง LINE ภายใน 180s**
- `trademan_driver.modify_order_price()` L1404–1418: DRY_RUN guard = `settings.DRY_RUN_MODE and not bypass_dry_run`
  ⇒ rehearsal = `bypass_dry_run=False` · LIVE จริง = `bypass_dry_run=True`
- Router จริง = `/api/v1/phase3/scenario/negotiation/{live-orders,execute-direct}` (`app/api/v1/api.py` L22 `prefix="/phase3"`)
- runbook §C ตรงกับโค้ด (strict uptick `> last`, fail-closed, skip เมื่ออยู่ที่ offer/+1 tick) — ไม่มี contradiction

### Gate 0 decision (ผู้ใช้, 2026-10-09 ~12:22 BKK)
- ⛔ **ไม่ login ตอนนี้** — ผู้ใช้เลือก **รอเปิดตลาดรอบบ่าย 14:30** แล้วเริ่มทั้งหมด (login + amend) ในทีเดียว
- เหตุผลเชิงเวลา: 12:22 → ตลาดพัก 12:30 (เหลือ ~8 นาที) ไม่พอทำ live amend ให้ปลอดภัย
- **Invariant 9:** ไม่ยิง SMS OTP จนกว่าจะมีคนพร้อม relay จริง ✅ (ไม่เสีย OTP / ไม่เสี่ยง account lock)

### Run sequence สำหรับ 14:30 (พร้อมรัน — ยังไม่ execute)

| Gate | การกระทำ | Expected Outcome | หลักฐานที่ต้องเก็บ |
|---|---|---|---|
| **1** | `switch_platform("TRADEMAN")` → `browser_open` (headed) → `broker_login("TRADEMAN")` → พิมพ์ OTP จาก SMS ลง LINE (≤180s) → `trademan_check_session()` | session `RECENT/FRESH` + เห็น equity จริง (ห้าม mock) · ถ้า `BRIDGE_DOWN` → หยุด + แจ้ง (ไม่วนซ้ำ) | screenshot จอ TradeMan + ค่า equity |
| **2** | read-only: `GET :8000/api/v1/phase3/scenario/negotiation/live-orders` (หรือ `scrape_orders(platform="KRUNGSRI")`) | เห็น order ค้างจริงพร้อม `broker_order_no` (0 orders = ไม่ใช่ error) | JSON response |
| **3** | DRY_RUN: `POST .../execute-direct` body `{broker_order_no,symbol,side,new_price,volume,bypass_dry_run:false}` | `status="SIMULATED_MODIFIED"` + SessionLog `ORDER_NEGOTIATION_DRY_RUN` · 🛑 **HALT ขอ confirm ผู้ใช้** | response + SessionLog row |
| **4** | LIVE: `trade_dispatcher.switch_mode("LIVE", pin=…)` → `POST .../execute-direct` body `{..., bypass_dry_run:true}` | cancel (PIN) + re-submit (PIN) สำเร็จ · `CANCEL_FAILED` ⇒ amend abort อัตโนมัติ (ไม่ duplicate position) | before/after `Order No.` + screenshot |
| **5** | REFLECT | บันทึก `KSS-RCA-0xx` + อัปเดต runbook §C (Zero-Contradiction) + เติม Cline Report | diff ของ 2 ไฟล์ |

**Guardrails ที่ยังทำงานในรอบ LIVE:** `LIVE_ORDER_VALUE_LIMIT_THB=50,000` · strict SHORT uptick (fail-closed) · PIN/OTP ไม่ถูก log/แสดง · SHORT เท่านั้นที่มี uptick gate (BUY/SELL ไม่ติด)

> ⚠️ **Safety note (สำคัญ — อ่านจากโค้ดจริง):** `phase3.execute_direct_price_modification` hard-code `force_live=True` และ
> `dispatch_price_modification` ตัดสินเส้นทางด้วย `is_live_exec = self.is_live or force_live`
> ⇒ **โหมด TEST ไม่กันคำสั่งนี้** ถ้าส่ง `bypass_dry_run=true` เข้า `execute-direct` มันจะยิง LIVE ทันที
> (`modify_order_price` L1404 จะข้าม DRY_RUN guard). ดังนั้น **ตัวกันจริงของ Gate 4 = `bypass_dry_run=true`**
> → ห้ามส่ง flag นี้ก่อนได้ human confirm + คำสั่งชัดเจนในแชท · Gate 3 (rehearsal) ต้องเป็น `false` เท่านั้น

### Open questions (Live E2E)
1. **ต้องได้จากผู้ใช้ก่อน 14:30:** คำสั่งค้างจริงบน TradeMan (symbol / side / ราคาที่ค้าง / volume / `Order No.`) + PIN พร้อม + มือถือพร้อมรับ SMS OTP
2. ถ้า TradeMan **ไม่มีคำสั่งค้าง** → พิสูจน์ได้แค่ DRY_RUN + uptick-reject path (ยังไม่นับ hardware verify ตาม Invariant 4)
3. Live amend จะแตะเงินจริง — ต้องมีคำสั่งชัดเจนในแชทของ task นั้น (Trading safety) และ human confirm ก่อน Gate 4 เสมอ
4. `--full` suite ยังค้าง (SQLite lock) — ใช้ targeted `verify_changes.py` ระหว่างรอบนี้

---

## Cline Report — Addendum #2: P0 Amend Guard Fix (`KSS-RCA-018`) + Live Attempt (2026-10-09)

> ต่อจาก Gate Log ด้านบน · Broker: Krungsri TradeMan เท่านั้น (**Broker Knowledge Isolation**)
> รอบนี้ = **P0 hotfix** ของบั๊กที่พบตอนเตรียม Gate 4 (ปิดช่องที่ Gate 4 กำลังจะเหยียบ) + ลอง LIVE 1 รอบ

### Files changed (รอบนี้)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/browser/trademan_driver.py`
  - `execute_order()` L566–575: เพิ่มพารามิเตอร์จริง `bypass_dry_run: bool = False` (+ docstring)
  - L624: `if settings.DRY_RUN_MODE and not bypass_dry_run:` (เดิมเป็น `if settings.DRY_RUN_MODE:`)
  - L746–748: guard ก่อนคลิก Send → `if settings.DRY_RUN_MODE and not bypass_dry_run:`
  - L1524: `modify_order_price` ส่ง `bypass_dry_run=bypass_dry_run` เข้า `execute_order`
  - L582 / L747: แก้ comment ref `KSS-RCA-017` → `KSS-RCA-018` (Zero-Contradiction)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/tests/test_trademan_amend_bypass_dryrun.py` — **ใหม่** (2 tests)
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/scripts/verify_changes.py` — เพิ่มไฟล์ใหม่ใน `MODULE_TEST_MAP`
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/krungsri/rca_krungsri_trademan.md` — registry row + Deep Dive `KSS-RCA-018` + กฎเหล็กข้อ 15
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/rca/shared/rca_gateway_lifecycle.md` — `GW-RCA-003` + Zero-Contradiction checklist
- `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/docs/handoff/TASK-krungsri-cancel-amend-uptick.md` — ไฟล์นี้

### Summary — P0 bug & fix
- **บั๊ก (position-loss)**: `modify_order_price` / `cancel_order` gate DRY_RUN ด้วย `and not bypass_dry_run` (จึง **ยกเลิกคำสั่งจริงได้**) แต่ `execute_order` **ไม่มีพารามิเตอร์ `bypass_dry_run`** และมี `**kwargs` → flag ถูก **กลืนเงียบ** → ตกด่าน DRY_RUN → คืน `SIM-<epoch>` โดยไม่ส่งคำสั่งใหม่ ⇒ **position หายถาวร** ขณะที่ caller ได้ `success=True`
- **แก้**: เพิ่มพารามิเตอร์จริง + gate ทั้ง 2 จุดของ `execute_order` ด้วย `not bypass_dry_run` + ส่ง flag ต่อจาก `modify_order_price` ให้ครบทั้ง cancel และ submit (**Symmetric Guards**)
- **สถานะ**: 🟢 โค้ด + เทสต์ (verified) · 🟡 **LIVE round-trip ยังไม่พิสูจน์** (ดู Open questions #1)

### Tests run + result
| คำสั่ง | ผล |
|---|---|
| `scripts/verify_changes.py app/browser/trademan_driver.py` (targeted, ต่อ unit) | **PASS (exit 0)** · `29 passed` · `compileall: OK` |
| `scripts/verify_changes.py --full` (ตอนปิดงาน ครั้งเดียว) | **PASS (exit 0)** · `362 passed, 2 warnings in 204.97s` · `PASS (full) in 211.2s` — **รอบนี้ไม่ค้าง** (SQLite lock ไม่เกิด) |

### Live attempt (2026-10-09 ~15:22–15:45 BKK) — outcome: **order preserved (fail-safe proven)** ✅
- Gateway restart: pid `79187` → `84611`; source mtime `15:12:57` < proc start `15:22:24` (ยืนยันโค้ดใหม่มีผลจริง — `LINE-RCA-011`)
- Session: `POST /api/v1/session/login {force_fresh:false}` → `resumed:true` · `otp_ref:null` · **AUTHENTICATED** (Zero-OTP, ไม่เผา SMS — `GW-RCA-003`)
- Live orders re-scanned: BCPG `11014378` SHORT 7,600 · VGI `11012374` SHORT 52,600
- **LIVE amend BCPG → REJECTED ที่ SET uptick guard ก่อนถึง `cancel_order`** ⇒ forensics ยืนยัน **ไม่มี cancel/re-submit** · `Order No. 11014378` ยังอยู่ครบ ✅
- **ข้อสรุปตรงไปตรงมา**: ยัง **ไม่มีการรัน cancel + re-submit LIVE จริง** ⇒ P0 fix **ยังไม่ถูกพิสูจน์ end-to-end**
- ผู้ใช้ยืนยันว่าราคาที่ขยับ (BCPG → ฿6.55, VGI → ฿0.95) เป็นการแก้ **ด้วยมือ** ของผู้ใช้ ไม่ใช่ผลของระบบ

### Open questions (อัปเดต)
1. 🟡 **P0 fix ยังไม่พิสูจน์ใน LIVE** — รอบจริงถูก reject ที่ uptick *ก่อน* cancel ⇒ ต้องมีคำสั่งค้างที่ราคาต้องแก้จริง + **คำสั่งชัดเจนในแชท** + human confirm ก่อนยิงทุกครั้ง (ห้ามยิงเอง)
2. 🟡 `POST /api/v1/simulation/live/probe/unmatched?account_type=EQUITY` → **HTTP 500** (นอก scope รอบนี้ — ต้อง RCA แยก)
3. ⚠️ **Residual risk (ใหม่)**: `execute_order` เรียก `validate_all` **หลัง** cancel ⇒ ถ้า reject ที่ด่านนั้น (สาเหตุอื่นที่ไม่ใช่ uptick) = **position หาย** เพราะไม่มี compensation/rollback → ควรเพิ่ม re-submit ที่ราคาเดิมในอนาคต
4. 🟢 `--full` รอบนี้ **ผ่าน** (`362 passed`, 204.97s) — ไม่ค้าง (SQLite lock ไม่เกิด) แต่ยังเป็น latent risk; ระหว่างทำงานใช้ targeted mode
5. 🔴 **`KSS-RCA-015` พิสูจน์ซ้ำอีกครั้ง (2026-10-09 ~15:39 BKK)**: การรัน `--full` **ลบ `data/session_state.json` จริง**
   (ไฟล์หายไปหลังรันเสร็จ) — รอบนี้ปลอดภัยเพราะ **สำรองก่อนรัน** แล้วกู้คืนได้ (md5 `619dee54…` ตรงกัน, 56 cookies / 3 origins)
   ⇒ **บังคับ**: ก่อนรัน `pytest tests/` ทุกครั้งต้อง `cp data/session_state.json data/session_state.json.manual.bak` ก่อนเสมอ (ห้ามลบ backup)

> ❗ **ไม่มีการยิง amend ซ้ำในรอบนี้** — ทั้งสองคำสั่งอยู่ที่ราคาเป้าหมายแล้ว (`needs_adjustment=False`)

---

## Antigravity Review
- Verdict:
- Notes:

