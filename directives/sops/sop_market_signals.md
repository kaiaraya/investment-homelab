# Standard Operating Procedure (SOP): Market Intelligence & Signal Monitoring
**Document ID:** `SOP-002`  
**Governing Sub-Agent:** `MarketAnalystAgent`  
**Version:** 1.0  
**Effective Date:** 2026-10-03  

---

## 1. Objective & Scope
Define standard procedures for processing incoming trading signals (via LINE messages or daily strategy sheets), maintaining high-frequency real-time price feeds via Settrade Open API (MQTT WebSocket), detecting abnormal price swings, and evaluating Take Profit (TP) and Stop Loss (SL) triggers.

---

## 2. Input & Output Contracts

### Inputs:
- `raw_signal_text`: Thai/English text from webhook or strategy report.
- `tickers`: List of stock tickers to monitor.
- `tp_price`: Target Take Profit price level.
- `sl_price`: Cut loss Stop Loss price level.
- `position_side`: Position direction (`'LONG'` or `'SHORT'`).

### Outputs:
- `structured_signal`: `SignalParseResult` with immediate orders, watchlist triggers, and hold positions.
- `price_alert_event`:
  - `symbol`: str
  - `trigger_type`: `'TAKE_PROFIT'`, `'STOP_LOSS'`, `'ABNORMAL_SWING'`
  - `last_price`: float
  - `threshold`: float
  - `action_recommended`: `'SELL'`, `'COVER'`, or `'ALERT_ONLY'`

---

## 3. Step-by-Step Standard Operating Procedure

### Step 3.1: Signal Extraction & Parsing
1. Ingest raw text through `signal_agent` (PydanticAI + Gemini 3.8 Flash).
2. Clean stock tickers: uppercase, strip brackets or Thai notes (e.g. `'AOT (ไม้ 1)'` -> `'AOT'`).
3. Classify action urgency:
   - Immediate Execution: Cut Loss, Time-Exit, Breakout Buy today.
   - Watchlist Triggers: Dynamic Trailing Stop or Take Profit levels.
   - Hold Positions: Track days held and return %.

### Step 3.2: High-Frequency Price Feed Registration
> ⚠️ **SUPERSEDED (2026-10-06)** — Monitor & Alert ถูกลบทั้งระบบแล้ว: ไม่มี MCP tool ชื่อ
> `monitor_register_position` / `monitor_get_realtime_quote` / `alert_add_rule` ในโค้ดอีก
> (ดู `docs/handoff/TASK-pillar2-portfolio-refactor.md`). อย่าปฏิบัติตามขั้นตอนนี้
1. ~~For every active position or watchlist trigger, call `monitor_register_position`:~~
   - Bind symbol to Settrade Open API v2 MQTT Stream.
   - Establish Dual-Direction TP/SL rules:
     - **Long Position**: TP triggered when `last_price >= tp_price`; SL triggered when `last_price <= sl_price`.
     - **Short Position**: TP triggered when `last_price <= tp_price`; SL triggered when `last_price >= sl_price`.

### Step 3.3: Abnormal Fluctuation Monitoring
> ⚠️ **SUPERSEDED (2026-10-06)** — Alert Center engine (`alert_center_service`) ถูกลบแล้ว; ขั้นตอนนี้ไม่ทำงาน
1. ~~Continuous background check for price deviations:~~
   - Calculate `%change = (last_price - previous_close) / previous_close * 100`.
   - If `%change` exceeds **+/- 3.0%** in a single session, trigger an abnormal swing event.
   - Dispatch an interactive Alert Card to LINE with current Bid/Offer spread.

### Step 3.4: Dispatch to Execution Engine
1. When a TP or SL threshold is breached:
   - Verify tick validity (filter out zero-volume erroneous ticks).
   - Dispatch structured event to `MasterOrchestrator` -> `OrderExecutionAgent`.
   - Send LINE notification summary of the trigger event.

---

## 4. Guardrails & Safety Constraints
- Max simultaneous monitored tickers: **30** (to avoid excessive memory consumption).
- Do not trigger orders on stale quote ticks (> 15 seconds without timestamp update).
- Respect market hours: Quotes received outside 09:55 - 16:35 are flagged as `OFF_MARKET_TICK` and will not trigger autonomous market executions.

---

## 5. Definition of Done (DoD)
- Raw signals parsed into structured JSON adhering to `SignalParseResult`.
- Real-time quote stream active with latency under 50ms.
- Alerts dispatched to LINE within 1 second of trigger event.
