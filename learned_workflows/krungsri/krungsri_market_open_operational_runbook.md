# Krungsri Market-Open Operational Runbook (Live Trading Protocol)

> **Document Status**: Approved Architecture Specification (Awaiting Market Open Hours)  
> **Market Operating Hours**: 09:55 – 16:35 Bangkok Time (SET Trading Days)  
> **Primary Accounts**: Krungsri Cash (`3024952`) & Krungsri Credit Balance SBL (`3024959`)

---

## 1. Executive Summary & Objective

This runbook documents the operational protocol and step-by-step execution procedure for the 4 remaining Krungsri workflows across **Pillar 3 (Trade Execution)** and **Pillar 6 (Tactical Strategy)**:
1. **Pillar 3 — ยืมหุ้น (SBL Borrow)**: ⚡ *Just-In-Time (JIT) Auto-Borrowing* via SSO SBL Real Time (`#MainCenter_lbBorrow`).
2. **Pillar 3 — คืนหุ้น (SBL Return)**: 📦 *Scheduled EOD Bulk Return (16:30 น.)* via SSO SBL Real Time.
3. **Pillar 6 — ต่อราคา (Price Negotiation)**: 🎯 *Passive Queue Pegging* (Bid 1 / Offer 1 / Uptick compliance) on TradeMan open orders.
4. **Pillar 6 — Action Entry**: 🤖 *Fully Autonomous Multi-Window Entry* with pre-trade risk shields.

---

## 2. Daily Market-Open Operational Timeline

```mermaid
timeline
    title Daily Autonomous Market-Open Execution Matrix
    09:45 : Pre-Flight Session Check : D-Bus + KDE + Auto Session-Drop Warning (KSS-RCA-011)
    09:55 : SBL Real Time Sync : Scan SET50/SET100 Pool & XD Hard Blocker
    10:00 : Market Open : Action Exit Window 1 (Priority Sell @ Offer 1)
    10:05 : Tactical Window 1 : Action Entry (Long @ Bid 1 / Short @ Offer 1 with JIT SBL Borrow)
    11:00 : Price Negotiation 1 : Evaluate Unmatched Orders -> Re-peg to Bid 1 / Offer 1
    14:30 : Afternoon Open : Re-verify Session State & %MM
    14:35 : Tactical Window 2 : Action Entry Afternoon Window
    15:30 : Price Negotiation 2 : Pre-Close Passive Re-pegging
    16:30 : SBL Bulk Return : Submit Return Batch for all Covered Contracts
    16:35 : EOD Clean-Up : Cancel all Remaining Unmatched Orders
```

---

## 3. Workflow Specifications & Technical Anchors

### A. SBL Borrow (Just-In-Time Auto-Borrowing)
* **DOM Target**: `https://www.krungsrisecurities.com/sblweb/MainSBL.aspx` -> `#MainCenter_lbBorrow`
* **Trigger**: Triggered automatically when an `ActionEntry` produces a `SHORT SELL` signal.
* **Pre-conditions**:
  1. Symbol exists in SBL Pool (SET50 / SET100 / NEW SEC).
  2. Available borrow volume >= requested volume.
  3. **Strict XD/XR Shield**: Symbol is NOT present in `#MainCenter_lbXD` list (avoids 100% dividend compensation liability).
* **DOM Actions**:
  - Click `#MainCenter_lbBorrow`.
  - Type Symbol into `#ctl00_MainCenter_txtSecName`.
  - Type Board Lot Volume into `#ctl00_MainCenter_txtVol`.
  - Click `#ctl00_MainCenter_btnSubmit` and handle modal confirmation dialog.
  - Parse contract reference number into `data/session_state.json`.

### B. SBL Return (Scheduled EOD Bulk Return at 16:30)
* **DOM Target**: `https://www.krungsrisecurities.com/sblweb/MainSBL.aspx` -> `#MainCenter_lbTrans` / `#MainCenter_lbReturn`
* **Trigger**: Daily cron at 16:30 BKK.
* **Pre-conditions**:
  1. Active borrow contracts exist with outstanding balance.
  2. Matching `COVER` orders in TradeMan are 100% `Matched` and shares are settled on-hand.
* **DOM Actions**:
  - Open active contracts table.
  - Select all eligible contracts matching covered positions.
  - Submit batch return requests.
  - Broadcast return summary card to LINE (`a14s homelab`).

### C. ต่อราคา (Passive Queue Pegging)
* **DOM Target**: TradeMan `View Order` / `Order Status` & Live Streaming Bid 1 / Offer 1.
* **Schedule**: 11:00 BKK (Round 1) and 15:30 BKK (Round 2).
* **Rules**:
  - `BUY` / `COVER`: If unmatched and current order price < Bid 1, amend price up to **Bid 1**.
  - `SELL`: If unmatched and current order price > Offer 1, amend price down to **Offer 1**.
  - `SHORT`: Respect **SET Uptick Rule** — target price must be **strictly > Last Price** (zero-plus tick / equal price is **NOT** allowed; minimum = **Last + 1 tick**). Target = `max(Offer 1, Last + 1 tick)`.
    - If the order already sits **at the best offer, or 1 tick above it** → leave it alone and wait for the market to move up (no negotiation).
    - If `Last` cannot be read → **fail-closed**, propose nothing (Anti-Mock; never backfill from the order's own price).

### D. Action Entry Dispatcher
* **Component**: [app/services/action_entry_dispatcher.py](file:///home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab/app/services/action_entry_dispatcher.py)
* **Execution Windows**:
  - Window 1: 10:05 – 10:45 BKK (Morning post-open liquidity discovery).
  - Window 2: 14:35 – 15:15 BKK (Afternoon continuation/breakout).
* **Safety Thresholds**:
  - Maintenance Margin (%MM) >= 50% (Hard stop if below).
  - Purchasing Power (PP) >= Order Value + 10% safety buffer.
  - Volume % 100 == 0 (Strict board lot check).

---

## 3.1 Automated Session-Drop Detection (KSS-RCA-011 — added 2026-10-06)

ห้ามรายงานว่า "พร้อม" ทั้งที่ session หาย/หมดอายุ (Anti-Mock Guardrail) — ทุก component ใช้ **single source of truth** เดียวกัน:

* **Inspector**: `app/brokers/krungsri/session_health.py::session_file_info()` (browser-free, stdlib-only)
  → `reason ∈ {MISSING, STALE (>12h), RECENT}` และ `needs_fresh_login`
* **Preflight** (`scripts/preflight_check.py` step 3): `⚠️ missing` / `⚠️ EXPIRED/STALE` /
  `ℹ️ Saved cookies present` — **ไม่มี ✅** เพราะ TradeMan SSO เป็น session cookie (`expires: -1`)
  จึงยืนยันความใช้ได้แบบ offline ไม่ได้ (live DOM check จะตัดสินตอน connect)
* **MCP** `session_get_health().krungsri_trademan` เพิ่ม `session_file_exists`,
  `session_file_mtime`, `session_file_age_hours`, `needs_fresh_login`, `session_file_reason`
* **SessionSentinel** (ตรวจทุก tick — ไม่ผูกกับ live tab หรือ trading hours):
  * ไฟล์หาย → log `SESSION_FILE_LOST` + alert **LINE + KDE Connect**
  * ไฟล์กลายเป็น stale → log `SESSION_FILE_EXPIRED` + alert
  * Weekday **09:45–09:55 BKK** ถ้ายังต้อง login → `PREMARKET_SESSION_WARNING` (ไม่เกิน 1 ครั้ง/วัน)
    และ `_next_wait_seconds()` cap sleep ให้ loop ลงจอดในหน้าต่างเสมอ

### Operator response เมื่อได้ alert
1. รัน `.venv/bin/python -m app.brokers.krungsri.cli login` (headed) แล้วรับ SMS OTP
2. ยืนยัน: `curl -s http://127.0.0.1:8000/api/v1/session/health`
   → ต้องเห็น `session_file_exists: true` และ `needs_fresh_login: false`
3. ⚠️ **หมายเหตุ deploy:** uvicorn ที่รันค้างอยู่ cache โมดูลเก่า → ต้อง restart service
   หลังอัปเดตโค้ด มิฉะนั้น REST/MCP จะยังคืน payload เก่า (ไม่มี key ใหม่)

---

## 4. Live Verification Checklist for Next Trading Day

When SET Market opens on the next trading session:
1. [ ] Run `./start_homelab.sh` at 09:40 to verify 4-stage readiness gate.
2. [ ] Open Web Console at `http://localhost:8000/console`.
3. [ ] Confirm SBL Real Time Pool sync displays live status in the radar card.
4. [ ] Run smoke test for SBL Borrow on an approved SET50 stock (100 shares test).
5. [ ] Verify Action Entry test order placing in TradeMan.
6. [ ] Verify Price Negotiation round at 11:00 adjusts queued order to Bid 1 / Offer 1.
7. [ ] Confirm 16:30 SBL Bulk Return completes and reports to LINE.
