# TradeMan Portfolio / View Order — DOM map (probe 2026-10-13)

**Status:** PARTIALLY VERIFIED. This is read-only probe output and the input for the CLI-RCA-006 P0 handoff.
**Source:** `brain/<conv>/scratch/probe_trademan_dom.py` → `probe_out/D2..D5*.json`. Only structure was dumped, no money values.
**Supersedes selectors in:** `trademan_account_switch_and_portfolio.md`. Its `.v-list-item` selector is **STALE**: the UI is now Nuxt + Tailwind, not Vuetify.

## Page / tabs
- URL: `https://trademan.in.th/Portfolio`. The Portfolio and View Order tabs share this URL; switching tabs does not change it.
- Tabs: `div#port_btn` (Portfolio), `div#order_btn` (View Order).
- A "What's new" popup re-appears after navigation. It blocks clicks on `#dropDownAccountPort`: Playwright click timed out after 8s at D3. Dismiss popups before every interaction.

## Account switch (`#dropDownAccountPort`)
- Current account: `#dropDownAccountPort > div.flex.w-full.justify-between > div` (text = 7-digit acc no).
- Open the list by clicking `#dropDownAccountPort`. The list renders **inside** the same element, not as a modal or portal:
  - `#dropDownAccountPort div.absolute.w-full.top-8 > div.flex.flex-col > span.px-2.py-1.5`, one span per account.
- Selector to use: `#dropDownAccountPort div.absolute span:text-is("<acc_no>")`.
- After selecting, verify that the current-account div text equals the target before scraping.
- The user confirmed manually that selecting 3024952 changes the holdings table.
- Not verified by script: clicking the span. The probe filtered out in-dropdown nodes, which was a probe bug.

## Portfolio holdings (MARGIN 3024959 verified)
- The **header and body are separate `<table>` elements**:
  - Header table: `table.w-full.h-[2.5rem]`. It has `thead th` = `Symbol | On Hand | Sellable | Avg | Last | Cost | Market Value | Unreal | %Unreal | Real` and 0 body rows.
  - Body table: `div.overflow-y-auto.scrollbar-container.section > table.w-full.relative`. It has no thead; 15 rows, each with ≥8 td; the first td is the symbol.
  - Summary table: `table.w-full.h-[2rem]`. One row with ≥8 td, a totals row. **The legacy selector counts it as a holding.**
- Other tables on the page with symbol-like text:
  - A pie/legend widget table.
  - `#draggable-table-stocks` and `#draggable-table-funds` (watchlist / funds).
  - None of them have ≥8 td, so the legacy filter skips them by luck only.
- `table tbody tr` with td≥8 gives 16 rows = 15 holdings + 1 totals row.
- Duplicate symbols (BCPG×2, VGI×2) are probably LONG and SHORT rows of the same symbol (hypothesis, ties to CLI-RCA-002). Identify the side column/marker in the next probe.
- **CASH 3024952 holdings DOM: NOT captured.** All dumps show 3024959. Re-probe is needed to confirm it uses the same component.

## View Order (CASH 3024952, empty after hours)
- Header table: `table.w-full.h-[2.5rem].max-h-[35px]`, columns `Order No. | Side | Symbol | Volume | Price | Matched | Status | Time | Quote`.
  - **Symbol = column 3**, not column 1.
- Body table: `div.overflow-y-auto.scrollbar-container.section > table.w-full.relative`. With no orders it has 1 placeholder row with fewer than 8 td.
- The user confirmed the screen is empty. Scrape the open/matched order rows during market hours.

## Required scraper rules (for the RCA-006 fix)
1. Check that the session is authenticated: URL is not `/SignIn` and the current-account div is present (see CLI-RCA-008).
2. Dismiss popups, select the account explicitly, and verify the current-account text.
3. Locate the header table by its `thead th` texts, then take the **sibling** body table in the same container. Never use a global `table tbody tr`.
4. Map columns by header text index, not by fixed position. Skip the totals table and placeholder rows.
5. Re-navigate or refresh even when the URL already contains `Portfolio`.

## Open items
- CASH holdings DOM and the side (LONG/SHORT) marker column.
- Account-summary (cash / EE) selectors: not probed yet (CLI-RCA-003/009).
- Order rows with real data during market hours.

## Implementation status (CLI-RCA-006 fix, 2026-10-14)

Rules 1–5 above are now implemented in `app/browser/trademan_driver.py`:

| Rule | Code |
|---|---|
| 1. Authenticated session only | `_is_authenticated_page()` (no `/SignIn`, `#dropDownAccountPort > div.flex.w-full.justify-between > div` has 7 digits) — `scrape_account_summary`, `scrape_portfolio` |
| 2. Dismiss popups → select account → verify | `popup_manager.dismiss_popups()` then `_select_account_on_page(page, target)`; option span `#dropDownAccountPort div.absolute span:text-is("<acc>")`, verified against `_read_current_account_no()`, else `ACCOUNT_SWITCH_FAILED` |
| 3. Header table → sibling body table | `_PORTFOLIO_TABLES_JS` + `_pair_holdings_tables()` (never a global `table tbody tr`) |
| 4. Map by header name, skip totals/placeholder | `_map_holdings_columns()`, `_is_placeholder_or_totals_row()` |
| 4b. Read the summary/totals row (RCA-013) | `_find_totals_row()` (see the RCA-013 section below) |
| 5. Refresh even when the URL already has `/Portfolio` | `scrape_portfolio` always re-navigates before scraping |

`scrape_portfolio` returns the legacy keys plus `account_no` (read from the DOM), and sets
`portfolio_scrape_authenticated` — the CLI renders `cards.unavailable_card`
("⚠️ อ่านไม่ได้ / session หมดอายุ — /login kss") and never 🟢 live while it is `False`.
Evidence: `tests/test_trademan_portfolio_scraper.py` (real chromium `set_content` fixture built from
this DOM: 15 rows; the legacy scan returns 16).

## Holdings side markers + card rendering (CLI-RCA-002/010 fix, 2026-10-14)

- The holdings `Symbol` cell carries the side as a **text suffix**: `BCPG (S)` = short, `BCPG(B)` / `MTC (B)`
  = borrowed (avg cost 0.00). `scrape_portfolio` strips the marker into `raw_symbol`/`symbol` and stores
  `position_type` = `SHORT` / `BORROWED` / **`UNKNOWN` when no marker is present** — it must NOT default to
  `LONG`, because that inverts the P/L sign of a short. ⚠️ The marker itself is still unconfirmed live
  (Open Q1): if the live page turns out to use a separate column, change only the parsing in
  `_PORTFOLIO_TABLES_JS`/`_map_holdings_columns`, never the CLI layer.
- P/L rendering (shared with LIBERATOR — `PositionItem` has no side field, so it defaults to `LONG`):
  LONG `(last−cost)/cost`, SHORT `(cost−last)/cost`, BORROWED / UNKNOWN / no cost base → `—`.
  The card label is `Unrealized P/L` (this is **not** today's realized P/L).
- The `/port` card paginates `PORT_ROWS_PER_BUBBLE = 12` rows per bubble into a LINE carousel so all rows
  are reachable (the "…และอีก N ตัว" teaser is gone). The symbol cell is `flex=4` + `wrap: true` and the
  qty cell `flex=2`, so `DOHOME (S)` is no longer clipped (CLI-RCA-012).
- **P1.6 (2026-10-14):** the main table now carries only `(S)` (SHORT) tags — `handlers._split_borrowed()`
  moves every `BORROWED` row out, and the first bubble renders them in a `หุ้นยืมคงเหลือ (B)` section
  (`MTC  1,700 หุ้น`, qty only, no money) directly under `Unrealized P/L`. A `volume = 0` loan (e.g.
  `BCPG (B)`) is dropped; no loans → no heading. LIB never gets this section (broker isolation): its
  `PositionItem` has no side field and is always `LONG`.

## Totals row → `portfolio_totals` (CLI-RCA-013 fix, 2026-10-14)

- `_PORTFOLIO_TABLES_JS` now also returns `cls` (the table's `className`) so the summary table can be
  identified without a global selector.
- `_find_totals_row(tables, header_pos)` (new) returns the summary row's cell texts, or `None`:
  - candidates are the tables **after** the holdings header table that are neither the `thead` header nor
    the `in_scroll` body table and hold exactly **one row with ≥8 td**;
  - the table carrying the `h-[2rem]` class wins; otherwise the first candidate whose first cell is a
    totals token (`Total` / `ยอดรวม` / `มูลค่ารวม` / `sum` …);
  - a candidate matching **neither** rule is deliberately not claimed as totals → the CLI falls back.
- `_pair_holdings_tables()` returns it as `pair["totals"]`; `scrape_portfolio` parses the three numeric
  cells **by the header column positions** (`Cost → cost_value`, `Market Value`, `Unreal`) with the new
  `_parse_float_or_none()` and stores:

  ```python
  trademan_driver.portfolio_totals = {
      "amount", "market_value", "unrealized_pnl", "account_no"
  }   # None while no summary table; a blank/placeholder cell stays None (never 0.0)
  ```

  It is reset to `None` at the start of every scrape, so a failed/expired scrape can never leak a previous
  account's figures (Anti-Mock).
- `handlers._live_card` (port) uses `portfolio_totals["amount"]` **only for KSS/TRADEMAN** (broker isolation)
  and only when the DOM cell is not `None`; otherwise it falls back to `_portfolio_amount()` = Σ(vol×avg) of
  non-BORROWED rows. Unreadable → `—` via `cards._money()`.
- **P1.6 (2026-10-14):** `portfolio_totals["market_value"]` is still scraped but **no longer rendered** — the
  card header (first bubble) is `Amount` then `Unrealized P/L` only (legacy `มูลค่ารวม` gone). The
  `_portfolio_totals()` Σ(vol×last) total survives only as the `cost_base` term inside `%P/L`. Unrealized
  P/L formula unchanged (per side, P1).
- Evidence: `tests/test_trademan_portfolio_scraper.py` (7 new: summary row parsed / blank → `None` /
  absent → `None` / stale cleared / class-vs-token selection) and `tests/test_line_cli_flow.py`
  (DOM-preferred totals, labels, `—`, `_money`, BORROWED excluded, unclipped symbol).

## Summary keys after P2b (CLI-RCA-011, 2026-10-14)

- ⚠️ History (P2a, superseded): `scrape_account_summary()["cash_balance"]` used to hold the **Line Available**
  of the account on screen (the old selector list tried `Line Available` first), not a cash balance.
- P2b (2026-10-14) rewrote the selectors against the probed DOM and normalised the keys:
  `excess_equity` · `line_available` (PP for MARGIN / Buy Limit for CASH) · `real_cash_balance` (the Account
  Info `Cash Balance` row — MARGIN exposes it, CASH does not) · `credit_line` · `realized_pnl_today` ·
  `total_equity` · `account_no`. `cash_balance` is still emitted for the 5 legacy callers and is now an
  explicit **mirror of `line_available`** (`summary["cash_balance"] = summary["line_available"]`).
- Every key is `None` when its selector misses (Anti-Mock, RCA-009) — never `0.0`, and the body-text regex
  fallback stays removed.
- Since P2a the summary also carries `account_no`, read from
  `#dropDownAccountPort > div.flex.w-full.justify-between > div` via `_read_current_account_no()`, and is
  `None` when unreadable; `_unreadable_summary()` returns `account_no: None` too.
- `pillar2_portfolio.portfolio_get_balances` (KRUNGSRI) binds each figure **only** to the account whose
  number matches (`values_bound=True`); every other account gets `None`. `_bind()` maps `line_available`
  (falling back to the legacy `cash_balance` key), `cash_balance` ← `real_cash_balance` (the honest table
  row), `excess_equity`, `credit_line`, `total_equity`. The KSS `/cash` card therefore shows
  `Line Available`, an `Excess Equity` row for MARGIN, and a `Cash balance` row **only when
  `real_cash_balance` was actually read** — under the account it could read; nothing readable →
  `อ่านไม่ได้` (never 🟢 live).
- Probed & Discovered (P2b, 2026-10-14): The Account Info panel is always rendered at the bottom center
  of `/Portfolio` (no chevron click required). Verified via `scripts/krungsri/probe_account_info.py`
  dumps (`data/probe_out/account_info_*.json`).
- Evidence: `tests/test_sbl_account_driver.py`, `tests/test_remote_mcp.py`, `tests/test_line_cli_flow.py`,
  `tests/test_probe_account_info.py`.

## Ground-Truth DOM for Account Info & Bottom Bar (CLI-RCA-011 P2b, 2026-10-14)

### 1. Bottom Summary Bar (`div.bg-darkGray`)
Located at the bottom of the portfolio screen (`div.h-full.border-borderGray > div.flex.bg-darkGray`).
Divided into 3 centered columns (`div.text-center.h-full`):
- Label: `div.text-textGrayColor.text-xs`
- Value: `div.text-sm.font-semibold`

| Account Type | Col 1 | Col 2 | Col 3 |
|---|---|---|---|
| **MARGIN** | `Excess Equity` | `PP` (Purchasing Power) | `Equity` |
| **CASH** | `Credit Line` | `Buy Limit` | `Equity` |

Robust CSS selectors:
- Column Col: `div.bg-darkGray div.text-center:has-text('<LABEL>') div.text-sm, div.bg-darkGray div.text-center:has-text('<LABEL>') div.font-semibold`

### 2. Middle Account Info Table (`div.w-full.font-light > table.w-full`)
Each row `tr` consists of:
- `td:nth-of-type(1)`: Label container (`td.text-textGrayColor.justify-between > div:nth-of-type(1)` contains the label name, `div:nth-of-type(2)` contains `:`)
- `td:nth-of-type(2)`: Value container (`td.text-left` or `td.text-right` contains the formatted number / text)

Available Fields:
- **MARGIN (`Credit Balance`):**
  - Table 1 (Left): `Excess Equity`, `Equity`, `%MM`, `Margin Required`
  - Table 2 (Right): `Account Type`, `PP`, `Credit Line`, `Cash Balance`, `Liabilities (Loan)`
- **CASH (`Cash Balance`):**
  - Table: `Name`, `Account Type`, `Credit Line`, `Buy Limit`, `Equity`

Robust CSS selectors:
- `tr:has-text('<LABEL>') > td:nth-of-type(2)` (or `tr:has(td:has-text('<LABEL>')) > td:last-child`)
- Old selector bug: `td:has-text('Excess Equity') + td` failed because `+ td` matched nothing when label and colon were inside divs of td1, or when values were in the bottom summary bar.

### 3. Selectors shipped in `trademan_driver.scrape_account_summary` (P2b, verified)

| Field | Selector (Playwright `query_selector`, comma = first match wins) |
|---|---|
| `excess_equity` | `div.bg-darkGray div.text-center:has-text('Excess Equity') div.font-semibold`, `… div.text-sm`, `tr:has-text('Excess Equity') > td:nth-of-type(2)` |
| `line_available` | bottom bar `div.text-center:has-text('PP')` / `:has-text('Buy Limit')` `div.font-semibold` / `div.text-sm`, then `tr:has-text('PP')` / `:has-text('Buy Limit')` / `:has-text('Line Available')` `> td:nth-of-type(2)` |
| `real_cash_balance` | `tr:has-text('Cash Balance') > td:nth-of-type(2)` (MARGIN only) |
| `credit_line` | bottom bar `div.text-center:has-text('Credit Line') div.font-semibold` / `div.text-sm`, else `tr:has-text('Credit Line') > td:nth-of-type(2)` |
| `total_equity` | bottom bar `div.text-center:has-text('Equity'):not(:has-text('Excess')) div.font-semibold` / `div.text-sm`, else `tr:has-text('Equity'):not(:has-text('Excess')) > td:nth-of-type(2)` |
| `realized_pnl_today` | unchanged: `.realized-pnl-today`, `td:has-text('Realized P/L') + td`, `td:has-text('กำไรที่เกิดขึ้นจริง') + td` |

⚠️ **Collision guard (must keep):** the MARGIN bottom bar reads `Excess Equity` → `PP` → `Equity`, so a bare
`:has-text('Equity')` matches the **Excess Equity** column first and would report EE as the total equity.
`:not(:has-text('Excess'))` is what prevents it — regression-guarded by
`tests/test_sbl_account_driver.py::test_scrape_account_summary_reads_real_dom_selectors` (real chromium +
HTML fixture).

Evidence: `tests/test_sbl_account_driver.py` (per-field mock selectors + real-DOM fixture),
`tests/test_remote_mcp.py` (`_bind` mapping), `tests/test_line_cli_flow.py` (`/cash kss` card rows).


