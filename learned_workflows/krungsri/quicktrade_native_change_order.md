# Krungsri Quick Trade Native Change Price & Volume Runbook
`learned_workflows/krungsri/quicktrade_native_change_order.md`

- **Generated At**: 2026-10-14 (Market Open Live Probe)
- **Target Application**: Krungsri Quick Trade (`fastorder.jsp`) & Settrade Order Details (`app.settrade.com/order-status-detail/`)
- **Protocol**: Interactive Probe & Verification
- **Verified Order**: `11008198` (MTC, Side Short @ 29.25, Account `3024959`)

---

## 1. Architectural Overview & Workflow Path

```mermaid
flowchart TD
    A["Krungsri Member Portal SSO<br/>(/Put_SSO_Settrade.aspx?Page=place_order)"] --> B["Quick Trade Multi-Market Application<br/>(/realtime/fastorder/fastorder.jsp)"]
    B -->|Select #accInv| C["Credit Balance Account (3024959)"]
    C -->|Realtime Quote| D["#eqQuoteSymbol + #instBidOfferEq (5 Bids/Offers)"]
    
    C -->|Table #orderBodyEq| E["Open Orders Ledger<br/>(Order No, Symbol, Side, Price, Vol, Status)"]
    
    E -->|Direct URL Navigation| F["Settrade Order Detail Popup<br/>(app.settrade.com/order-status-detail/?brokerId=029&accountNo=3024959&orderNo=11008198)"]
    F -->|Click Button| G["Change Price& Volume Modal"]
    G -->|Fill input[name='price']| H["New Negotiated Price"]
    G -->|Fill input[name='pin']| I["Trading PIN"]
    G -->|Click Button| J["Submit -> Live Market Amendment"]
```

---

## 2. Verified DOM Selectors & Endpoints

### 2.1 Quick Trade (`fastorder.jsp`)
| Element | Selector | Usage / Details |
|---|---|---|
| **Account Selector** | `#accInv` (`name="txtAccountNo"`) | Dropdown with options: `3024952 (Equity)` and `3024959 (Equity)` |
| **Quote Symbol Input** | `#eqQuoteSymbol` | Fill stock symbol (e.g. `MTC`, `CPALL`) |
| **Quote Button** | `#btnGetQuotes` / `input[value='Get Quotes']` | Triggers real-time bid/offer update |
| **Bid/Offer Table** | `#instBidOfferEq` | 5 rows of `Volume | Bid | Offer | Volume` |
| **Market Info Table** | `#instInfoEq` | Contains `High/Low`, `Ceil./Floor`, `Avg./Close` |
| **Order Ledger Table** | `#orderBodyEq` | Rows of active orders with columns: `Checkbox`, `Order no`, `Symbol`, `Date`, `Time`, `Side`, `Price`, `Volume`, `Matched`, `Balance`, `Cancelled`, `Status` |
| **Detail Button** | `input[value='Detail']` / `button:has-text('Detail')` | Opens order detail popup for selected checkbox |

### 2.2 Settrade Order Detail Popup (`app.settrade.com/order-status-detail/`)
- **Direct Entry URL**:
  `https://app.settrade.com/order-status-detail/?brokerId=029&accountNo={account_no}&orderNo={order_no}&tradeDate={YYYY-MM-DD}`
- **Buttons on Page**:
  - `button:has-text('Change Price& Volume')`
  - `button:has-text('Cancel Order')`
  - `button:has-text('Change A/C Type')`
- **When 'Change Price& Volume' is clicked**:
  - Price Input: `input[name='price']` (or input associated with Price label)
  - Volume Input: `input[name='volume']` (or input associated with Volume label)
  - PIN Input: `input[name='pin']` / `input[placeholder*='PIN' i]`
  - Submit Button: `button:has-text('Submit')`
  - Back Button: `button:has-text('Back')`

---

## 3. Regulatory Safety Invariants (Strict)
1. **Short Sell Uptick Rule (STRICT)**:
   Under SET rules a short may only be amended to a price **strictly above** `LastPrice`
   (`validator.validate_short_uptick` — the zero-plus tick on `LastPrice` is rejected).
   `plan_negotiation()` aborts with `UPTICK_VIOLATION` when `Best Offer 1 < LastPrice` (down-tick)
   **and** when the final target would equal `LastPrice`.
2. **Volume Invariance**:
   Passive price negotiation only alters `price`. `volume` must remain identical to existing `balance`.
3. **Session Reusability**:
   Uses `data/session_state.json`. Zero-OTP.

---

## 4. Pillar 6 Implementation (2026-10-14) — Passive Price Negotiation

| Layer | Artifact | Behaviour |
|---|---|---|
| Policy (pure) | `app/services/quicktrade_negotiation_service.py` → `plan_negotiation()` | BUY→Best Bid 1 · SELL/SHORT→Best Offer 1 · SHORT→`max(Offer1, Last)`; volume is copied from `balance`, never changed; guardrails **G4** `validate_tick_size` → `TICK_SIZE_VIOLATION` · **G5** `tick_distance_exceeds()` ≤ `LINE_NEGO_MAX_TICKS` → `MAX_TICKS_EXCEEDED` (reason states the tick count) · **G6** `validate_short_uptick` (strict) → `UPTICK_VIOLATION`; every refusal clears `target_price` |
| Driver | `app/brokers/krungsri/quicktrade_driver.py` | `get_quote` (`#eqQuoteSymbol` + `#btnGetQuotes` → `#instBidOfferEq`/`#instInfoEq`) · `get_order` (searches `candidate_accounts()` = MARGIN → CASH — see `rca/krungsri/rca_krungsri_quicktrade.md` KSS-QT-RCA-001) · `amend_price` (direct order-detail URL → `Change Price& Volume` → price + PIN → Submit) · `list_open_orders()` (read-only `#orderBodyEq` scrape; `pending_orders()` keeps `balance > 0`) |
| Orchestration | `negotiate_order_price(order_no, …)` (same service module) | resolves the snapshot → live quote → policy → `amend_price` on `OK` only; `execute=False` = plan only |
| REST | `POST /api/v1/krungsri/quicktrade/negotiate-price` (`app/api/v1/quicktrade.py`) | broker-isolated router mounted in `app/api/v1/api.py` |
| LINE | `/nego kss [SYMBOL\|order_no]` (`handlers.py::_handle_nego`) · `/negotiate <order_no>` = **alias** of it | G1 kill-switch → G2 `LINE_NEGO_WINDOWS` → G3 session alive → per-broker lock (`CLI_BUSY`); discovery = `list_open_orders()`; LIVE amend = `negotiate_order_price()` on the SAME order_no; card = `negotiate_card` (one explicit order_no) / `nego_card` (batch) |

Safety: **Zero-OTP** (reads `data/session_state.json`; never logs in, never fires SMS) · `settings.DRY_RUN_MODE`
gates the Submit · **Anti-Mock** (unknown order / unreadable quote / uptick violation are reported as failures —
never a fabricated price or a fabricated submission).

### 4.1 LINE command registration (required — easy to miss)
A new slash command needs **both** edits, or the parser rejects it with `E_UNKNOWN_CMD` before the handler runs:
`app/services/line_cli/parser.py` `COMMAND_ALIASES` (+ the target-token branch when it takes an argument)
**and** the dispatch inside `handlers.handle()`. `/negotiate` therefore added `"negotiate": "negotiate"` plus
`canonical in ("nego", "negotiate")`, and does **not** require a broker token.

### 4.2 Verification (no browser needed)
- `.venv/bin/python -m pytest tests/test_quicktrade_negotiation_policy.py tests/test_quicktrade_driver.py -q`
- LINE flow: `tests/test_line_cli_flow.py` (bad-args · kill-switch · out-of-hours · OK card · uptick violation)
  and `tests/test_line_cli_parser.py` (alias/target/bad-target).
- `.venv/bin/python scripts/verify_changes.py <changed files>` → **PASS** (152 tests, compileall OK, 2026-10-14).
- The handoff's `tests/test_line_cli_handlers.py` does **not** exist — the correct mapping is
  `tests/test_line_cli_flow.py` (handlers + cards) and `tests/test_line_cli_parser.py` (parser).

### 4.3 Send-state contract (Anti-Mock — verified 2026-10-14)

`amend_price()` always returns `success` / `submitted` / `dry_run` (plus `status`, `price_field`, `new_price`;
`error` on failure). **`submitted` is the only field that says whether anything reached the broker:**

| Situation | `success` | `submitted` | `status` |
|---|---|---|---|
| LIVE amendment accepted | `True` | `True` | `SUBMITTED` |
| DRY-RUN staged (price + PIN filled, Submit **not** clicked) | `True` | `False` | `STAGED_DRY_RUN` |
| Rejected / aborted (no account, no session, uptick, unknown order, amendment refused) | `False` | `False` | — |

`negotiate_order_price()` initialises `submitted` / `dry_run` to `None` and mirrors the amendment's values to
the top level, so a REST/remote consumer can never infer a live amendment from `success` alone. The LINE card
renders `True → ส่งเข้าตลาดแล้ว` · `False → จัดเตรียมไว้ (TEST/DRY-RUN)` · `None → —`; the handler reads
`submitted` from `result["amendment"]` (never from `success`). Locked by
`test_amend_price_result_always_carries_submitted_and_success_keys` (driver),
`test_negotiate_order_price_dry_run_reports_unsubmitted_amendment` + `..._reports_amendment_failure` (service),
`test_negotiate_dry_run_card_never_claims_a_live_submission` (LINE flow).

### 4.4 Live Verification Status
1. **DRY-RUN live probe of `amend_price`**:
   - ✅ **VERIFIED (2026-10-14 17:08)**: Live headed probe completed successfully on order `11008198` (Credit Balance `3024959`).
   - Ground-truth DOM: Settrade order detail uses Angular Reactive Forms without `name`/`id` on inputs:
     - Price: `input[formcontrolname='price']`
     - Volume: `input[formcontrolname='vol']`
     - PIN: `input[placeholder='PIN']` / `input[type='password']`
   - Verified on modal: Price staged to `29.50`, volume preserved at `1,700`, PIN filled, Submit untouched (`DRY-RUN` guaranteed).
   - Screenshot logged: `data/screenshots/quicktrade_amend_dryrun.png`.
2. **LIVE `/negotiate <order_no>` in LINE group**:
   - Staging test available via `/negotiate 11008198`. Submission remains gated by `settings.DRY_RUN_MODE` until live market trading window.

---

## 5. Unified `/nego` (2026-10-15) — one in-place path for kss

`/nego kss [SYMBOL|order_no]` and `/negotiate <order_no>` now run the **same** code path
(`handlers._handle_nego`); `/negotiate` rewrites itself into `/nego kss <order_no>`.

Flow: G1 kill-switch → G2 `LINE_NEGO_WINDOWS` → G3 session alive → per-broker lock → discovery
(`quicktrade_driver.list_open_orders()` on `#orderBodyEq`, MARGIN first) → target filter (order_no or symbol)
→ `_plan_nego()` preview → LIVE: `_broker_modify("kss")` → `negotiate_order_price()` (in place, same order_no)
→ card (`negotiate_card` for one explicit order_no, else `nego_card`).

**Rules that must not regress**
- **No cancel+replace for kss**: `trademan_driver.modify_order_price` must never be reachable from `/nego`
  (locked by `test_broker_modify_kss_live_uses_quicktrade_in_place`).
- The card/audit row mirrors the **service's** outcome: `NO_CHANGE` and the G4/G5/G6 refusals are **skips**, and a
  DRY-RUN staging is labelled — a refusal is never counted as `ok`
  (`test_nego_kss_live_refusal_is_reported_as_skipped`).
- An unreadable ledger raises, so the command reports ❌ instead of "no pending orders".
- LIB is untouched by this section (its hardening is `TASK-loop1-3`).

Verify: `.venv/bin/python scripts/verify_changes.py app/services/quicktrade_negotiation_service.py app/brokers/krungsri/quicktrade_driver.py app/services/line_cli/handlers.py`
→ **PASS (125 targeted, compileall OK, 2026-10-15)**. Live witness: **not yet** (`TASK-loop1-4`).

