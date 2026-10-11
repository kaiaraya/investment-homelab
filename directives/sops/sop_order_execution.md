# Standard Operating Procedure (SOP): Order Execution & Tactical Trading
**Document ID:** `SOP-003`  
**Governing Sub-Agent:** `OrderExecutionAgent`  
**Version:** 1.0  
**Effective Date:** 2026-10-03  

---

## 1. Objective & Scope
Define the deterministic standard operating procedure for validating, formatting, and submitting trading orders (BUY, SELL, SHORT, COVER) to broker platforms (Click2Win Sandbox and Krungsri TradeMan) via Playwright runbooks (`learned_workflows/*.md`), executing dynamic price negotiations (Bid/Offer stepping), and cancelling unmatched orders.

---

## 2. Input & Output Contracts

### Inputs:
- `symbol`: Ticker symbol (e.g. `'BDMS'`, `'PTT'`).
- `side`: Order direction (`'BUY'`, `'SELL'`, `'SHORT'`, `'COVER'`).
- `volume`: Number of shares (integer).
- `price`: Limit price (float) or `'ATO'` / `'ATC'`.
- `pin`: 6-digit broker trading PIN.
- `account_type`: `'CASH_BALANCE'` (Equity) or `'DERIVATIVES'` (TFEX).
- `negotiate_price`: Boolean flag to enable passive price stepping.

### Outputs:
- `order_result`:
  - `status`: `'SUBMITTED'`, `'MATCHED'`, `'REJECTED'`, `'ANNEALED'`
  - `broker_order_no`: str
  - `matched_volume`: int
  - `matched_price`: float
  - `execution_timestamp`: ISO 8601 string

---

## 3. Step-by-Step Standard Operating Procedure

### Step 3.1: Pre-Trade Structural Guardrails
Before touching the browser DOM, validate every parameter strictly:
1. **Odd-Lot Restriction**:
   - Verify `volume % 100 == 0`. If false, abort immediately with error `"Reject Odd-lot: Volume must be multiple of 100"`.
2. **Account Capability Guard**:
   - If `side` in `('BUY', 'SELL', 'SHORT', 'COVER')`, account must be Equity (`CW32_E_...` or Cash Balance).
   - If `side` in `('LONG', 'SHORT')` on TFEX, account must be Derivatives (`CW32_D_...`).
   - `LONG` is strictly forbidden on Equity forms.
3. **Max Order Value Limit**:
   - Calculate `order_value = volume * price`.
   - Reject if `order_value > settings.MAX_SINGLE_ORDER_VALUE` (e.g. > 500,000 THB) without prior override.
4. **Kill Switch Verification**:
   - Check `kill_switch_service.is_active()`. If active, immediately abort all submissions.

### Step 3.2: Runbook-Driven Browser Execution
1. Load corresponding runbook specification from `learned_workflows/`:
   - Click2Win Equity: `click2win_order_submit.md`
   - TradeMan Order: `trademan_order_submit.md`
2. Follow steps sequentially:
   - Select Side (Buy / Sell / Short / Cover).
   - Focus Symbol input, type symbol, press Enter or wait for dropdown suggestion.
   - Fill Volume and Price fields.
   - Fill 6-digit Trading PIN.
   - Click Submit button.
   - Verify Confirmation Modal appears and click Confirm.
3. Extract `Order No.` and initial status (`Pending`, `Queuing`, `Matched`).

### Step 3.3: Self-Annealing Recovery on Failure
If any locator times out or element is blocked:
- Pass error trace and screenshot to `SelfAnnealingEngine`.
- Attempt Tier 1 fallback selectors.
- If still failing, trigger Tier 2 LLM patch on `learned_workflows/<name>.md`.
- If unresolvable, trigger Tier 3 emergency alert.

### Step 3.4: Tactical Price Negotiation (Passive Stepping)
1. At scheduled negotiation intervals (e.g. 10:45, 11:45, 14:45, 15:45):
   - Query unmatched orders in `portfolio_get_open_orders`.
   - Retrieve current Best Bid 1 and Best Offer 1.
   - For Buy/Cover: Adjust price to match current Best Bid 1 (step up if market moved away).
   - For Sell/Short: Adjust price to match current Best Offer 1 (step down if market moved lower).
   - Send `trade_modify_price` or cancel and re-submit.

### Step 3.5: End-of-Day (EOD) Order Purge
1. At 16:25 (prior to 16:30 Market Pre-Close/ATC):
   - Scan for all remaining Unmatched or Queuing orders.
   - Call `trade_cancel_order` for every pending order to ensure a clean overnight state.

---

## 4. Guardrails & Safety Constraints
- Live trades proceed autonomously if within risk limits, but can be halted immediately via the Emergency Kill Switch.
- Never re-submit an order blindly without verifying if the previous submission actually matched.

---

## 5. Definition of Done (DoD)
- Order submitted and validated on broker view order tab.
- Order record, execution price, and broker order ID stored in SQLite.
- LINE notification card sent with execution status.
