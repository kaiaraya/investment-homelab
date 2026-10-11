# Standard Operating Procedure (SOP): SBL Lifecycle & Short Selling Intelligence
**Document ID:** `SOP-004`  
**Governing Sub-Agent:** `SBLManagerAgent`  
**Version:** 1.0  
**Effective Date:** 2026-10-03  

---

## 1. Objective & Scope
Define the standard procedures for managing Securities Borrowing and Lending (SBL) workflows on Krungsri TradeMan, including pre-short inventory checks, automated stock borrowing, tracking borrowing interest fees, managing unmatched short contingencies, dividend risk protection, and returning borrowed lots upon position close.

---

## 2. Input & Output Contracts

### Inputs:
- `symbol`: Stock ticker to borrow or return.
- `volume`: Number of shares (must be multiple of 100).
- `action`: `'CHECK_INVENTORY'`, `'BORROW'`, `'RETURN'`, or `'AUDIT_CORPORATE_ACTIONS'`.
- `borrow_tx_no`: Broker Transaction Reference for returning specific lots.

### Outputs:
- `inventory_status`:
  - `available_volume`: int
  - `borrow_rate_annual`: float (standard 5.5% p.a.)
  - `status`: `'AVAILABLE'`, `'OUT_OF_STOCK'`
- `sbl_action_result`:
  - `status`: `'BORROWED'`, `'RETURNED'`, `'HELD_UNMATCHED'`, `'FAILED'`
  - `tx_no`: str
  - `borrow_date`: str
  - `accrued_interest_est`: float

---

## 3. Step-by-Step Standard Operating Procedure

### Step 3.1: Pre-Short Inventory Scrape
1. Prior to initiating any `SHORT` trade recommendation:
   - Navigate to Krungsri TradeMan `หุ้นยืม SBL` (SBL Tab).
   - Enter `symbol` into inventory search.
   - Extract `Available Inventory` (จำนวนคงเหลือในคลัง).
   - If `available_volume < required_volume`, abort shorting signal immediately.
   - Record available quota in short-term working memory.

### Step 3.2: Automated Stock Borrowing
1. Click `ยืมหุ้น (Borrow Stock)`.
2. Input target `volume` (multiple of 100).
3. Confirm borrowing terms (Borrow Rate: ~5.5% per annum, calculated daily).
4. Submit and record:
   - Broker Lot Transaction ID.
   - Timestamp and borrowing date.
   - Initial collateral requirement (typically 150% of market value in Equity/Cash).
5. Notify `OrderExecutionAgent` that borrowed inventory is ready for Short submission.

### Step 3.3: Unmatched Short Contingency Policy (Crucial Business Rule)
1. If the subsequent `SHORT` order on the market is **cancelled, unmatched, or only partially filled**:
   - **DO NOT RETURN BORROWED SHARES IMMEDIATELY**.
   - Immediate return might incur redundant transaction friction or lose rare inventory.
   - Hold the borrowed shares in SBL pending pool.
   - Send interactive LINE notification to user:
     - *"ยืมหุ้น [SYMBOL] [VOLUME] หุ้น สำเร็จ แต่ออเดอร์ Short ไม่จับคู่"*
     - Option A: Re-try Short order at revised price.
     - Option B: Return shares to SBL inventory to avoid overnight fee.

### Step 3.4: Automated SBL Return upon Cover
1. When a Short position is closed via `COVER`:
   - Wait for trade confirmation of the Cover order.
   - Navigate to `หุ้นยืม SBL` -> `คืนหุ้น (Return Stock)`.
   - Match original `borrow_tx_no` or lot date.
   - Enter returned volume.
   - Click `ยืนยันการคืนหุ้น (Confirm Return)` to stop interest accumulation.
   - Update SQLite database to mark SBL lot as `RETURNED`.

### Step 3.5: Corporate Action & Dividend Safeguard
1. At 09:15 daily (Pre-Market):
   - Scan active borrowed lots against SET Corporate Action Calendar (XD / XR / XM).
   - If a borrowed stock is within **2 business days** of the XD (Ex-Dividend) date:
     - Issue urgent alert: Borrowers must compensate lenders 100% of gross dividend.
     - Recommend covering and returning shares prior to XD date.

---

## 4. Guardrails & Safety Constraints
- Never borrow shares without an active or planned Short signal.
- Never let an unused borrowed lot sit over a weekend unless explicitly confirmed by the user.

---

## 5. Definition of Done (DoD)
- Stock successfully borrowed or returned with broker transaction reference.
- SBL lot tracked in SQLite table with daily interest calculated.
- Notification sent to LINE and user alerted of remaining borrow liabilities.
