# Master Directive: InvestmentHomelab — Focused LINE CLI & In-Place Price Negotiation (Pillar 1–3)

**Status:** Canonical Single Source of Truth (Active Development Loop) — Phase B (Order Entry) เปิดแล้ว  
**Last Synchronized Commit:** `2bf22f8` (2026-10-16) · Phase B scope edit 2026-10-21 (เพิ่ม `/buy /sell /short /cover`)  
**Target Readers:** Hermes planner (`default`) + lane `homelab-build` (implementer) + lane `homelab-review` (verifier) + lane `homelab-colab` (GPU/CPU)

> **กฎสูงสุดสำหรับ Agent (Hermes ทุก lane):** เอกสารฉบับนี้คือแม่บทเดียวของ Development Loop ปัจจุบัน (ความยาว < 200 บรรทัด) หากเนื้อหาใน `directive/idea.md`, `directive/phase3_detail.md`, `directive/kdeconnect.md`, หรือ `directives/sops/*.md` ขัดแย้งกับไฟล์นี้ **ให้ยึดไฟล์นี้เป็นหลักทั้งหมด และห้ามแตะโมดูลที่ถูกระบุว่าเป็น Dormant/Disabled** — วิธีทำงานของแต่ละ lane อยู่ใน `docs/agent/kanban_operating_model.md` และ `.hermes.md`

## 1. เป้าหมายสูงสุดและขอบเขตของ Development Loop นี้ (Current Loop Scope)

1. **โฟกัสเฉพาะ 2 โบรกเกอร์ 2 บัญชีเท่านั้น**:
   * **Krungsri Settrade Streaming (`kss`)** — เฉพาะบัญชี **`MARGIN` (`3024959`)** — รองรับ **`/short` `/cover`** เท่านั้น
   * **Liberator WebTrade (`lib`)** — เฉพาะบัญชี **`CASH`** — รองรับ **`/buy` `/sell`** เท่านั้น
   * โบรกเกอร์และบัญชีอื่นทั้งหมด (`Click2Win`, `Settrade Open API`, และบัญชี `KSS CASH 3024952`) **พักไว้ก่อน (Out of Scope)**
   * **Side → Broker routing (Phase B):** `short`/`cover` → `kss` MARGIN · `buy`/`sell` → `lib` CASH (broker override `kss:margin` เก็บไว้ optional)
2. **เป้าหมายสูงสุดของระบบ (North Star Goal)**:
   * ระบบเป็น **LINE Slash CLI** ที่เสถียรสำหรับ **(1) ล็อกอินและรักษา Session**, **(2) ตรวจพอร์ต/วงเงิน/ออเดอร์ค้าง**, **(3) ต่อราคาออเดอร์ค้างในที่ (`/nego`)**, และ **(4) ส่งคำสั่งใหม่ (`/buy` `/sell` `/short` `/cover`) ผ่าน Flex Card Confirm (Phase B)**
   * การส่งคำสั่งใหม่ต้องผ่าน **Flex Card Confirm** ก่อนยิงจริง + **DRY_RUN_MODE** gate เสมอ — อ้างอิง `cdp_headed_architecture_plan.md` และ `docs/handoff/TASK-loop1-b0a-order-entry-contract.md`
3. **ทำเฉพาะ Pillar 1 ถึง Pillar 3 เท่านั้น**:
   * **ไม่มี Schedule / Cron อัตโนมัติ** (ผู้ใช้เป็นคนกดสั่งผ่าน LINE CLI เองทุกครั้ง)
   * **ไม่มี Agentic AI / Sub-Agents / LLM Orchestrator**
   * **ไม่ใช้หน้าเว็บ `/console`** (ใช้ LINE Chat เป็น Interface หลักเพียงช่องทางเดียว)

## 2. สถาปัตยกรรมที่เปิดใช้งานจริง (Active Architecture: Pillar 1–3)

Entrypoint เดียวของระบบคือ **`app.main:app`** (รันผ่าน `uvicorn` พอร์ต `:8000` โดย **ห้ามใช้ `--reload`** และเมื่อแก้โค้ดต้อง Restart Process เสมอตาม `LINE-RCA-011`) รับคำสั่งจาก LINE Webhook (`/api/v1/webhook/line`) เข้าสู่ **`app/services/line_cli/`**

| โบรกเกอร์ (CLI Alias) | บัญชีที่ใช้ใน Loop นี้ | โมดูล Driver หลัก | กลไกการต่อราคา (`/nego`) | ไฟล์ Session & Runbook |
| :--- | :--- | :--- | :--- | :--- |
| **Krungsri (`kss`)** | **`MARGIN`** (`3024959`) เท่านั้น | `app/browser/auth_driver.py`<br>`app/browser/trademan_driver.py`<br>`app/services/quicktrade_negotiation_service.py` | แก้ราคาในที่ (In-Place Change) บนตารางออเดอร์ (`modify_order_price` / QuickTrade Change) **ห้าม Cancel แล้วส่งใหม่** | `data/session_state.json`<br>`learned_workflows/krungsri/*.md`<br>`rca/krungsri/*.md` |
| **Liberator (`lib`)** | **`CASH`** เท่านั้น (Single-Account) | `app/brokers/liberator/driver.py`<br>`app/brokers/liberator/plugin.py` | แก้ราคาในที่ (In-Place Change Order) บนหน้า WebTrade **ห้าม Cancel แล้วส่งใหม่** | `data/liberator_session.json`<br>`learned_workflows/liberator/*.md`<br>`rca/liberator/*.md` |

### Pillar 1: Session & LINE OTP Relay (`app/mcp/pillars/pillar1_session.py`)
* **คำสั่ง LINE CLI**: `/status [kss|lib|all]`, `/login kss|lib|all [force]`, `/logout kss|lib|all`
* **กฎการทำงาน**:
  1. **LINE คือช่องทาง OTP เดียวที่ใช้งาน (`otp_relay_readiness.py`)**: รับ-ส่งคำขอรหัส 2FA SMS OTP 6 หลักผ่านกลุ่ม LINE (`LINE_GROUP_ID`) หรือแชท 1:1 (`LINE_ADMIN_USER_ID`)
  2. **Zero-OTP Gate (Invariant 9)**: ห้ามกดขอ SMS OTP จากเว็บโบรกเกอร์เด็ดขาดหาก `otp_relay_readiness.check().ready != True`
  3. **Multi-Broker Attribution (`otp_relay_registry.py` — `LINE-RCA-010`)**: บันทึกสถานะ `OTP_REQUESTED` ลงฐานข้อมูลหลัก (`AsyncSessionLocal`) เสมอ พร้อมระบุชื่อโบรกเกอร์และ `Ref Code` หากสั่ง `/login all` ต้องทำทีละโบรกเกอร์ตามลำดับ (`kss` → `lib`) ห้ามขอ OTP พร้อมกัน
  4. **Honest Session Health**: ตรวจจับการหลุดไปหน้า SignIn/Login จาก DOM จริง (`session_sentinel.py`) หากหลุดต้องรายงาน `🔴 หลุด` ตามจริง ห้ามรายงานว่า `alive`

### Pillar 2: Portfolio, Cash & Open Orders (`app/mcp/pillars/pillar2_portfolio.py`)
* **คำสั่ง LINE CLI**: `/port [kss|lib|all] [sync]`, `/cash [kss|lib|all] [sync]`, `/orders [kss|lib|all] [sync]`
* **กฎการทำงานและสัญญาข้อมูล**:
  1. **Snapshot First, Explicit `sync` Only (Invariant 7)**: ค่าเริ่มต้นให้อ่านจาก SQLite DB (`investment_homelab.db`) เมื่อต่อท้ายด้วย `sync` จึงจะไป Scrape สดจากหน้าเว็บ **โดยห้ามสั่ง Login หรือขอ OTP เองเด็ดขาด** (หาก Session หลุด ให้ตอบเตือนให้ผู้ใช้สั่ง `/login <broker>` ก่อน)
  2. **สัญญาข้อมูล `/port` (`P1.5` / `P1.6`)**:
     * แสดงยอดรวม **Amount (ต้นทุนรวม)** และ **Unrealized P/L** ให้ตรงกับหน้าเว็บโบรกเกอร์ (ไม่แสดง Market Value)
     * สำหรับ `kss` (MARGIN) แสดงส่วน **`หุ้นยืมคงเหลือ (B)`** (เฉพาะจำนวนหุ้นยืมคงเหลือที่อ่านได้จากพอร์ต) และห้ามนำส่วน `(B)` ไปแสดงใน `lib`
  3. **สัญญาข้อมูล `/cash` (`CLI-RCA-011` / `P2b`)**:
     * **`kss` (MARGIN `3024959`)**: ดึงจากแถบล่าง `div.bg-darkGray` และตาราง Account Info ได้แก่ `Line Available` (จาก `PP`), `Excess Equity` (`EE`), และ `Cash balance` (`real_cash_balance` จากตาราง) โดยต้องตรวจว่าหน้าจอเลือกบัญชี `3024959` อยู่จริง (`values_bound`)
     * **`lib` (CASH)**: แสดงวงเงินและเงินสดของบัญชี CASH เท่านั้น ไม่มีแถว Margin/EE
  4. **สัญญาข้อมูล `/orders`**: ดึงรายการออเดอร์วันนี้จากตาราง View Order แยกสถานะคำสั่งที่ยังค้าง (`Open`/`Queuing`/`Partially Matched` ที่มี `balance > 0`) ออกจากคำสั่งที่ `Matched` หรือ `Cancelled` อย่างชัดเจนเพื่อเป็นข้อมูลตั้งต้นให้ `/nego`

### Pillar 3: In-Place Price Negotiation (`/nego` — `app/services/line_cli/handlers.py` & Driver)
* **คำสั่ง LINE CLI**: `/nego kss|lib [SYMBOL|order_no]`
* **หลักการทำงาน (หัวใจหลักของ Loop นี้)**:
  1. **แก้ราคาออเดอร์ที่ผู้ใช้ส่งไว้แล้วเท่านั้น**: เลือกเฉพาะออเดอร์ที่ยังค้างอยู่ (`balance > 0`) ของโบรกเกอร์ที่ระบุ (ทั้งหมด, เฉพาะหุ้น `SYMBOL`, หรือเฉพาะเลขคำสั่ง `order_no`)
  2. **ราคาเป้าหมาย (Passive Best Bid 1 / Offer 1)**:
     * ออเดอร์ฝั่ง **`BUY` / `COVER`** → ขยับราคาไปที่ **`Best Bid 1`**
     * ออเดอร์ฝั่ง **`SELL`** → ขยับราคาไปที่ **`Best Offer 1`**
     * ออเดอร์ฝั่ง **`SHORT`** (เฉพาะ `kss` MARGIN) → ขยับราคาไปที่ **`Best Offer 1`** โดยต้องผ่านเกณฑ์ **Strict Short Uptick Rule**
  3. **In-Place Change เท่านั้น**: กดปุ่มแก้ไขราคา (Change/Amend) บนแถวออเดอร์เดิมเพื่อรักษาคิวและประเภทคำสั่ง **ห้ามใช้วิธี Cancel แล้วส่งออเดอร์ใหม่โดยเด็ดขาด**
  4. **Guardrails บังคับต่อออเดอร์ (G1–G6)**:
     * **G1 (Kill-Switch)**: `kill_switch_service.is_active()` ต้องเป็น `False`
     * **G2 (Time Window)**: ต้องอยู่ในช่วงเวลาทำการที่อนุญาต (`LINE_NEGO_WINDOWS = 09:55-12:30,14:25-16:30`)
     * **G3 (Session Alive)**: Session ของโบรกเกอร์นั้นต้องยัง `alive` (ห้าม Login อัตโนมัติ)
     * **G4 (SET Tick Size)**: ราคาเป้าหมายต้องผ่าน `validator.validate_tick_size()`
     * **G5 (Max Tick Distance)**: ระยะห่างระหว่างราคาใหม่กับราคาเดิมต้องไม่เกิน `LINE_NEGO_MAX_TICKS` (**สูงสุด 3 ช่องราคา/Ticks**) หากห่างเกิน 3 ช่องให้ข้ามออเดอร์นั้นและแจ้งผู้ใช้ในการ์ดสรุปผล
     * **G6 (Short Uptick Rule)**: ออเดอร์ `SHORT` ที่ราคาเป้าหมายผิดกฎ Uptick ต้องข้ามและแจ้งเตือนทันที

## 3. โมดูลที่ปิดการทำงานใน Loop นี้ (Dormant / Disabled by Design)

ไฟล์ต่อไปนี้ยังมีอยู่ใน Repository แต่ **ถูกปิดการใช้งานใน Loop นี้** — **ห้าม lane ใดเปิดใช้งาน, ห้ามนำมาคิดใน Flow ปัจจุบัน, และห้ามแก้ไขเว้นแต่ได้รับคำสั่งโดยตรง**:

| หมวดหมู่ที่ปิดไว้ก่อน | การตั้งค่าบังคับใน `config.py` / `.env` | โมดูล / ไฟล์ที่อยู่ในสถานะ Dormant (ห้ามแตะ) |
| :--- | :--- | :--- |
| **1. ระบบตั้งเวลาอัตโนมัติ (Schedulers & Time-Windows)** | `ENABLE_INTRADAY_SCHEDULER = False`<br>`ENABLE_ACTION_EXIT_DISPATCHER = False` | `app/services/phase3_scheduler.py`, `app/services/action_exit_dispatcher.py`, `app/services/action_exit_service.py`, `app/services/eod_service.py`, `app/mcp/pillars/pillar6_strategy.py` (ส่วนตั้งเวลา) |
| **2. ระบบ Agentic AI & Sub-Agents (Pillar 7)** | `ENABLE_AGENTIC_ORCHESTRATOR = False` | `app/ai/orchestrator.py`, `app/ai/agents/*`, `app/ai/signal_agent.py`, `app/mcp/pillars/pillar7_agentic.py`, `directives/sops/sop_*.md` |
| **3. ระบบยืม-คืนหุ้น SBL อัตโนมัติ (Pillar 4)** | ปิดการเรียกใช้งานอัตโนมัติ | `app/mcp/pillars/pillar4_sbl.py`, `app/services/sbl_intelligence_service.py` (ผู้ใช้จัดการยืม-คืนเองไปก่อน ส่วน `/port kss` แสดงแค่ยอดหุ้นยืมคงเหลือ `(B)` ที่อ่านจากหน้าพอร์ต) |
| **4. หน้าเว็บ Operator Console (`/console`)** | ไม่เปิดใช้งานในขั้นตอนปฏิบัติการ | `app/console.py` (ไม่ต้องเปิดเบราว์เซอร์เข้า `/console` และไม่ต้องแก้ UI ของ Console) |
| **5. โบรกเกอร์อื่น & KDE Connect Bridge** | `ENABLE_CLICK2WIN_POLLING = False`<br>`LINE_OTP_RELAY_ENABLED = True` | `app/brokers/click2win/*`, `app/browser/click2win_*.py`, `app/brokers/settrade_openapi/*`, `app/services/kdeconnect_service.py` |
| **6. ฟีเจอร์ที่ถอดออกถาวรแล้ว (Removed)** | ลบออกจากระบบแล้ว (ห้ามอ้างอิง) | `app/monitoring/*` (`monitor_*`, `alert_*`), `pillar5_portfolio.py` (ยุบรวมเข้า `pillar2_portfolio.py` แล้ว), `app.mcp.mcp_server` (stdio MCP) |

## 4. กฎเหล็กด้านความปลอดภัยและการพัฒนา (Non-Negotiable Invariants — ทุก lane)

1. **Anti-Mock**: ห้ามคืนค่าบัญชีปลอม, ยอดเงิน `0.00` แทนค่าที่อ่านไม่ได้ (`None`), หรือแกล้งรายงานว่าต่อราคาสำเร็จทั้งที่ DOM ไม่เปลี่ยน ต้องรายงานผลจริงจากหน้าเว็บโบรกเกอร์เท่านั้น
2. **Strict Broker Isolation**: โค้ดและ Selector ของ `kss` (TradeMan/QuickTrade) กับ `lib` (Liberator WebTrade) แยกกันโดยสมบูรณ์ ห้ามใช้ปนกัน
3. **Order Entry ต้องผ่าน Guardrails เสมอ (Phase B)**: อนุญาตส่งคำสั่งใหม่ผ่าน `/buy` `/sell` `/short` `/cover` แต่ทุกคำสั่งต้อง (a) ผ่าน `validator` (odd-lot / tick / strict short uptick G6), (b) เช็ค `line_available` จาก DB ก่อน, (c) ส่ง **Flex Card ยืนยัน (Confirm)** ก่อนยิงจริง, (d) ผ่าน `DRY_RUN_MODE` gate หลัง validate ก่อน submit — ห้าม mock ผลสำเร็จ; `/short` ต้องมีหุ้นยืม (SBL) คงเหลือ (ผู้ใช้ยืม/คืน manual ใน Loop นี้, Pillar 4 ยัง dormant) และการแก้ราคาในที่ (`/nego`) ยังคงห้าม Cancel+Replace
4. **Never Overwrite Saved Sessions in Tests/Probes (Invariant 8)**: สคริปต์ Probe และชุดเทสต์ทั้งหมดห้ามเขียนทับหรือลบไฟล์ `data/session_state.json` และ `data/liberator_session.json`
5. **No Secret or Balance Leakage**: ห้ามนำรหัสผ่าน, PIN, Token หรือตัวเลขยอดเงินจริง (ตั้งแต่ 4 หลักขึ้นไป) ออกมาเขียนลง Log, ไฟล์ Dump, หรือ Handoff Report (ใช้ `app/services/redaction.py`)
6. **Zero-Contradiction Runbooks**: ทุกครั้งที่ปรับแก้ Selector หรือลำดับการคลิกหน้าเว็บของ `kss` หรือ `lib` ต้องอัปเดตไฟล์ `learned_workflows/<broker>/*.md` และ `rca/<broker>/` ให้ตรงกันทันที

## 5. แพลตฟอร์มการทำงาน (Hermes-only, ตั้งแต่ 2026-10-26)

Jules / Cline / Antigravity IDE (4-agent hybrid loop) **ปลดระวางแล้ว** — งานทั้งหมดวิ่งบน Hermes Kanban board `investment-homelab` โดย lane = profile:

| Lane (assignee) | งาน | Model | Gate |
| :--- | :--- | :--- | :--- |
| `default` (planner) | แตกการ์ด · spec · verdict · board · merge | `gemini-4-argon` | gate #1/#2 (human) |
| `homelab-build` | T0/T1: code + unit test + `## Worker Report` | T0 `gemini-3.8-flash` · T1 `gemini-3.1-pro` | — |
| `homelab-review` | diff audit + `verify_changes.py` + `## Review Report` | `gemini-3.1-pro` | — |
| `default` (desktop, headed) | 0a read-only probe · 🔴T2 live witness | `gemini-3.8-flash` | **คนอยู่หน้าจอ** |
| `homelab-colab` | ☁️ GPU/CPU ผ่าน `colab` CLI (artifact → Drive) | `gemini-3.8-flash` | ห้าม commit เข้า repo |

**Triage rule (บังคับ):** idea / bug / tech-debt ที่พบระหว่างทำงานและอยู่นอก scope ของการ์ดที่กำลังรัน → สร้างการ์ดใหม่ `hermes kanban --board investment-homelab create "<title>" --triage --assignee default` ให้ specifier เติม body แล้ว promote — **ห้ามขยาย scope การ์ดเดิม และห้ามแก้โค้ดในการ์ด witness**

**Probe gate:** การ์ดที่แตะ DOM/XHR ต้องมี `Probe: PROBE_DONE` + `## DOM / API Contract` (จาก probe read-only + headed ที่คนยืนยันหน้าจอ) ก่อนถูกปล่อยจาก `blocked` — `scripts/preflight_card.py` ตรวจให้

**T2 gate:** worker รัน live ได้เฉพาะเมื่อ `DRY_RUN_MODE=false` เฉพาะ run นั้น · browser headed · คนนั่งดูจอและสั่ง "go" · การ์ดต้องมี `## Witness Session` ครบก่อน dispatch

รายละเอียด STEP 0–5, card body contract, และคำสั่งทั้งหมด → `docs/agent/kanban_operating_model.md`
