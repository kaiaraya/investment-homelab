# Plan: LINE CLI Actionable Portfolio Cards with Nego-Priced Order Entry

**Date:** 2026-10-30  
**Author:** Hermes Agent  
**Workspace:** `/home/araya-sawasdichai/Documents/antigravity/InvestmentHomelab`  

---

## 1. Goal

Transform the LINE CLI portfolio display (`/port`, `/port all`, `/port <broker>`) into an interactive multi-broker Flex Carousel where each position row explicitly identifies its broker (Krungsri Margin vs Liberator Cash) and provides direct action buttons to submit negotiated orders (Sell for Long, Short + Return for Borrowed (B), and Cover for Short (S)) with passive auto-pricing via the existing draft confirmation workflow.

---

## 2. Current Context & Codebase Architecture

1. **Data Model & Position Extraction:**
   - In `app/services/line_cli/handlers.py` (`_read_db_positions`), the database positions are read by joining `Position` and `BrokerAccount.broker_code` (e.g. `kss`, `lib`). Each item already carries `r['broker']`.
   - `_split_borrowed(rows)` cleanly partitions rows into `main` (LONG, SHORT) and `borrowed` (BORROWED lots from SBL Realtime).
2. **Card Rendering Engine:**
   - In `app/services/line_cli/cards.py`, `port_card` paginates rows into bubbles of a Flex Carousel (`PORT_ROWS_PER_BUBBLE = 12`).
   - `_port_row(r)` and `_borrowed_row(b)` currently render text-only information with no action buttons.
3. **Trade Grammar & Order Draft Engine:**
   - Parser grammar (`_parse_trade` in `parser.py`) supports `/<side> [broker[:account]] <symbol> <amount> [price]`. If price is omitted, it sets `price = None`.
   - `_handle_trade_order` in `handlers.py` handles price resolution when `price is None`:
     - For `buy` and `cover`: Queues at **Bid 1** (passive queue / ต่อราคา).
     - For `sell` and `short`: Queues at **Offer 1** (passive queue / ต่อราคา).
   - After validation and safety guards (G1 SBL check, G2 Uptick rule), it presents `cards.trade_confirmation_card` with `trade_draft_confirm` and `trade_draft_cancel` buttons, perfectly enforcing the R3 human-in-the-loop safety gate.
   - For SBL return, `/return <symbol> all` triggers `_handle_return` which creates a return draft with `sbl_return_confirm`.

---

## 3. Proposed Architecture & Approach

1. **Broker Isolation & Labeling:**
   - Every row in the portfolio display will explicitly show its broker badge (e.g. `[LIB CASH]` or `[KSS MARGIN]`).
2. **Action Buttons per Position Type:**
   - **LONG Position (Default on LIB Cash / KSS Margin):**
     - Button: `🔴 ขาย (ต่อราคา)` -> sends message `/sell {broker} {symbol} {volume}`
     - Behaviour: Omits price -> triggers passive queue at Offer 1 -> presents `trade_confirmation_card`.
   - **BORROWED (B) Lot (KSS Margin SBL):**
     - Dual Buttons:
       1. `🟣 Short (ต่อราคา)` -> sends message `/short kss {symbol} {volume}`
       2. `🔄 คืนหุ้น (Return)` -> sends message `/return {symbol} all`
   - **SHORT (S) Position (KSS Margin):**
     - Button: `🔵 Cover (ต่อราคา)` -> sends message `/cover kss {symbol} {volume}`
     - Behaviour: Omits price -> triggers passive queue at Bid 1 -> presents `trade_confirmation_card`.
3. **Flex Layout Design:**
   - Because adding action buttons increases row height, we keep the compact two-line structure for data, followed by a dedicated button bar `box (horizontal)` with `height="sm"` action buttons.
   - Adjust `PORT_ROWS_PER_BUBBLE = 6` (from 12) so bubbles fit within LINE's mobile screen height without vertical scrolling.

---

## 4. Step-by-Step Implementation Tasks

### Task 1: Update Card Builders in `cards.py` with Action Buttons (TDD)

- **File:** `tests/test_line_cli_portfolio_actions.py` (New Test File)
- **Action:** Write failing unit tests checking that `_port_row` and `_borrowed_row` render the expected action buttons and broker tags.

```python
# tests/test_line_cli_portfolio_actions.py
import pytest
from app.services.line_cli import cards

def test_port_row_long_generates_sell_button():
    row = {
        "symbol": "PTT", "volume": 100, "cost": 33.0, "last": 34.0,
        "pnl_pct": 3.03, "position_type": "LONG", "broker": "lib",
    }
    box = cards._port_row(row)
    box_str = str(box)
    assert "LIB" in box_str
    assert "/sell lib PTT 100" in box_str
    assert "ขาย (ต่อราคา)" in box_str

def test_port_row_short_generates_cover_button():
    row = {
        "symbol": "TISCO", "volume": 500, "cost": 98.0, "last": 97.0,
        "pnl_pct": 1.02, "position_type": "SHORT", "broker": "kss",
    }
    box = cards._port_row(row)
    box_str = str(box)
    assert "KSS" in box_str
    assert "/cover kss TISCO 500" in box_str
    assert "Cover (ต่อราคา)" in box_str

def test_borrowed_row_generates_short_and_return_buttons():
    borrowed = {"symbol": "PTT", "volume": 100, "broker": "kss"}
    box = cards._borrowed_row(borrowed)
    box_str = str(box)
    assert "KSS" in box_str
    assert "/short kss PTT 100" in box_str
    assert "/return PTT all" in box_str
```

- **Verification Command:**
```bash
pytest tests/test_line_cli_portfolio_actions.py
```
*(Expected: Fails - functions do not yet generate action buttons)*

- **File:** `app/services/line_cli/cards.py`
- **Action:**
  1. Modify `PORT_ROWS_PER_BUBBLE = 6` to prevent oversized bubbles.
  2. Update `_port_row(r)` and `_borrowed_row(b)` to include broker tag and action buttons:

```python
def _port_row(r: Dict[str, Any]) -> Dict[str, Any]:
    ptype = str(r.get("position_type") or "LONG").upper()
    tag = " (S)" if ptype == "SHORT" else (" (B)" if ptype == "BORROWED" else "")
    pnl_pct = r.get("pnl_pct")
    if pnl_pct is None:
        pnl_cell = _cell("—", MUTED, flex=2, align="end")
    else:
        pc = float(pnl_pct)
        pnl_cell = _cell(f"{pc:+.2f}%", UP if pc >= 0 else DOWN, flex=2, align="end")

    sym = str(r.get("symbol", ""))
    vol = int(r.get("volume", 0))
    broker = str(r.get("broker", "lib")).lower()
    broker_badge = _BROKER_LABEL.get(broker, broker.upper())

    # Action buttons
    buttons: List[Dict[str, Any]] = []
    if ptype == "SHORT":
        buttons.append(_msg_button("🔵 Cover (ต่อราคา)", f"/cover {broker} {sym} {vol}", color="#1e40af"))
    elif ptype == "BORROWED":
        buttons.append(_msg_button("🟣 Short (ต่อราคา)", f"/short {broker} {sym} {vol}", color="#581c87"))
        buttons.append(_msg_button("🔄 คืนหุ้น", f"/return {sym} all", color="#334155"))
    else:
        buttons.append(_msg_button("🔴 ขาย (ต่อราคา)", f"/sell {broker} {sym} {vol}", color="#991b1b"))

    return {
        "type": "box", "layout": "vertical", "margin": "md", "spacing": "xs",
        "contents": [
            _row([
                _cell(f"[{broker_badge}] {sym}{tag}", FG, flex=4, weight="bold", wrap=True),
                _cell(f"{vol:,}", FG, flex=2, align="end"),
                _cell(f"{float(r.get('cost', 0.0)):.2f}", FG, flex=2, align="end"),
                _cell(f"{float(r.get('last', 0.0)):.2f}", FG, flex=2, align="end"),
                pnl_cell,
            ]),
            {
                "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "xs",
                "contents": buttons,
            },
        ],
    }

def _borrowed_row(b: Dict[str, Any]) -> Dict[str, Any]:
    sym = str(b.get("symbol", ""))
    vol = int(b.get("volume", 0))
    broker = str(b.get("broker", "kss")).lower()
    broker_badge = _BROKER_LABEL.get(broker, broker.upper())

    buttons = [
        _msg_button("🟣 Short (ต่อราคา)", f"/short {broker} {sym} {vol}", color="#581c87"),
        _msg_button("🔄 คืนหุ้น", f"/return {sym} all", color="#334155"),
    ]
    return {
        "type": "box", "layout": "vertical", "margin": "sm", "spacing": "xs",
        "contents": [
            _row([
                _cell(f"[{broker_badge}] {sym} (B)", WARN, flex=4, weight="bold", wrap=True),
                _cell(f"{vol:,}", FG, flex=3, align="end"),
                _cell("ยืม SBL", MUTED, flex=3, align="end"),
            ]),
            {
                "type": "box", "layout": "horizontal", "spacing": "sm", "margin": "xs",
                "contents": buttons,
            },
        ],
    }
```

- **Verification Command:**
```bash
pytest tests/test_line_cli_portfolio_actions.py
```
*(Expected: 3 passed)*

---

### Task 2: Pass Broker Code from Handlers into Rows

- **File:** `app/services/line_cli/handlers.py`
- **Action:** Ensure `_read_db_positions` and `_broker_sync_cdp` correctly populate `r['broker'] = broker_code` for all positions and borrowed items.
  - In `_split_borrowed(rows)`: preserve `r['broker']` inside the borrowed dicts:

```python
def _split_borrowed(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    src = rows or []
    def _is_borrowed(r: Dict[str, Any]) -> bool:
        return str(r.get("position_type") or "LONG").upper() == "BORROWED"
    main = [r for r in src if not _is_borrowed(r)]
    borrowed = sorted(
        ({
            "symbol": str(r.get("symbol", "")),
            "volume": int(r.get("volume", 0) or 0),
            "broker": str(r.get("broker", "kss")).lower(),
        }
        for r in src if _is_borrowed(r) and int(r.get("volume", 0) or 0) > 0),
        key=lambda b: b["symbol"],
    )
    return main, borrowed
```

- **Verification Command:**
```bash
pytest tests/test_line_cli_flow.py -k test_port
```
*(Expected: Passes)*

---

### Task 3: Regression & End-to-End Suite Verification

- **Action:** Run the full LINE CLI test suite to verify that parser, handlers, draft confirmation, and other cards continue functioning seamlessly.
```bash
pytest tests/test_line_cli_*.py
```
*(Expected: 100% tests passed, 0 failures)*

---

## 5. Tests & Validation Plan (TDD)

| Phase | Test Target | Description / Expected Result |
| :--- | :--- | :--- |
| **Red** | `tests/test_line_cli_portfolio_actions.py` | Verify failure when buttons & broker badges are not yet rendered |
| **Green** | `tests/test_line_cli_portfolio_actions.py` | Verify 3 tests pass with buttons `/sell`, `/short`, `/cover`, `/return` |
| **Regression** | `pytest tests/test_line_cli_*.py` | All existing CLI tests (parser, flow, order draft, sbl) pass |

---

## 6. Risks, Tradeoffs & Open Questions

1. **LINE Bubble Height Limit:**
   - *Risk:* Multiple rows with buttons could make the bubble taller than mobile screen limits.
   - *Mitigation:* Set `PORT_ROWS_PER_BUBBLE = 6` (instead of 12) so carousel bubbles paginate smoothly without overflowing.
2. **Execution Safety Gate (R3 Compliance):**
   - *Design Choice:* Buttons use `type: "message"` instead of instant execution postback. The message triggers the existing `_handle_trade_order` flow, which looks up the real-time order book, plans the passive price, and requires user confirmation via `trade_confirmation_card` before submitting to the broker.
3. **Broker Parameter in Slash Commands:**
   - Using `/<cmd> <broker> <symbol> <volume>` (e.g. `/sell lib PTT 100`) is already natively supported by `_has_override` in `parser.py`, guaranteeing correct broker routing without human guesswork.
