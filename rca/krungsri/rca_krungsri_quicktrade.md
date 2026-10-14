# RCA — Krungsri Quick Trade (`fastorder.jsp` + Settrade FastOrder order-detail)

Surface: Krungsri Securities **Member SSO → Quick Trade** (`www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=place_order`
→ `/realtime/fastorder/fastorder.jsp`) plus the Settrade shared order-detail page
(`app.settrade.com/order-status-detail/`), brokerId `029`.

Knowledge is kept **separate from `rca_krungsri_trademan.md`** (Broker/Application Isolation): Quick Trade is a
different application with its own DOM, URLs and amendment mechanism. Never reuse TradeMan selectors or the
TradeMan cancel+resend amendment path here.

- Runbook: `learned_workflows/krungsri/quicktrade_native_change_order.md`
- Code: `app/brokers/krungsri/quicktrade_driver.py`, `app/services/quicktrade_negotiation_service.py`,
  `app/api/v1/quicktrade.py`, LINE `/negotiate` (`app/services/line_cli/handlers.py`)
- ID space: `KSS-QT-RCA-###` (the TradeMan `KSS-RCA-###` sequence in `rca_krungsri_trademan.md` is untouched)

---

## KSS-QT-RCA-001 (2026-10-14) — Order ledger is account-scoped; a pinned account hides the order

**Symptom**: `get_order("11008198")` returned `order … not found in open-order ledger` even though the order
was visible and live on the Quick Trade screen.

**Root cause**: `#orderBodyEq` only ever renders the rows of the account currently selected in `#accInv`.
The ledger reader defaulted to whatever `_select_account(None)` left selected (the first option,
`3024952` CASH), while the target order belonged to `3024959` (MARGIN/Credit Balance).

**Edge cases**
- The same order number can exist in both accounts → the account must be part of the result, never guessed.
- `#accInv` options come from the broker (`3024952`, `3024959`); they are already mirrored as
  `settings.TRADEMAN_ACCOUNT_NO_CASH` / `TRADEMAN_ACCOUNT_NO_MARGIN` — do **not** hardcode them again.
- A missing/renamed option must fail closed, not silently read the wrong ledger.

**Proven solution**
- `KrungsriQuickTradeDriver.candidate_accounts()` → `[MARGIN, CASH]` (deduped, blank skipped).
- `get_order(order_no, account_no=None)` iterates the candidates, selecting each account before reading the
  ledger, and returns `account_no` = the account that actually held the order.
- The discovered `account_no` is then threaded into `get_quote` and `amend_price` (Settrade URL `accountNo=`).
- Guarded by `tests/test_quicktrade_driver.py::test_candidate_accounts_are_deduped_and_ordered` and the
  orchestration test `test_negotiate_order_price_resolves_snapshot_and_amends` (asserts the account reaches `amend_price`).

**User feedback**: pending live `/negotiate 11008198` re-test by Antigravity.

---

## KSS-QT-RCA-002 (2026-10-14) — Amendment is in place (`Change Price& Volume`), not cancel+resend

**Symptom / risk**: The TradeMan habit (KSS-RCA-016: `modify_order_price` = cancel + re-submit) would leave an
order gap and lose queue priority if applied to Quick Trade.

**Root cause**: Quick Trade is Settrade-backed and **does** expose a native amendment
(`Change Price& Volume` on the order-detail page) — the TradeMan limitation does not transfer.

**Edge cases**
- `input[name='volume']` must never be written — passive negotiation changes price only (volume invariance).
- Submission is gated by `settings.DRY_RUN_MODE` (default True): fill price + PIN, do not click Submit.
- SHORT must respect the strict SET uptick rule: `Best Offer 1 < LastPrice` → abort (`UPTICK_VIOLATION`),
  fail closed; never fabricate `last`.

**Proven solution**: one submission path only — `amend_price()` (price field + PIN → `Submit`), with
`dry_run`/`pin` defaulting to settings and `submitted` reported honestly in the result. The policy lives in
`quicktrade_negotiation_service.plan_negotiation` (pure, testable) and never mutates the driver.

**User feedback**: pending live re-test (DRY_RUN first, then LIVE).

---

## KSS-QT-RCA-003 (2026-10-14) — `success` means "plan processed", not "the broker amended the order"

**Symptom / risk (caught in unit review, before any live call)**: `amend_price()` returns `success=True` for a
DRY-RUN staged amendment (`submitted=False`, `status=STAGED_DRY_RUN`). Any caller reading only `success` would
report a price change that never reached the broker — an Anti-Mock violation (Invariant 1). The same payload is
what the REST endpoint hands to a remote consumer.

**Root cause**: two different truths were collapsed into one flag — "the amendment call completed" vs "the broker
accepted the new price". The LINE card disambiguated via `submitted`, but the payload did not expose the send
state at its top level, so `success=True` was the only signal a non-UI caller could see.

**Edge cases**
- DRY-RUN must report `submitted=False` (not a missing key, not `None`) — `None` means *nothing was attempted*
  (`NO_QUOTE` / `NO_CHANGE` / `UPTICK_VIOLATION` / `execute=False` / unknown order), which is a different state.
- A refused amendment (`success=False`, driver `error` set) must not look like a staging.
- If a refactor drops the `submitted` key, the card silently degrades to `—` → the key is now asserted by test.

**Proven solution**
- Driver contract: `amend_price()` always returns `success` / `submitted` / `dry_run` (+ `status`, `price_field`,
  `new_price`, or `error`). `submitted` comes only from `_submit(page, dry_run)`, i.e. `True` only when `Submit`
  was actually clicked.
- `negotiate_order_price()` initialises `submitted` / `dry_run` to `None` and mirrors
  `amendment["submitted"]` / `amendment["dry_run"]` after a real call.
- Card: `True → ส่งเข้าตลาดแล้ว` · `False → จัดเตรียมไว้ (TEST/DRY-RUN)` · `None → —` (never inferred from `success`);
  the handler reads `result["amendment"]["submitted"]`.
- Tests: `test_amend_price_result_always_carries_submitted_and_success_keys` (driver) ·
  `test_negotiate_order_price_dry_run_reports_unsubmitted_amendment` + `..._reports_amendment_failure` (service) ·
  `test_negotiate_dry_run_card_never_claims_a_live_submission` (LINE flow).

**User feedback**: pending the live `/negotiate <order_no>` re-test (runbook §4.4).

