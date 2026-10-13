# RCA — LINE slash CLI (`app/services/line_cli/*`)

> Source: live test Round A 2026-10-13 (commit `0aecf8a`). Full evidence: `docs/handoff/TASK-line-cli-livetest-A.md`.

| ID | Severity | Symptom | Root cause | Fix (proposed) |
|---|---|---|---|---|
| CLI-RCA-001 | Low | `/cash kss` no reply once | `_send_reply` httpx 5s timeout to `api.line.me` (transient); no retry/fallback, empty error log | retry 1× + push fallback; log `type(e).__name__` |
| CLI-RCA-002 | **High** (R2 2026-10-14: card total P/L sign inverted vs app Unrealized P/L; per-row %P/L inverted for (S) rows; label "P/L วันนี้" wrong = unrealized) | `/port` no (S)/(B), SHORT P/L inverted | `_normalise_holdings` drops `position_type`; P/L formula LONG-only | keep field, tag rows, invert P/L for SHORT |
| CLI-RCA-003 | High (PARTIAL: 500k removed in 5f81cc5; 0.0 remains → see 009) | `/cash kss sync` missing Excess Equity | card shows only `is_active` account (default CASH); fallbacks 500,000/0.0 fabricate values | show CASH+MARGIN; `None` → "อ่านไม่ได้"; verify DOM selectors |
| CLI-RCA-004 | Med | `/orders` symbol unreadable on phone | 3-col `xs` no-wrap row truncates symbol | 2-line row, symbol `md` bold |
| CLI-RCA-005 | ~~High~~ **FIXED** (5f81cc5, re-tested C1 2026-10-13) | `/login lib` silent hang | pre-existing missing `import os` in `pillar1_session.py` L139; CLI no try/except after ack; tests mock whole login | import; wrap long ops → push ❌; test real LIB branch with driver mock |
| CLI-RCA-006 | **Critical** | `/port kss sync` shows wrong stocks with 🟢 live | `scrape_portfolio` uses the global `table tbody tr` (td≥8), so it also counts the totals table. Header and body are separate tables. Account select uses the stale `.v-list-item` (driver L366; the UI is now Tailwind). No reload. Probe 2026-10-13 confirmed this: see `learned_workflows/krungsri/trademan_portfolio_dom.md` | watch-and-learn DOM; scoped selector + header check + account select + refresh; gate Round B |
| CLI-RCA-007 | **Critical** | `/cash lib sync` shows Click2Win data (C2, 2026-10-13) | `portfolio_get_balances` (`pillar2_portfolio.py` L355-361) normalises platform with no LIBERATOR branch → `else: CLICK2WIN`; the `elif plat == "LIBERATOR"` block (L419) is dead code. Handler passes `"LIBERATOR"` (`handlers.py` L102). Broker-isolation violation + Anti-Mock (stale C2W data shown as 🟢 live) | add `LIBERATOR` to normalisation; unknown platform → raise, never default to C2W; test `/cash lib sync` routes to liberator_plugin; audit other `else: CLICK2WIN` fallbacks in pillar2 |
| CLI-RCA-008 | **Critical** | `/login kss` replies ✅ (no OTP) but browser ends at `https://trademan.in.th/SignIn` (C3, 22:27) | `auth_driver` saved-session check (L199-225) logs `SESSION_RESTORED` at 22:27:18 once `#dropDownAccountPort` is visible and URL has no `"login"`. Hypothesis: the SPA renders its shell or dropdown before the auth redirect, and the URL guard checks `"login"` but TradeMan uses `/SignIn`. Expired cookie → false AUTHENTICATED | URL guard covers `signin`; re-check URL/DOM after settling (~3s) or call an authenticated API; on fail → normal OTP flow (relay-gated) |
| CLI-RCA-009 | **Critical** | `/cash kss sync` shows 0.00 as 🟢 live (C3, 22:29) | `trademan_driver.scrape_account_summary` (L1957) ran on the SignIn page and returned all `0.0` defaults; it has no auth/URL/selector-found check. Same family as RCA-003 (Anti-Mock) | return `None` when selector not found; verify URL is authenticated before scraping; card shows "อ่านไม่ได้ / session หมดอายุ" |
| CLI-RCA-010 | Med | `/port kss sync` shows only 10 of 15 holdings ("…และอีก 5 ตัว"), user cannot see all (R2, 2026-10-14 04:35) | `handlers.py` L463/516 hard-cap `rows[:10]` + overflow line; Flex bubble sized for 10 rows | show all rows (paginate into a carousel of bubbles ≤12 rows each, or `/port kss all`); keep LONG/SHORT pair rows (ties to RCA-002) |
| CLI-RCA-011 | High | `/cash kss sync` card titled `KSS · CASH` shows one number as both "Cash balance" and "Buying power"; it equals the MARGIN account's **Line Available**, not any cash balance; EE missing (R3, 2026-10-14 04:49; compared to app Account Info) | `scrape_account_summary` returns a single value; `portfolio_get_balances` copies it into `cash_balance` + `line_available` of the CASH dict; handler picks `is_active` (CASH) while the page is on MARGIN 3024959. Mislabel + wrong account | probe the TradeMan web **Account Info** panel (bottom bar Trading A/C / Credit Limit / Excess Equity + expand chevron) per account; map fields by label: Credit Limit, Line Available, Excess Equity, Margin Required, %MM, Cash Balance; card title = account no read from DOM; CASH and MARGIN scraped separately |

## Proven fix — 2026-10-14 (Cline, TASK-cli-p0-data-integrity)

Status: **code + unit verified**; live re-test (A8/A9/A11 + C2/C3) still owned by Antigravity.

| ID | Change (code) | Evidence |
|---|---|---|
| CLI-RCA-006a | `trademan_driver.switch_account` → new `_select_account_on_page`: option `#dropDownAccountPort div.absolute span:text-is("<acc>")` (stale `.v-list-item` removed), popups dismissed first, current-account div (`#dropDownAccountPort > div.flex.w-full.justify-between > div`) re-read **after** the click; mismatch or missing dropdown → `success=False` + `status="ACCOUNT_SWITCH_FAILED"` (was a fake `UPDATED_CONTEXT`/`True`) | `tests/test_sbl_account_driver.py::test_switch_account_*` (5 tests) |
| CLI-RCA-006b | `trademan_driver.scrape_portfolio`: auth gate → account select + verify → **always reload** `/Portfolio` → `_PORTFOLIO_TABLES_JS` dumps the table inventory → `_pair_holdings_tables` pairs the `thead` table with its sibling `scrollbar-container` body table → `_map_holdings_columns` maps columns by header **name** → totals/placeholder rows skipped → each row carries the DOM `account_no`, and `portfolio_scrape_authenticated` gates the 🟢 badge | `tests/test_trademan_portfolio_scraper.py` (11; incl. real chromium `set_content` fixture: 15 rows where the legacy `table tbody tr` scan gives 16) |
| CLI-RCA-007 | `portfolio_get_balances`: `LIBERATOR`/`LIB` normalised to the Liberator branch, unknown platform → `ValueError` (no `else: CLICK2WIN`); `authenticated` exposed to the CLI | `tests/test_pillar2_portfolio_liberator.py`, `tests/test_line_cli_flow.py::test_live_cash_card_lib_uses_liberator_balances` |
| CLI-RCA-008 | `auth_driver.verify_saved_session`: URL guard covers `signin`, ~3 s settle + post-load re-check of URL **and** the 7-digit account div; on failure the previous quarantine/OTP path runs (Invariant 8/9) | `tests/test_auth_session_nondestructive.py` (3 new) |
| CLI-RCA-009 | `scrape_account_summary` returns `None` per unreadable field + `authenticated: False`; the body-text regex fallback (fabrication risk) is deleted; handlers render `cards.unavailable_card` — "⚠️ อ่านไม่ได้ / session หมดอายุ — /login kss" — and never 🟢 live | `tests/test_sbl_account_driver.py`, `tests/test_line_cli_flow.py` (5 new) |

## Proven fix — 2026-10-14 (Cline, TASK-cli-p1-display-and-redaction)

Status: **code + unit verified**; live re-test (`/port kss sync` sign check + log grep) owned by Antigravity.

| ID | Change (code) | Evidence |
|---|---|---|
| CLI-RCA-002 | `handlers._normalise_holdings` keeps `position_type` plus the page's own `unrealized_pnl`/`market_value`; new `_holding_pnl_pct` (LONG `(last−cost)/cost`, **SHORT `(cost−last)/cost`**, BORROWED / UNKNOWN / no cost base → `None` → renders `—`); new `_portfolio_totals` (Σ market value, Σ unrealized: prefers the DOM column, else side-aware `volume×(last−cost)` inverted for SHORT, `0.0` for BORROWED/UNKNOWN — never fabricated); `_read_db_positions` restores `Position.position_type`; `cards.port_card` tags `(S)`/`(B)` and renames `P/L วันนี้` → `Unrealized P/L`; `scrape_portfolio` no longer assumes `LONG` — an unmarked symbol becomes `UNKNOWN` (Open Q1: the marker still needs live confirmation) | `tests/test_line_cli_flow.py` (4 new: 5-case side matrix, SHORT fallback, carousel, tag + `—`), `tests/test_trademan_portfolio_scraper.py::test_scrape_portfolio_side_markers_short_borrowed_unknown` |
| CLI-RCA-010 | `port_card` drops the `overflow` / `…และอีก N ตัว` teaser and the `rows[:10]` caps at its call-sites; it paginates `PORT_ROWS_PER_BUBBLE = 12` rows per bubble into a LINE **carousel** (bubble 1 = totals + rows, later bubbles = rows only) so all 15 rows are reachable | `tests/test_line_cli_flow.py::test_port_card_paginates_into_carousel_and_drops_overflow_teaser` |
| F-5 / F-8 (log hygiene) | new shared `app/services/redaction.py`: `redact_otp()` → `******`, `redact_url()` → `?token=<redacted>`, `redact_otp_details()` for the relay details line. Applied at `otp_relay_registry` L269, `auth_driver` L501/L670/L864, `liberator/driver.py` L479/L525/L547/L566 (the console `print` of the full OTP is gone) | `tests/test_redaction.py` (5) |
| CLI-RCA (small) | `/cash lib` card header no longer leaks the raw enum: `handlers._ACCOUNT_TYPE_LABEL` maps `CASH_BALANCE → "Cash Balance"` (presentation only — the balance-value mapping stays untouched for RCA-011) | `tests/test_line_cli_flow.py::test_account_type_label_maps_raw_codes` |

### Invariants preserved
- Redaction is **log-only**: `otp_relay_registry.format_otp_details()` still writes the real OTP into
  `SessionLog.details`, because each driver parses it back with `auth_driver.OTP_SESSION_LOG_PATTERN`
  (cross-process hand-off in LINE-RCA-010). Guarded by
  `tests/test_redaction.py::test_db_relay_payload_keeps_the_real_otp`.
- `tests/test_sbl_account_driver.py::test_scrape_account_summary_dry_run` was environment-dependent: the
  500 000 DRY_RUN placeholder is returned only when `self.page is None`, and a live `data/session_state.json`
  (untracked, written by the real-browser tests) made the driver restore the session and scrape real DOM
  numbers. The test now patches `ensure_browser_ready` + forces `page=None`. Test-only change, outside the
  handoff file whitelist — flagged in the Cline Report.

### Notes / couplings
- `scrape_portfolio` deliberately does **not** call `switch_account()`: that path authenticates and could fire an SMS OTP from a background scrape (Invariant 9). Both now share `_select_account_on_page()`.
- Still open (out of handoff scope, reported): `switch_account`'s "browser not active" branch returns `success=True` with a settings-derived `account_no` (`SIMULATED_SWITCH`); `portfolio_holdings`/`current_orders` still contain their own `else: CLICK2WIN` fallbacks and propagate no auth flag (orders card cannot report "อ่านไม่ได้" yet).

## Live re-test P1 — 2026-10-14 05:34 (Antigravity)
- RCA-002 ✅ live: Unrealized P/L sign + value match the app; (S)/(B) tags shown. **Q1 resolved:** the web holdings Symbol cell carries `(S)`/`(B)` as text suffix.
- RCA-010 ✅ live: 2-bubble carousel, all rows reachable.
- RCA-008 ✅ live (valid-session path only; expired path = unit test).
- F-5/F-8 ✅ live: 0 OTP / `token=eyJ` hits in gateway log after restart.
- New, Low: **CLI-RCA-012** long symbol + suffix truncated (`DOHOME …`) in `port_card` symbol column → widen flex ratio or shrink suffix font.
- Observations (not yet RCA): per-row %P/L differs from app by ~0.02–0.11 pt (app likely includes fees in cost); card "มูลค่ารวม" matches neither app Amount nor Market Value → confirm which figure to show.
- F-10 (P2): `data/session_state.json` rewritten 05:12 while gateway was down → suspect non-hermetic real-browser test overwrote the live Zero-OTP session (Invariant 8). Audit tests that call `ensure_browser_ready`/`storage_state`.
- Resolved observation → **CLI-RCA-013 (Low, label/definition)**: card "มูลค่ารวม" = Σ(vol×last) of (S) rows only (verified = 531,932 from card rows). App *Market Value* = same + (B) rows (MTC 1,700×28.75 = 48,875 → 580,807). App *Amount* = Σ(vol×avg) cost basis (≈531,042); Unrealized = Amount − Market(S) = −889.59. Fix: show app-equivalent fields by label (Amount, Market Value) scraped from the DOM totals table, — **user chose option 1 (2026-10-14): show Amount + Market Value read from the DOM totals table, labelled as in the app.**

## Proven fix — 2026-10-14 (Cline, TASK-cli-p1_5-port-totals-and-symbol-width)

Status: **code + unit verified**; live re-test (`/port kss sync` vs Portfolio > Total, `DOHOME (S)` width)
owned by Antigravity.

| ID | Change (code) | Evidence |
|---|---|---|
| CLI-RCA-013 | `trademan_driver`: `_PORTFOLIO_TABLES_JS` returns `cls`; new `_find_totals_row()` locates the summary table **by position** next to the holdings pair (single ≥8-td row; `h-[2rem]` class, else a totals token — an unlabelled single-row table is refused) and `_pair_holdings_tables()` exposes it as `pair["totals"]`; new `_parse_float_or_none()` (blank/placeholder → `None`); `scrape_portfolio` fills `trademan_driver.portfolio_totals = {amount, market_value, unrealized_pnl, account_no}` (reset to `None` on every scrape, so a failed scrape never leaks stale figures). `handlers`: new `_portfolio_amount()` (Σ vol×avg, BORROWED excluded, `None` when no cost base); `_live_card`(port)/`_handle_read`(snapshot) prefer the on-page row for **KSS/TRADEMAN only** and fall back to computed Amount / Market Value. `cards`: header is now `Amount` / `Market Value` / `Unrealized P/L` (legacy `มูลค่ารวม` gone) with new `_money()` rendering `—` for `None` — never a fabricated `0.00` | `tests/test_trademan_portfolio_scraper.py` (7 new), `tests/test_line_cli_flow.py` (5 new: `test_live_port_card_prefers_dom_totals_row`, `test_port_card_header_labels_match_the_app`, `test_port_card_totals_render_dash_when_the_page_exposed_nothing`, `test_money_formats_thb_and_dash`, `test_portfolio_amount_excludes_borrowed_and_dom_totals_win`) |
| CLI-RCA-012 | `cards._cell()` gains `wrap`; `_port_row()` symbol cell `flex=3 → 4` + `wrap=True`, qty cell `flex=3 → 2` (numbers keep `size=xs`), `_port_header_row()` follows the same ratios — so `DOHOME (S)` renders in full instead of `DOHOME …` | `tests/test_line_cli_flow.py::test_port_card_keeps_long_symbol_with_suffix_unclipped` |

### Invariants preserved
- The Unrealized P/L formula + `%P/L` per side are untouched (P1); `portfolio_totals["unrealized_pnl"]` is
  stored but **not** used to render the card — the P1 side-aware logic still produces that figure.
- Broker isolation: only `KRUNGSRI`/`TRADEMAN` read `trademan_driver.portfolio_totals`; LIB keeps the
  computed Σ values (its `PositionItem` has no such row).
- Anti-Mock: no summary table, blank cell, or no cost base → `None` → `—` (never `0.0`), and the totals are
  cleared at the start of every scrape.

## Live re-test P1.5 — 2026-10-14 06:10 (Antigravity)
- RCA-012 ✅ live: `DOHOME (S)` rendered in full.
- RCA-013 ⚠️ live: card Market Value excludes MTC (B). Computed fallback includes (B), so this shows the card read the **web DOM totals row**, and the web TradeMan summary row's Market Value counts (S) rows only. The mobile app's Market Value includes (B). Web ≠ mobile definition. Awaiting user decision: follow web, or add (B) market value to match mobile.
