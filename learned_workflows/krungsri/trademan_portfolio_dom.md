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
- The `/port` card tags rows `(S)`/`(B)` and paginates `PORT_ROWS_PER_BUBBLE = 12` rows per bubble into a
  LINE carousel so all 15 rows are reachable (the "…และอีก N ตัว" teaser is gone). The symbol cell is
  `flex=4` + `wrap: true` and the qty cell `flex=2`, so `DOHOME (S)` is no longer clipped (CLI-RCA-012).

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
- `handlers._live_card` (port) uses `portfolio_totals` **only for KSS/TRADEMAN** (broker isolation) and only
  when the DOM cell is not `None`; otherwise it falls back to the computed values — Amount =
  `_portfolio_amount()` = Σ(vol×avg) of non-BORROWED rows, Market Value = `_portfolio_totals()` = Σ(vol×last)
  **including** `(B)` rows. Unreadable → `—` via `cards._money()`.
- Card header (first bubble) is now `Amount` / `Market Value` / `Unrealized P/L` — the app's own labels; the
  legacy `มูลค่ารวม` label is gone. The Unrealized P/L formula is unchanged (per side, P1).
- Evidence: `tests/test_trademan_portfolio_scraper.py` (7 new: summary row parsed / blank → `None` /
  absent → `None` / stale cleared / class-vs-token selection) and `tests/test_line_cli_flow.py`
  (DOM-preferred totals, labels, `—`, `_money`, BORROWED excluded, unclipped symbol).

