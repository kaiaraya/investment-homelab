# Learned Workflow: TradeMan "View Order" Ledger — Deterministic Table Isolation (Matched vs Unmatched)
**Workflow Name:** `trademan_view_order`  
**Recorded At:** 2026-10-07 14:30:02 UTC  
**Status:** `VERIFIED`  

## Description
Reads the Krungsri TradeMan "View Order" tab (the full Order Ledger) with deterministic isolation. The tab renders TWO sibling <table> elements inside one `div.relative.bg-[#1F2025]` section: a HEADER table (`div.pr-[20px] > table`, thead th = Order No.|Side|Symbol|Volume|Price|Matched|Status|Time|Quote) and a BODY table (`div.overflow-y-auto.scrollbar-container > table.w-full.relative`, 10 td/row). Anchor on the header table's own <thead> labels, then read the sibling body table — do NOT use the broad `table tbody tr` selector (it swallows the Watchlist/fund tables and shifts columns -> symbol=UNKNOWN, status=<time>, KSS-RCA-014). Side is a single code letter coloured by the app's own palette (B=BUY green, S=SELL red, H=SHORT #D964D7 magenta, C=COVER #478BCC blue -> TRADEMAN_SIDE_CODE_MAP). Status is a FULL WORD (Matched / Canceled / Reject). Time has its own column (8). Column map: 1=Order No. 2=Side 3=Symbol 4=Volume 5=Price 6=Matched 7=Status 8=Time 9=Quote 10=actions. Implemented in app/browser/trademan_driver.py -> _scrape_view_order_rows() (JS: _VIEW_ORDER_ROWS_JS), used by scrape_all_orders() and scrape_unmatched_orders().

## Execution Steps
| Step | Action | Target Selector | Value / Arguments | Description |
| :---: | :---: | :--- | :--- | :--- |
| 1 | `CLICK` | `div#order_btn` | `View Order` | Switch to the View Order tab. Use the unique id #order_btn — do NOT use div:has-text('View Order') (matches ancestors/navbar). |
| 2 | `WAIT` | `div.overflow-y-auto.scrollbar-container table` | `800` | Wait for the ledger body table to render. |
| 3 | `CHECK` | `table:has(thead th:text('Order No.'))` | `-` | Header table anchor: thead th must contain Order No. | Side | Symbol | Status (used to find the correct section). |
| 4 | `CHECK` | `td:nth-child(2)` | `B|S|H|C` | Side code (single letter). Map via TRADEMAN_SIDE_CODE_MAP: B=BUY, S=SELL, H=SHORT, C=COVER. |
| 5 | `CHECK` | `td:nth-child(4)` | `volume` | Ordered volume (strip commas, e.g. '2,300' -> 2300). |
| 6 | `CHECK` | `td:nth-child(5)` | `price` | Order price. |
| 7 | `CHECK` | `td:nth-child(6)` | `matched` | Matched volume; balance = volume - matched. |
| 8 | `CHECK` | `td:nth-child(7)` | `Matched|Canceled|Reject` | Status as a FULL WORD (not M/O/C). Feeds _classify_order_category(). |
| 9 | `CHECK` | `td:nth-child(8)` | `HH:MM:SS` | Time column (separate from Status). |
| 10 | `CLICK` | `#order_detail_btn` | `-` | Optional: open the Order Detail modal (renders as .v-overlay--active, NOT [role=dialog]). |

## Health Verification Rules
- [x] #order_btn is visible and the View Order tab is active
- [x] Header table with thead th 'Order No.' + 'Status' + 'Symbol' exists
- [x] Body table rows have >= 9 <td> cells
- [x] Side cell is one of B/S/H/C; Status cell is a full word (Matched/Canceled/Reject/Open/Partial)
- [x] No Watchlist (div.drag-container) rows are mixed into the ledger

---
*Maintained automatically by Playwright MCP Learning Loop*
