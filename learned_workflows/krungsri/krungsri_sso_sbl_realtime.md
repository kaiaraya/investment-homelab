# Krungsri SSO SBL Real Time Navigation & Extraction Runbook
`learned_workflows/krungsri_sso_sbl_realtime.md`

- **Generated At**: 2026-10-03
- **Source**: Krungsri Securities Member SSO Portal (`https://www.krungsrisecurities.com/`)
- **Protocol**: Watch-and-Learn Interactive Co-pilot Protocol (`/watch-and-learn`, `/playwright-studio`)
- **Target Application**: Krungsri SBL Real Time (`/sblweb/MainSBL.aspx`)
- **Authentication**: Pre-authenticated Session State (`data/session_state.json`)

---

## 1. Architectural Overview & Workflow Path

Unlike the legacy TradeMan SBL screen, the genuine Krungsri SBL Real Time system is hosted directly on Krungsri's Member Portal SSO infrastructure:

```mermaid
flowchart TD
    A["Krungsri Member Portal<br/>(th/main/default.aspx)"] -->|Click #sbls or Nav Menu| B["SBL Disclaimer Gate<br/>(th/discliaimer-sbl/Default.aspx?start=sbl)"]
    B -->|Click a.disclaimer<br/>href='javascript:popup(../../th/SBL/start.aspx)'| C["SBL Start Handler<br/>(th/SBL/start.aspx)"]
    C -->|Redirects to| D["Krungsri SBL Real Time Application<br/>(/sblweb/MainSBL.aspx)"]
    
    D --> E["SET 50 Inventory Grid<br/>(#MainCenter_lbSet50)"]
    D --> F["SET 100 Inventory Grid<br/>(#MainCenter_lbSet100)"]
    D --> G["NEW SEC Inventory Grid<br/>(#MainCenter_lbNewSec)"]
    D --> H["XD / XR Corporate Actions Risk Table<br/>(#MainCenter_lbXD)"]
    D --> I["Purchasing Power & Borrow Execution<br/>(#ctl00_MainCenter_ctl00_MainCenter_pnlBorrowPanel)"]
    D --> J["Active Borrow Transaction Table<br/>(#ctl00_MainCenter_rgTrans_ctl00)"]
```

---

## 2. Direct Navigation Strategy (Autonomous Execution)

When pre-authenticated with `data/session_state.json`:
- **Direct Entry URL**: `https://www.krungsrisecurities.com/th/SBL/start.aspx`
- This endpoint validates member session cookies and immediately routes to the active SBL Real Time application at `https://www.krungsrisecurities.com/sblweb/MainSBL.aspx`.
- Popup Window Dimensions: `1100 x 800` (or maximized `1280 x 850`).

---

## 3. Verified DOM Selectors & Schema

### 3.1 Top Navigation Tabs
| Tab Name | Selector | Action / Description |
| :--- | :--- | :--- |
| **SET 50** | `#MainCenter_lbSet50` | Swaps grid to top 50 market cap borrowable stocks |
| **SET 100** | `#MainCenter_lbSet100` | Swaps grid to top 100 market cap borrowable stocks |
| **NEW SEC** | `#MainCenter_lbNewSec` | Swaps grid to newly added eligible securities |
| **XD, XR** | `#MainCenter_lbXD` | **CRITICAL RISK TAB**: Shows stocks with upcoming XD, XR, XM corporate actions |
| **Refresh** | `#MainCenter_lbRefresh` | Re-queries latest inventory from Krungsri SBL server |

### 3.2 Inventory Grid Data Layout
The inventory grids (SET50, SET100, NEW SEC) are rendered across 4 columnar sub-tables:
- Table Headers: `Symbol | Fee | Volume | IM`
  - `Symbol`: Stock ticker (e.g. `ADVANC`, `BDMS`, `CPALL`)
  - `Fee`: Annualized borrow fee percentage (typically `3.50%`)
  - `Volume`: Available share inventory for borrowing (e.g. `5,014,000`, `0`)
  - `IM`: Initial Margin percentage required (typically `50%` or `60%`)

### 3.3 XD / XR Risk Table (Mandatory Short-Sell Blocker)
When clicking `#MainCenter_lbXD`:
- Columns: `Symbol | Book Date | Type`
  - `Symbol`: Stock ticker (e.g. `SAWAD`, `PTT`, `LH`)
  - `Book Date`: Record Date / Effective Date (e.g. `06/10/2026`)
  - `Type`: Corporate action code (`XD` = Dividend, `XR` = Rights Offering, `XM` = Meeting)
- **Risk Invariant**:
  > [!CAUTION]
  > Under Thai SBL regulations, borrowers holding a short position over an XD date are legally required to manufacture 100% of dividend compensation back to the lender.
  > Any symbol present in this tab **MUST BE HARD-BLOCKED** from automated short selling in the Homelab engine!

### 3.4 Account Information & Purchasing Power
| Field | Selector / Extraction Pattern | Example Value |
| :--- | :--- | :--- |
| **Customer Code** | `#ctl00_MainCenter_txSearchCode` / `#ctl00_MainCenter_txtCusCode` | `302495` |
| **Customer Name** | `#ctl00_MainCenter_lbCusName` | `คุณอารยะ สวัสดิชัย` |
| **Purchasing Power (PP)**| `#ctl00_MainCenter_ctl00_MainCenter_pnlBorrowPanel` regex `PP = ([0-9,.]+)` | `96,885.94` THB |

### 3.5 Active Borrow Transactions Table
- Container Table: `#ctl00_MainCenter_rgTrans_ctl00`
- Row Columns:
  1. `Ref.No`: Borrow contract reference ID (e.g. `B494343`)
  2. `Tran Date`: Borrow date (`DD/MM/YYYY`)
  3. `Time`: Execution time (`HH:MM:SS`)
  4. `Symbol`: Stock symbol (e.g. `KBANK`)
  5. `Type`: `B` (Borrow)
  6. `Quantity`: Number of shares borrowed
  7. `Borrowing Price`: Closing/settlement price on borrow date
  8. `Borrowing Value`: Total borrowed value in THB
  9. `Fee Rate`: Interest fee rate (`3.5%`)
  10. `Close Date`: Date loan was closed/returned
  11. `คืนหุ้น` (Return): Anchor `a[id*='RadReturn']` triggering `ShowReturnForm(refNo, rowIdx)`

### 3.6 Borrow Submission Form (Lower Panel)
| Field | Selector | Usage |
| :--- | :--- | :--- |
| **Customer Code** | `#ctl00_MainCenter_txtCusCode` | Readonly `302495` |
| **Stock Symbol** | `#ctl00_MainCenter_txtSymbol` | Fill stock symbol uppercase (e.g. `BDMS`) |
| **Borrow Quantity** | `#ctl00_MainCenter_txtQty` | Fill number of shares to borrow |
| **Submit Button** | `#MainCenter_lbBorrow` | PostBack trigger for `__doPostBack('ctl00$MainCenter$lbBorrow','')` |

---

## 4. Playwright Autonomous Execution Snippet

```python
import re
from playwright.async_api import async_playwright

async def run_krungsri_sbl_extraction():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        executable_path="/usr/bin/google-chrome"
    )
    context = await browser.new_context(
        storage_state="data/session_state.json",
        viewport={"width": 1280, "height": 850}
    )
    page = await context.new_page()

    # Step 1: Direct navigation into SBL Real Time
    await page.goto("https://www.krungsrisecurities.com/th/SBL/start.aspx", wait_until="networkidle")

    # Step 2: Extract Purchasing Power
    body_text = await page.inner_text("body")
    pp_match = re.search(r"PP\s*=\s*([0-9,.]+)", body_text)
    purchasing_power = float(pp_match.group(1).replace(",", "")) if pp_match else 0.0

    # Step 3: Extract SET50 Inventory
    set50_items = await extract_inventory_grid(page)

    # Step 4: Extract XD/XR Risk Calendar
    await page.click("#MainCenter_lbXD")
    await page.wait_for_timeout(1500)
    xd_items = await extract_xd_xr_grid(page)

    await browser.close()
    await playwright.stop()
    return {
        "purchasing_power": purchasing_power,
        "set50": set50_items,
        "xd_risk": xd_items
    }
```
