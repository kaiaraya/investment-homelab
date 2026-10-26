# TASK-loop2-autotrade-roadmap — Roadmap สู่ Full Autotrade (Model 19 Supreme) Loop 2–7

**Status:** DRAFT (รอ Argon เปิด Loop 2) · **Owner:** Argon (Planner) · **Target Readers:** Argon, Cline, Flash 3.8, Jules
**อ้างอิง:** `directive/master_directive_v2.md` (แม่บท Loop ปัจจุบัน) · `18_model_era4_grandmaster_v6_chandelierbooster_forwardtest.py` (Model 19 Supreme)

---

## 1. เป้าหมายสุดท้าย (North Star ของ Roadmap นี้)

เปิดเครื่อง homelab ทิ้งไว้ → ระบบทำครบวงจรเองทุกวันตาม **Model 19 Supreme** (Signal → Entry → Exit → SBL → EOD Report) สื่อสารผ่าน **LINE 100%** มนุษย์เดินทางไปไหนก็ได้ และเมื่อมีปัญหา (หรือไม่อยากให้ระบบทำต่อ) **สั่งหยุด/แก้ไขผ่าน LINE ได้ทันที**

หลักการ 5 ข้อ:
1. **ก้าวละหนึ่งขีดความสามารถ** — แต่ละ Loop เพิ่มอำนาจให้ระบบทีละชั้น จบด้วย Unit Test + Live Witness (T2) เสมอ
2. **LINE เป็น interface เดียว** — ห้ามกลับไปใช้ `/console` (Invariant จาก Loop 1)
3. **Slim Gateway คงเดิม** — Scheduler/Autotrade เป็น **process แยก** ไม่ฝังใน `app.main:app`; Gateway ทำหน้าที่ LINE CLI + Execution เท่านั้น
4. **โหมดอิสระ 3 ระดับ** สลับผ่าน LINE: `manual` (Loop 1) → `semi` (ระบบคิด+เสนอ มนุษย์กดยืนยัน) → `auto` (ระบบทำเอง มี circuit breaker กันพัง)
5. **Paper → Sandbox → Real วงเงินเล็ก → Full** — ห้ามข้ามขั้น; เงินจริงต้องมี Kill-Switch + วงเงินจำกัด

---

## 2. สถานะปัจจุบัน (Loop 1 — Baseline)

| มีแล้ว | ใช้ต่อใน Loop ไหน |
| :--- | :--- |
| LINE CLI: `/help /status /login /logout /port /cash /orders /nego` + Conversation State (multi-turn) | ทุก Loop |
| OTP Relay ผ่าน LINE (`otp_relay_registry.py`) + Zero-OTP Gate | 2,4,5,6 |
| Kill-Switch (`kill_switch_service.py`), Validator (odd-lot, tick, uptick, margin lock) | 4,5,6 |
| ตัว Drivers: `trademan_driver` (kss MARGIN 3024959), `quicktrade_driver`, `liberator_driver` (lib CASH), `click2win_driver` (Sandbox) | 4,5 |
| SBL JIT Borrow/Bulk Return runbook (รอตลาดเปิด) | 5 |
| Click2Win Sandbox (ทดสอบคำสั่งจริงได้ปลอดภัย) | 4 |
| **ยังไม่มี**: โค้ด Model 19 (compass engine, chandelier, SQN, fear&greed feeds), Scheduler, คำสั่ง `/buy /sell /short /cover` | สร้างใน 2,3,4,5 |

---

## 3. แผนภาพรวม Loop 2–7 (Summary)

| Loop | ชื่อ | Goal (จบเมื่อ...) | Tier | ความเสี่ยง |
| :---: | :--- | :--- | :---: | :--- |
| 2 | **Model Data Engine** | ข้อมูลครบทุกวัน + parity กับ notebook 100% | T0/T1 | ไม่มี (read-only) |
| 3 | **Live Signal Engine (Paper)** | ทุกเช้า 09:15 ออกแผนเทรดผ่าน LINE + paper P&L ตรง forward test | T1 | ไม่มี (paper) |
| 4 | **Order Placement + Auto-Exits** | ระบบส่งคำสั่งได้ผ่าน LINE confirm; exit อัตโนมัติ — บน Sandbox แล้ว Real วงเงินเล็ก | T0/T1 + T2 | เงินจริงวงเล็ก |
| 5 | **Full Autotrade Scheduler** | เปิดเครื่องทิ้งไว้ ระบบทำครบวงจรเอง มี `/halt` หยุดทันที | T1/T2 | เงินจริงเต็มระบบ (มีเบรก) |
| 6 | **Resilience & Travel Mode** | ระบบฟื้นตัวเองได้ มนุษย์สั่งได้ทุกอย่างผ่าน LINE จากที่ไหนก็ได้ | T0/T1 | — |
| 7 | **Model Ops** | ระบบไม่เสื่อม: walk-forward รายไตรมาส, drift monitor | T1 | — |

---

# 4. การแตกย่อยราย Loop (การ์ด 2.1, 2.2, …)

> **ลำดับภายใน loop**: ไล่จากบนลงล่าง (เลขย่อย = ลำดับแนะนำ) · การ์ดที่ขึ้นต้น `0a` = STEP 0a Probe (read-only + human) ต้องเสร็จก่อนการ์ด coding ที่อ้างอิง · สัญลักษณ์ tier: 🟢T0 (`homelab-build` / gemini-3.8-flash) · 🟡T1 (`homelab-build` / gemini-3.1-pro) · 🔴T2 (`default` + human witness, headed) · ☁️Colab (`homelab-colab`) · 🔧SQ (การ์ด `--triage`)

---

## 🔋 Loop 2 — Model Data Engine (Fuel)

### 2.0a — STEP 0a Probe: แหล่งข้อมูลและสัญญาข้อมูล (🔴 T2 Probe · Flash 3.8 + Human)
- **เป้า:** ตอบ Open Q#1 — ระบุ Source of Truth ของทุก feed ที่ notebook ใช้
- **ทำอะไร:** ไล่ CELL 2–3 ของ notebook ทีละ feed (`prices_202*.csv`, `thai_fear_greed_daily.csv`, `mcp_historical_sqn_data.json`, `kinematic_wave_zones_daily.csv`, `chandelier_stop_daily_cache.csv`, `wave_forensics_context_daily.csv`, `decision_compass_master_records.csv`, `position_*.csv`) → เขียนตาราง: ไฟล์ ← pipeline ไหนสร้าง (ตัวเก็บเดิมใน Colab/Drive/repo อื่น?) ← คำนวณจากอะไร ← อัปเดตเมื่อไหร่ ← schema คอลัมน์
- **Output:** `docs/handoff/TASK-loop2-0a-data-source-contract.md` (สัญญาข้อมูล) — การ์ด 2.1–2.4 ต้องรอสัญญานี้
- **Done when:** ทุก feed มีคำตอบครบ 5 ช่อง ไม่มี "หาไม่เจอ"

### 2.1 — Data Schema & DB Layer (🟢 T0 · Jules)
- **เป้า:** ตาราง SQLite สำหรับทุก feed + audit column ป้องกัน lookahead
- **งาน:** `app/db/models.py` เพิ่มตาราง `market_prices`, `fear_greed`, `market_sqn`, `kinematic_zones`, `chandelier_cache`, `wave_forensics`, `breadth`, `candidate_pools` — ทุกตารางมี `asof_date` (วันที่ข้อมูลปิด) แยกจาก `ingested_at`
- **Verify:** `.venv/bin/python scripts/verify_changes.py app/db/models.py`
- **Done when:** Unit test เขียน/อ่าน/upsert ครบทุกตาราง + ห้ามเขียนทับแถวที่ `asof_date` ผ่านไปแล้ว (immutable-after-close)

### 2.2 — EOD Price Ingestor (🟢 T0 · Jules)
- **เป้า:** ราคาปิดรายวันทุกตัวเข้าฐานทุกวัน 17:00–18:30
- **งาน:** `scripts/data_ingest/eod_prices.py` — ดึง SET EOD ตามสัญญา 2.0a → ลง `market_prices` → export `prices_YYYY.csv` ตามรูปแบบ notebook (index=date, column=ticker) เพื่อใช้ parity test
- **Verify:** `.venv/bin/python scripts/data_ingest/eod_prices.py --date 2026-10-15 --dry-run`
- **Done when:** รัน 3 วันทำการติด ข้อมูลครบ 100% ticker, 0 แถวซ้ำ, log สรุปได้

### 2.3 — Derived Feeds Engine (🟡 T1 · Jules)
- **เป้า:** คำนวณตัวแปรต่อเนื่องทั้งหมดจากราคา (port ตรรกะจาก CELL 3)
- **งาน:** `scripts/data_ingest/derived_feeds.py`:
  - `atr_pct` (rolling 14d ของ |pct_change|, clip 0.5–15)
  - Chandelier Stop + `cs_dist_atr` + `w_cs_atr_long/short` (ตามสูตร on-the-fly ของ CELL 3)
  - SQN + `sqn_v3`, `vol_100d` → `market_sqn`
  - Fear&Greed `master_score` + `fg_5d_delta` + `zone_master` → `fear_greed`
  - Breadth (ema50/ema200/trend ต่อหุ้น → l_cnt/s_cnt/delta) → `breadth`
  - Kinematic zones (`zone_mode`, `wave_context`) → `kinematic_zones` · Wave forensics (`direction`, `running_peak_delta`, `sqn_crosses_10d` …) → `wave_forensics`
- **Verify:** parity unit test เทียบ notebook ทีละคอลัมน์ (feed เก่าเป็น golden data)
- **Done when:** Parity 100% ในวันย้อนหลังที่ notebook มีข้อมูล

### 2.4 — Candidate Pool Builder (🟡 T1 · Jules — รอ 2.3)
- **เป้า:** สร้าง `position_YYYY-MM-DD.csv` รายวันเหมือน notebook (คอลัมน์ `Ticker, ema50, ema200, trend, Dip_ZScore, %Change`)
- **งาน:** `scripts/data_ingest/candidate_pools.py` — คำนวณจาก `market_prices` ย้อนหลังแบบ PIT → ลง `candidate_pools` + ไฟล์สำหรับ parity
- **Done when:** `df_prices` + pools ที่ build ได้ให้ผล `breadth_records` ตรง notebook ทุกวัน

### 2.5 — EOD Scheduler & Alert (🟢/🟡 T0/T1 · Jules)
- **เป้า:** Job อัตโนมัติทุกวันทำการ 17:00–18:30 (process แยก ไม่ฝัง gateway)
- **งาน:** `scripts/data_ingest/run_daily.py` (เรียง 2.2 → 2.3 → 2.4, retry 3 ครั้ง, idempotent) + ลง `start_homelab.sh`/systemd timer · ถ้าขาด/ล้ม → แจ้ง LINE ทันที
- **Done when:** รันเอง 1 สัปดาห์โดยไม่ต้องสั่งมือ 0 ครั้ง

### 2.6 — Parity Test Suite (🟡 T1 · Jules — รอ 2.3/2.4)
- **เป้า:** CI ประจำการ์ดถัดไปทุกใบ — port ไปเท่าไหร่ต้องตรง notebook เท่านั้น
- **งาน:** `tests/test_model19_parity.py` — golden data จาก notebook export มาเป็น fixture, เทียบทุก feed/derived/candidate
- **Done when:** รันผ่าน 100% และ integration เข้า `verify_changes.py` loop

### 2.7 — LINE: `/data status` `/data refresh` (🟢 T0 · Jules — รอ 2.1/2.5)
- **เป้า:** มนุษย์ดูความสมบูรณ์ของข้อมูลจากมือถือ
- **งาน:** `app/services/line_cli/parser.py` + `handlers.py` + `cards.py`: `/data status` (แต่ละ feed ล่าสุดวันไหน, ขาดกี่วัน), `/data refresh [date]` (รัน EOD job ใหม่เฉพาะวันที่ระบุ)
- **Done when:** Unit test flow ผ่าน + แสดงผลบนมือถืออ่านรู้เรื่อง

### 2.8 — Loop 2 Live Witness (🔴 T2 · Flash + Human)
- **เป้า:** ปิด Loop 2 — ข้อมูลจริง 3 วันทำการต่อเนื่องถูกต้องครบ
- **ทำ:** Human ตรวจ `/data status` ตอน 18:45 เทียบกับหน้าตลาดจริง (SET EOD) 3 วันติด

---

## 🧠 Loop 3 — Model 19 Live Signal Engine (Paper Trading)

### 3.0a — STEP 0a Probe: โค้ด Map ของ notebook (🔴 T2 Probe · Flash + Human)
- **เป้า:** แยกฟังก์ชันไหน port ตรงได้ / ไหนต้องเขียนใหม่เป็นเวอร์ชัน "live" (รายวัน)
- **ทำ:** ไล่ CELL 4–5 — `DynamicCompassEngine` (จาก `compass_returns_engine.py`), `regime10_map`, `wave_thrust`, dual-synergy weights, hybrid flip-cut, house-money → ตาราง: ฟังก์ชัน → บรรทัด → ขึ้นกับ feed อะไร → port ได้เลย/ต้องแปลง
- **Output:** `docs/handoff/TASK-loop3-0a-model19-code-map.md`
- **Done when:** ทุกบรรทัดของ decision flow มีเจ้าภาพการ์ด (3.1–3.4) ชัดเจน ไม่เหลือ "เดี๋ยวค่อยคิด"

### 3.1 — Port Compass Engine (🟡 T1 · Jules — รอ 2.6)
- **เป้า:** `DynamicCompassEngine` + `compute_all_6_setups` ทำงานใน homelab ได้ผลตรง notebook
- **งาน:** `app/services/model19/compass_engine.py` (ย้าย `compass_returns_engine.py` มา + ปรับ import ให้ใช้ DB แทนไฟล์) + `calc_stats_20d` จาก `plot_comparison_boxplot.py`
- **Verify:** parity test (2.6) ต่อยอด — input วันเดียวกัน → score 6 setups ตรงกันทุกจุดทศนิยม
- **Done when:** Parity 100% ทุกวันย้อนหลัง 850 วัน

### 3.2 — Regime & Wave Engine (🟡 T1 · Jules)
- **เป้า:** `regime10_map` + wave thrust + kwz/wf contexts ครบ
- **งาน:** `app/services/model19/regime_engine.py` — `get_10_regime()` (SQN × vol_100d), wave id/thrust จาก breadth, `MAPPING_10_REGIMES_M18_ATR`
- **Done when:** regime ของทุกวันย้อนหลังตรง notebook

### 3.3 — Booster & Exit Logic (🟡 T1 · Jules — รอ 3.1/3.2)
- **เป้า:** หัวใจ Model 19 — 3 Pillars ครบ
- **งาน:** `app/services/model19/booster.py` (Pillar 1: `w_syn = w_dip×w_cs_atr`), `app/services/model19/exits.py` (Pillar 2: hybrid smart flip-cut + TP/SL/BE/Runway/Weedout), `app/services/model19/house_money.py` (Pillar 3: PIT 1.25x เมื่อ be_locked ≥ 2 และ PnL > +2%)
- **Done when:** Unit test ครบทุก branch + parity กับ notebook ในตัวอย่าง 10 วันสุ่ม

### 3.4 — Daily Signal Job (🟡 T1 · Jules — รอ 3.1–3.3)
- **เป้า:** ทุกเช้า 09:00–09:15 ระบบคำนวณแผนวันนี้จากข้อมูลเมื่อวาน (PIT) เสร็จก่อนตลาดเปิด
- **งาน:** `scripts/signal_job.py` (process แยก): regime → mode → `target_l/s` → candidate ranking → exit plan ของพอร์ต → บันทึก `daily_signals` + ส่ง LINE card 09:15
- **Done when:** ออกแผนถูกเวลา 5 วันทำการติด และแผนวัน D ใช้ข้อมูล asof D-1 เท่านั้น (audit ได้)

### 3.5 — Paper Book & EOD Summary (🟡 T1 · Jules)
- **เป้า:** บันทึกไม้เสมือน + mark-to-market + ปิดตาม exit engine ทุกวัน 19:00 สรุป LINE
- **งาน:** `app/services/model19/paper_book.py` — สร้าง/อัปเดต/ปิด paper positions ตามแผน 3.4 และ exits 3.3, คำนวณ realized/unrealized, MDD, win rate
- **Done when:** Paper 1 สัปดาห์ครบทุกไม้ ไม่มีไม้ "ค้าง" เกิน Runway

### 3.6 — LINE: `/signal` `/paper` (🟢 T0 · Jules — รอ 3.4/3.5)
- **งาน:** `/signal` (แผนวันนี้), `/signal <date>` (ย้อนหลัง), `/signal detail` (candidates + weights รายตัว), `/paper` (สรุป paper: กลับ %, MDD, WR, ไม้เปิดอยู่)
- **Done when:** การ์ดอ่านรู้เรื่องบนมือถือ + unit flow ผ่าน

### 3.7 — Drift Monitor ตัวแรก (🟡 T1 · Jules — รอ 3.5)
- **เป้า:** รู้ทันทีว่าของจริงเบี่ยงจาก backtest
- **งาน:** `scripts/drift_monitor.py` — เทียบ paper P&L สะสม vs forward test คาดการณ์ (+21.36%/76 วัน) รายสัปดาห์เข้า LINE
- **Done when:** รายงานแรกออกหลัง paper 2 สัปดาห์

### 3.8 — Loop 3 Live Witness (🔴 T2 · Flash + Human)
- **เป้า:** ปิด Loop 3 — Human อ่านแผน `/signal` ทุกเช้า 2–4 สัปดาห์ แล้วลงความเห็นว่า "แผนที่ระบบออก เทรดได้จริง" (ไม่ใช่แค่ตัวเลขตรง notebook)
- **Gate:** ถ้า paper เบี่ยงจาก backtest เกินเกณฑ์ (ระบุตอนเปิด loop) → ห้ามเข้า Loop 4 จนกว่า Argon ตัดสินปรับหรือหยุด

---

## 🔫 Loop 4 — Order Placement + Auto-Exits (Sandbox → Real วงเล็ก)

### 4.0a — STEP 0a Probe: DOM ของหน้าส่งคำสั่ง (🔴 T2 Probe · Flash + Human)
- **เป้า:** สัญญา DOM สำหรับ order entry ของทุกช่องทาง
- **ทำ:** เปิดหน้าส่งคำสั่งจริงทีละอัน: kss QuickTrade (Buy/Sell/Short, `#orderBodyEq`), lib WebTrade (`/vb/…`), Click2Win Sandbox → บันทึก selector + flow + ปุ่ม confirm + ตารางหลัง submit
- **Output:** `docs/handoff/TASK-loop4-0a-order-entry-dom-contract.md`
- **Done when:** ครบทั้ง 3 ช่องทาง + ระบุวิธี verify หลังกด (Anti-Mock อ่านตารางกลับ)

### 4.1 — Order Entry Drivers (🟡 T1 · Jules — รอ 4.0a)
- **เป้า:** `place_order()` จริง บน kss/lib/sandbox
- **งาน:** `app/brokers/krungsri/order_entry_driver.py`, `app/brokers/liberator/order_entry_driver.py` (+ wrap `click2win_driver` ที่มีอยู่) — ส่งได้ BUY/SELL/SHORT/COVER + อ่านผลกลับ (Order No., status) — **ห้าม mock ผลสำเร็จ**
- **Verify:** `.venv/bin/python scripts/verify_changes.py` + sandbox live probe
- **Done when:** Sandbox order ครบ 4 ประเภท ผ่าน witness

### 4.2 — Sizing & Risk Module (🟡 T1 · Jules)
- **เป้า:** คำนวณขนาดไม้ + bracket ตาม Model 19
- **งาน:** `app/services/model19/sizing.py` — slot = equity × lev × slot_mult / 7, SL/TP = sm×ATR / tm×ATR, BE-lock 0.65×ATR; เดินผ่าน validator เดิม (odd-lot, tick, uptick, margin lock) **ทุกไม้**
- **Done when:** Unit test ครบทุก branch + ไม้ที่คำนวณได้ผ่าน validator 100%

### 4.3 — LINE: `/buy /sell /short /cover /close /positions` + Approval Card (🟡 T1 · Jules — รอ 4.1/4.2)
- **เป้า:** มนุษย์สั่งซื้อขายจาก LINE ได้ ไม้ละ 1 ใบยืนยัน
- **งาน:** `parser.py`/`handlers.py`/`cards.py`: คำสั่งใหม่ + **Approval Card** (ราคา, จำนวนหุ้น, ATR SL/TP, ค่าธรรมเนียมประมาณ, ปุ่ม [ยืนยัน]/[ยกเลิก], หมดอายุ `CARD_TTL`) ใช้ `conversation_state.py` ที่มีอยู่
- **Done when:** Flow ผ่าน unit + sandbox: สั่ง `/buy` → กดยืนยัน → order เข้า sandbox จริง

### 4.4 — Auto-Exit Daemon (🟡 T1 · Jules — รอ 3.3/4.1)
- **เป้า:** ระบบเฝ้าไม้เปิดทุก 1 นาทีช่วงตลาด แล้วเสนอ/ยิง exit (TP/SL/BE/Flip/Runway/Weedout)
- **งาน:** `scripts/exit_daemon.py` — อ่านราคา → เทียบกติกา 3.3 → ใน semi mode: ส่ง card เสนอ exit ให้ human กดยืนยัน (auto mode ปิดไว้ก่อน)
- **Done when:** Sandbox: ไม้ครบวงจรถูกปิดครบทุก reason โดยไม่พลาด 1 สัปดาห์

### 4.5 — Sandbox Full-Cycle (🟡 T1 + 🔴 witness · Jules + Flash/Human)
- **เป้า:** รัน Daily Scenario ครบวงจรบน Click2Win 2–4 สัปดาห์ (เข้า → exit → nego → EOD)
- **ทำ:** ใช้ `daily_scenario_runner.py` ที่มีอยู่ + ต่อกับ signal 3.4 แบบ semi
- **Done when:** 0 ข้อผิดพลาด 10 วันทำการติด + witness ครบ

### 4.6 — Real Small Rollout (🔴 T2 · Flash + Human Witness)
- **เป้า:** เงินจริงวงเล็กภายใต้การควบคุม
- **ทำ:** ตั้ง `slot_mult = 0.5`, วงเงินต่อวัน cap, semi mode เท่านั้น, witness ทุกไม้ 1–2 สัปดาห์
- **Done when:** ตัวเลขบน LINE ตรงหน้าจอโบรกเกอร์ 100% + human อนุมัติเข้า Loop 5

---

## 👑 Loop 5 — Full Autotrade Scheduler (Auto mode)

### 5.0a — STEP 0a Design: Scheduler + Kill-Switch Contract (🔴 T2 · Flash + Human + Argon)
- **เป้า:** ออกแบบ process boundary ก่อนเขียนโค้ด
- **ทำ:** ระบุว่า autotrade อยู่ตรงไหน (process อะไร), kill-switch ใช้ flag ที่ไหน (ไฟล์ + DB, gateway อ่านได้), ใครถือ state, ลำดับของวันครบ 09:15→19:00
- **Output:** `docs/handoff/TASK-loop5-0a-scheduler-design.md`
- **Done when:** Argon + Human อนุมัติ design

### 5.1 — Scheduler Skeleton (🟢 T0 · Jules — รอ 5.0a)
- **งาน:** `scripts/autotrade_scheduler.py` — วงรอบหลัก + ผูก `start_homelab.sh`/systemd, log, alert พื้นฐาน
- **Done when:** รัน 1 วันว่างๆ (วันหยุด) ครบทุก checkpoint โดยไม่แตะ order

### 5.2 — Morning Entry Routine (🟡 T1 · Jules — รอ 5.1)
- **เป้า:** 09:15 signal → 10:30–12:00 เปิดไม้ตาม ranking อัตโนมัติ
- **งาน:** scheduler → อ่าน signal 3.4 → picks → 4.1 place (long: kss/lib; short: kss + **SBL JIT borrow** ก่อนส่ง short) → รายงาน LINE ทุกไม้ + unmatched → ต่อราคาอัตโนมัติ 12:00
- **Done when:** 1 สัปดาห์ semi witness ผ่าน (human เห็นทุกไม้ก่อนยิง)

### 5.3 — Intraday Exit + Auto-Nego (🟡 T1 · Jules — รอ 5.2)
- **งาน:** exit_daemon 4.4 เปิด auto mode + nego อัตโนมัติ 12:00/16:00 ผ่าน guardrails G1–G6 เดิม
- **Done when:** witness: ไม้ครบวงจรถูกปิด/ต่อราคาเอง 100% 3 วัน

### 5.4 — SBL Lifecycle Automation (🟡 T1 · Jules)
- **งาน:** ผูก runbook เดิม (P3.7/P3.8): borrow ก่อน short ทุกไม้, bulk return 16:30, hold unmatched short (P4.5)
- **Done when:** short ครบวงจร (borrow → fill/ไม่ fill → return) 0 หุ้นยืมค้างข้ามคืนเกินควร

### 5.5 — Circuit Breakers & Kill-Switch Hardening (🟡 T1 + 🔴 T2 · Jules + witness)
- **เป้า:** ระบบพังได้ แต่เสียหายจำกัด
- **งาน:** `app/services/circuit_breaker.py` — ขาดทุนวันเดียวเกิน cap → หยุด + LINE; MDD เข้าใกล้ -20% → ลดเป็น semi; positions ≥ 7 → หยุดเปิดใหม่; `/halt` ตอบสนอง <10 วินาที (ทดสอบจริง)
- **Done when:** จำลองเบรกทุกแบบแล้วทำงาน + witness `/halt` จริง

### 5.6 — LINE Control Surface (🟡 T1 · Jules)
- **งาน:** `/mode auto|semi|manual`, `/halt`, `/resume`, `/flatten`, `/skip SYM`, `/daily loss N%`
- **Done when:** สลับโหมดจริงกลางวันได้โดยไม่ค้าง (unit + witness)

### 5.7 — Rollout: 1 wk semi → 1 wk auto เล็ก → auto เต็ม (🔴 T2 · Human Witness ทุกขั้น)
- **Gate แต่ละขั้น:** Human เป็นคนสั่ง `/mode` เองผ่าน LINE หลังเห็นหลักฐานครบ
- **Done when:** auto ต่อเนื่อง 20 วันทำการ โดย human ไม่แตะเครื่อง homelab (แตะ LINE ได้)

---

## 🛡️ Loop 6 — Resilience & Travel Mode

### 6.1 — Watchdog & Auto-Restart (🟢 T0 · Jules)
- **งาน:** process monitor ทุก process (gateway, scheduler, exit daemon) ตาย → restart + LINE
- **Done when:** kill process แล้วฟื้นเอง <1 นาที

### 6.2 — Browser Crash Recovery + Auto-Login (🟡 T1 · Jules)
- **เป้า:** browser ล่ม/session หลุดกลางวัน → relaunch → login อัตโนมัติ (OTP ผ่าน LINE relay เดิม) → รายงาน
- **Done when:** จำลอง session หลุดตอนตลาดเปิด → ฟื้น + เข้าระบบภายใน 5 นาที

### 6.3 — LINE Webhook Heartbeat (🟡 T1 · Jules)
- **เป้า:** LINE เงียบเกิน N นาที (webhook ล่ม) → ระบบหยุดเปิดไม้ใหม่ + แจ้งช่องสำรอง
- **Done when:** ปิด webhook จำลอง → ระบบ hold + เตือนภายในเกณฑ์

### 6.4 — Alert Escalation Matrix (🟡 T1 · Jules)
- **งาน:** ระดับแจ้งเตือน: ปกติ (การ์ดเดียว) → สำคัญ (ping 2 ครั้ง) → วิกฤต (LINE + เสียง/ช่องสำรอง): abnormal price >3%, ออเดอร์ค้างนาน, broker ไม่ตอบ, เบรกสะดุด
- **Done when:** ทุกเหตุการณ์มีช่องทางและ timeout ระบุครบ

### 6.5 — Audit Log + `/report` `/audit` (🟢 T0 · Jules)
- **งาน:** ทุก action (order, signal, exit, mode change) ลง DB → `/report` (วัน/สัปดาห์), `/audit <date>` (ทุก action ตามเวลา)
- **Done when:** ย้อนดูวันไหนก็ได้ครบ 100%

### 6.6 — Chaos Drills (🔴 T2 · Flash + Human Witness)
- **เป้า:** พิสูจน์ Travel Mode
- **ทำ:** จำลองล่ม 3 แบบ (webhook ล่ม, browser ล่ม, session หลุด) + ล่มพร้อมกัน 1 ครั้ง → ระบบฟื้น/รายงานถูกต้อง โดย human ไม่แตะเครื่อง
- **Done when:** ผ่านทั้ง 4 ดริล

---

## 📈 Loop 7 — Model Ops (MLOps)

### 7.1 — Walk-Forward Re-fit รายไตรมาส (🟡 T1 · Argon + Jules)
- **งาน:** SOP re-run notebook แบบ PIT กับข้อมูลใหม่ 3 เดือน → ทบทวน frozen calibration → ผ่าน 4-agent loop เดิม
- **Done when:** รอบไตรมาสแรกผ่าน + directive ใหม่ (ถ้ามีการเปลี่ยน)

### 7.2 — Drift Monitor รายสัปดาห์ (🟡 T1 · Jules — ต่อจาก 3.7)
- **งาน:** รายงาน live vs backtest รายสัปดาห์ + เกณฑ์แจ้งเตือนเกิน drift
- **Done when:** รายงาน 4 สัปดาห์ติด

### 7.3 — A/B Test Framework (🟡 T1 · Jules)
- **งาน:** รัน booster weight / house-money variant คู่ขนานบน paper book พร้อมเกณฑ์หยุด (early stop) — ไม่แตะเงินจริงจนกว่าจะชนะชัด
- **Done when:** โครงสร้างรองรับ 2 variants + สลับได้

### 7.4 — Monthly Review SOP (🟢 T0 · Argon + Cline)
- **งาน:** เทมเพลตรีวิวรายเดือน (ผล auto vs เป้า, เหตุการณ์, สิ่งที่ต้องปรับ) + ต่อ directive
- **Done when:** ใช้จริงรอบแรก

---

## 5. ความสัมพันธ์ระหว่างการ์ด (Dependency Map)

```
2.0a → 2.1 → 2.2 → 2.3 → 2.4 → 2.5
                ↘ 2.6 (parity) ← 2.7 (LINE) ← 2.8 (witness) → ปิด Loop 2
3.0a → 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.7
                          ↘ 3.6 (LINE) ← 3.8 (witness) → ปิด Loop 3
4.0a → 4.1 → 4.3 (LINE สั่งซื้อ)          4.4 (exit daemon) ← 3.3
        ↘ 4.2 → 4.3      ↘ 4.5 (sandbox) → 4.6 (real เล็ก) → ปิด Loop 4
5.0a → 5.1 → 5.2 → 5.3 → 5.5 → 5.6 → 5.7 (rollout) → ปิด Loop 5
             ↘ 5.4 (SBL)
6.1–6.5 ขนานกันได้ (ยกเว้น 6.3 ต้องมี 5.5 ก่อน) → 6.6 (drills) → ปิด Loop 6
7.x เริ่มได้หลัง Loop 5 เปิด auto แล้ว 2 สัปดาห์
```

**การ์ดคู่ขนาน (Parallel lanes) ที่ทำพร้อมกันได้:** 2.2 ∥ 2.3 (คนละไฟล์) · 3.1 ∥ 3.2 · 4.1 ∥ 4.2 · 6.1 ∥ 6.4 ∥ 6.5 — ใช้ Jules bridge ยิงทีละ branch เหมือน Loop 1

---

## 6. Guardrails ข้าม Loop (ห้ามละเมิด)

1. **Kill-Switch อยู่เหนือทุกอย่าง** — `/halt` ต้องทำงานแม้ scheduler พัง (แยกไฟล์/แยก DB flag)
2. **Order เงินจริงทุกไม้** ต้องผ่าน validator (odd-lot, tick size, uptick, margin lock) — Loop 1 สร้างไว้แล้ว
3. **ห้าม Cancel+Replace** — แก้ราคาในที่เท่านั้น (Invariant จาก Loop 1)
4. **ไม่ lookahead** — ข้อมูลของวัน D ต้องปิดถาวรก่อนถูกใช้ในวัน D+1 (audit `asof_date`)
5. **Auto mode ต้องมีวงเงินจำกัด** + breaker วันละครั้งจนกว่าจะผ่าน witness ต่อเนื่อง 20 วันทำการ

## 7. ตัวชี้วัดความสำเร็จของ Roadmap (Definition of Done)

- ระบบ auto ต่อเนื่อง 20 วันทำการ โดย human ไม่แตะเครื่อง homelab เลย (แตะ LINE ได้)
- MDD ระหว่างทางไม่เกิน -20.35% (worst case ของ model)
- ทุกเหตุการณ์ผิดปกติ (session หลุด, ออเดอร์ไม่ match, broker ล่ม) ถูกจับ + รายงาน LINE ภายใน 5 นาที
- Human สั่ง `/halt` → ระบบหยุดส่งคำสั่งภายใน <10 วินาที (ทดสอบจริง)

---

## Open Questions (บันทึกไว้ ยังไม่ลงมือ)

1. แหล่งข้อมูล EOD ราคา SET ที่เชื่อถือได้ในระยะยาว (SET EOD ฟรี? / จากโบรกเกอร์? / ตัวเก็บเดิมจาก Colab อยู่ repo ไหน) — ต้องตอบใน 2.0a
2. งบประมาณค่าธรรมเนียม SBL + ค่าธรรมเนียมต่อรอบ ในโหมด auto ที่เทรดทุกวัน — กระทบ target slot sizing (การ์ด 4.2)
3. kss MARGIN วงเงิน Margin จริงรองรับ 7 ไม้ × 1.5 lev ได้ไหม หรือต้องลด slot ต่อวัน (การ์ด 4.2)
4. เวลาเปิดจริงของโหมด auto (ช่วงไหนของปี) — ควรเลี่ยงช่วงประกาศงบที่มี tail risk สูงหรือไม่ (Human + Argon ก่อน 5.7)
