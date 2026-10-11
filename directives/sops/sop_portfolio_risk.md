# Standard Operating Procedure (SOP): Portfolio Intelligence & Risk Sentinel
**Document ID:** `SOP-005`  
**Governing Sub-Agent:** `PortfolioRiskAgent`  
**Version:** 1.0  
**Effective Date:** 2026-10-03  

---

## 1. Objective & Scope
Define the standard procedures for managing multi-account portfolio synchronization, balance reconciliation, holding audits, dynamic risk monitoring (Max Drawdown, Position Sizing, Missing Stop-Loss Audits), and End-of-Day (EOD) portfolio reporting across Click2Win Sandbox and Krungsri Accounts.

---

## 2. Input & Output Contracts

### Inputs:
- `target_account`: Account number or type (`'EQUITY_CASH'`, `'DERIVATIVES_TFEX'`, `'CREDIT_BALANCE'`).
- `force_sync`: Boolean flag to trigger live browser scrape vs cached state.

### Outputs:
- `portfolio_snapshot`:
  - `account_id`: str
  - `cash_balance`: float
  - `line_available`: float
  - `excess_equity_ee`: float
  - `total_market_value`: float
  - `total_unrealized_pnl`: float
  - `positions`: List of positions (Symbol, Volume, Avg Cost, Market Price, Unrealized PnL %)
- `risk_audit_report`:
  - `unprotected_positions`: List of positions without defined Stop-Loss levels.
  - `max_drawdown_current`: float
  - `risk_alerts`: List of warning messages.

---

## 3. Step-by-Step Standard Operating Procedure

### Step 3.1: Multi-Account Context Switching
1. Read current active tab in broker trading screen:
   - For Equity: Ensure tab shows Cash Balance or Equity Account No.
   - For TFEX: Switch to Derivatives account tab (`CW32_D_...`).
2. Verify that account context matches the intended asset class before extracting balances.

### Step 3.2: Balance & Holding Reconciliation
1. Call `portfolio_get_balances` to extract:
   - Cash Balance, Line Available, Total Equity, Excess Equity.
2. Call `portfolio_get_holdings` to extract:
   - Symbol, Volume, Available Volume, Avg Cost, Current Price, Unrealized PnL, PnL %.
3. Reconcile with SQLite database:
   - Update `positions` table: upsert existing records and mark closed positions.
   - Update `account_balances` history.

### Step 3.3: Risk & Protective Stop-Loss Audit
1. Review any open position that lacks a protective TP/SL plan.
   - NOTE (2026-10-06): The former `portfolio_audit_risk_and_tpsl` MCP tool was **removed** together
     with the Pillar 2 "Monitor & Alert" feature (intraday monitor engine, alert rules and the
     `app/monitoring/` package). Protective TP/SL levels are now held on the position record
     (`take_profit_price` / `stop_loss_price`) and audited manually here; the automated Phase 3.2
     Alert Center engine (`alert_center_service`) was also removed on 2026-10-06.
   - If an unprotected position is found, notify user via LINE with recommended 2.0% Stop-Loss level.
2. Check Max Drawdown limit:
   - If intraday portfolio drawdown exceeds **5.0%**, trigger risk warning and advise halting new buys.

### Step 3.4: Pre-Flight Morning Audit (09:30 - 09:45)
1. Ensure all positions carried overnight are synchronized with accurate cost bases.
2. Verify margin collateral requirements for any open TFEX or SBL positions.
3. Emit a Pre-Market Health Summary to LINE.

### Step 3.5: End-of-Day (EOD) Reconciliation (16:35)
1. Collect final closing prices and settled PnL for the trading day.
2. Generate comprehensive Thai EOD Performance Card:
   - Daily Realized PnL
   - Open Positions Unrealized PnL
   - Net Portfolio Value
   - Total Trades Executed
3. Send EOD report to LINE messaging channel.

---

## 4. Guardrails & Safety Constraints
- Total exposure per single stock must not exceed **25%** of total portfolio equity.
- If Excess Equity (EE) drops below minimum maintenance margin on TFEX or SBL, issue high-priority warning immediately.

---

## 5. Definition of Done (DoD)
- Holdings and balances 100% matched between broker DOM and local SQLite database.
- EOD performance report published and logged.
