"""RCA-006b tests — TradeMan portfolio scraper (header/body table pairing + header-name mapping).

DOM structure under test comes from ``learned_workflows/krungsri/trademan_portfolio_dom.md``
(probe 2026-10-13): a *separate* header table, a body table inside
``div.overflow-y-auto.scrollbar-container.section``, a summary/totals table, and
symbol-like widgets (``#draggable-table-stocks``).

All tests are mocked or use a local headless Chromium with ``set_content`` — no broker
login, no OTP (Invariant 9).
"""
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from app.browser.trademan_driver import (
    _find_totals_row,
    _is_placeholder_or_totals_row,
    _map_holdings_columns,
    _pair_holdings_tables,
    _PORTFOLIO_TABLES_JS,
    trademan_driver,
)
from app.core.config import settings

# 15 holdings, with duplicate symbols (LONG/SHORT of the same ticker) per the runbook
_SYMBOLS = [
    "CPALL", "PTT", "AOT", "ADVANC", "BBL", "BCPG", "BCPG(B)", "VGI", "VGI(B)",
    "KBANK", "SCB", "TTB", "DELTA", "GULF", "PTTEP",
]

_HEADERS = [
    "Symbol", "On Hand", "Sellable", "Avg", "Last", "Cost",
    "Market Value", "Unreal", "%Unreal", "Real",
]


def _body_row(sym: str, i: int) -> str:
    return (
        f"<tr><td>{sym}</td><td>1,{i:02d}0</td><td>1,{i:02d}0</td><td>10.00</td><td>11.00</td>"
        f"<td>{i}0,000.00</td><td>{i}1,000.00</td><td>1,000.00</td><td>10.00%</td><td>0</td></tr>"
    )


def _fixture_html() -> str:
    """HTML fixture mirroring the probed TradeMan /Portfolio DOM."""
    ths = "".join(f"<th>{h}</th>" for h in _HEADERS)
    rows = "".join(_body_row(sym, i) for i, sym in enumerate(_SYMBOLS, start=1))
    return f"""<html><body>
      <table class="w-full"><tbody><tr><td>Legend</td><td>MARGIN</td></tr></tbody></table>
      <table id="draggable-table-stocks"><thead><tr><th>Symbol</th><th>Price</th><th>Change</th></tr></thead>
        <tbody><tr><td>PTT</td><td>35.00</td><td>+0.25</td></tr></tbody></table>
      <div class="section">
        <table class="w-full h-[2.5rem]"><thead><tr>{ths}</tr></thead><tbody></tbody></table>
        <div class="overflow-y-auto scrollbar-container section">
          <table class="w-full relative"><tbody>{rows}</tbody></table>
        </div>
      </div>
      <table class="w-full h-[2rem]"><tbody><tr>
        <td>Total</td><td>20,000</td><td>20,000</td><td>-</td><td>-</td><td>200,000.00</td>
        <td>220,000.00</td><td>20,000.00</td><td>10.00%</td><td>0</td>
      </tr></tbody></table>
    </body></html>"""


def _runbook_inventory():
    """Table inventory exactly as ``_PORTFOLIO_TABLES_JS`` reports it for ``_fixture_html()``.

    (The browser-backed test below re-validates this against the real JS.)
    """
    def cells(sym, i):
        return [sym, f"1,{i:02d}0", f"1,{i:02d}0", "10.00", "11.00",
                f"{i}0,000.00", f"{i}1,000.00", "1,000.00", "10.00%", "0"]

    return [
        {"cls": "w-full", "headers": [], "rows": [["Legend", "MARGIN"]],
         "in_scroll": False, "has_thead": False},
        {"cls": "", "headers": ["Symbol", "Price", "Change"], "rows": [["PTT", "35.00", "+0.25"]],
         "in_scroll": False, "has_thead": True},
        {"cls": "w-full h-[2.5rem]", "headers": list(_HEADERS), "rows": [],
         "in_scroll": False, "has_thead": True},
        {"cls": "w-full relative", "headers": [],
         "rows": [cells(sym, i) for i, sym in enumerate(_SYMBOLS, start=1)],
         "in_scroll": True, "has_thead": False},
        # RCA-013: the on-page summary row — Cost/Market Value/Unreal carry real values
        {"cls": "w-full h-[2rem]", "headers": [],
         "rows": [["Total", "20,000", "20,000", "-", "-", "200,000.00",
                   "220,000.00", "20,000.00", "10.00%", "0"]],
         "in_scroll": False, "has_thead": False},
    ]


# ==========================================
# Pure Python: column mapping / row filtering / table pairing
# ==========================================

@pytest.fixture(autouse=True)
def _isolate_driver_state():
    """The driver is a module-level singleton: pin MARGIN and restore state afterwards."""
    saved = (
        trademan_driver.active_account_no,
        trademan_driver.active_account_type,
        trademan_driver.portfolio_scrape_authenticated,
        trademan_driver.portfolio_totals,
    )
    trademan_driver.active_account_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN
    trademan_driver.active_account_type = "MARGIN"
    trademan_driver.portfolio_scrape_authenticated = False
    yield
    (
        trademan_driver.active_account_no,
        trademan_driver.active_account_type,
        trademan_driver.portfolio_scrape_authenticated,
        trademan_driver.portfolio_totals,
    ) = saved

def test_map_holdings_columns_by_name_not_position():
    idx = _map_holdings_columns(list(_HEADERS))
    assert idx == {
        "symbol": 0, "on_hand": 1, "sellable": 2, "avg_cost": 3, "current_price": 4,
        "cost_value": 5, "market_value": 6, "unrealized_pnl": 7, "pnl_pct": 8,
    }


def test_map_holdings_columns_keeps_unreal_and_pct_unreal_apart():
    idx = _map_holdings_columns(["Symbol", "Market Value", "%Unreal", "On Hand", "Unreal"])
    assert idx["pnl_pct"] == 2
    assert idx["unrealized_pnl"] == 4


def test_map_holdings_columns_reorders_when_columns_move():
    """Names win over positions: a moved 'Market Value' column must be followed."""
    idx = _map_holdings_columns(["On Hand", "Symbol", "Market Value", "Avg"])
    assert idx["symbol"] == 1
    assert idx["on_hand"] == 0
    assert idx["market_value"] == 2
    assert "sellable" not in idx


def test_pair_holdings_tables_picks_body_not_totals_table():
    pair = _pair_holdings_tables(_runbook_inventory())
    assert pair is not None
    assert pair["header"]["headers"] == list(_HEADERS)
    # 15 holdings — never 16 (the totals table is a separate element)
    assert len(pair["body"]["rows"]) == 15
    assert all(row[0] != "Total" for row in pair["body"]["rows"])


def test_pair_holdings_tables_returns_none_without_holdings_header():
    assert _pair_holdings_tables(_runbook_inventory()[1:2]) is None       # watchlist only
    assert _pair_holdings_tables([]) is None


def test_find_totals_row_prefers_summary_class_and_returns_cost_cell():
    """RCA-013: the h-[2rem] summary row is found by position, not a global selector."""
    inventory = _runbook_inventory()
    pair = _pair_holdings_tables(inventory)
    assert pair["totals"] is not None
    row = _find_totals_row(inventory, None)
    assert row is not None and row[0] == "Total"
    assert row[5] == "200,000.00"                   # Cost column → Amount


def test_find_totals_row_falls_back_to_totals_token_without_class():
    inventory = _runbook_inventory()
    inventory[-1]["cls"] = ""                       # class attribute absent in the DOM
    pair = _pair_holdings_tables(inventory)
    row = _find_totals_row(inventory, None)
    assert row is not None and row[0] == "Total"


def test_find_totals_row_returns_none_without_summary_table():
    inventory = [t for t in _runbook_inventory() if "2rem" not in (t.get("cls") or "")]
    assert _find_totals_row(inventory, None) is None


def test_find_totals_row_ignores_unlabelled_single_row_table():
    """A single >=8-td table with no summary class and no totals token is NOT totals."""
    inventory = [t for t in _runbook_inventory() if "2rem" not in (t.get("cls") or "")]
    inventory.append({"cls": "w-full", "headers": [],
                      "rows": [["สรุปพอร์ต", "1", "2", "3", "4", "5", "6", "7", "8"]],
                      "in_scroll": False, "has_thead": False})
    assert _find_totals_row(inventory, None) is None


def test_is_placeholder_or_totals_row():
    assert _is_placeholder_or_totals_row("Total", ["Total", "20,000", "220,000.00"]) is True
    assert _is_placeholder_or_totals_row("ยอดรวม", ["ยอดรวม", "20,000"]) is True
    assert _is_placeholder_or_totals_row("", ["", "", ""]) is True
    assert _is_placeholder_or_totals_row("-", ["-", "-", "-"]) is True
    assert _is_placeholder_or_totals_row("ไม่พบข้อมูล", ["ไม่พบข้อมูล", "-"]) is True
    assert _is_placeholder_or_totals_row("CPALL", ["CPALL", "800", "800", "46.25"]) is False

# ==========================================
# Real DOM: run the production JS against the HTML fixture
# ==========================================

def _find_local_chromium():
    """Fallback to any chromium build already present in the ms-playwright cache."""
    import glob
    import os

    patterns = (
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux/chrome",
    )
    root = os.path.expanduser("~/.cache/ms-playwright")
    for pattern in patterns:
        hits = sorted(glob.glob(os.path.join(root, pattern)), reverse=True)
        if hits:
            return hits[0]
    return None


@pytest.mark.asyncio
async def test_portfolio_tables_js_against_html_fixture():
    """The production `_PORTFOLIO_TABLES_JS` must see 15 body rows + a separate totals table."""
    pytest.importorskip("playwright.async_api")
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception as exc:  # this env's ms-playwright build != the driver's revision
            exe = _find_local_chromium()
            if not exe:
                pytest.skip(f"Playwright chromium unavailable: {exc}")
            try:
                browser = await pw.chromium.launch(headless=True, executable_path=exe)
            except Exception as exc2:
                pytest.skip(f"Playwright chromium unavailable: {exc} / fallback {exe}: {exc2}")
        try:
            page = await browser.new_page()
            await page.set_content(_fixture_html())
            inventory = await page.evaluate(_PORTFOLIO_TABLES_JS)
        finally:
            await browser.close()

    assert len(inventory) == 5
    assert any("2rem" in (t.get("cls") or "") for t in inventory)   # summary table class
    pair = _pair_holdings_tables(inventory)
    assert pair is not None
    assert pair["header"]["headers"] == list(_HEADERS)
    assert len(pair["body"]["rows"]) == 15          # 15, never 16
    assert pair["body"]["rows"][0][0] == "CPALL"
    assert _map_holdings_columns(pair["header"]["headers"])["market_value"] == 6
    # the legacy `table tbody tr` scan would have returned the totals row too
    legacy_rows = [r for t in inventory for r in t["rows"] if len(r) >= 8]
    assert len(legacy_rows) == 16


# ==========================================
# scrape_portfolio() end-to-end with a mocked page
# ==========================================

def _mock_portfolio_page(inventory, url="https://trademan.in.th/Portfolio", current=None):
    """Mock page exposing the account-dropdown DOM plus a canned table inventory."""
    current = current or settings.TRADEMAN_ACCOUNT_NO_MARGIN

    header_el = AsyncMock()
    header_el.inner_text.return_value = f"Trading A/C {current}"

    page = AsyncMock()
    page.url = url
    page.is_closed = MagicMock(return_value=False)      # sync in Playwright
    page.query_selector.side_effect = lambda selector: (
        header_el if str(selector).startswith("#dropDownAccountPort > div.flex") else None
    )
    page.wait_for_selector.return_value = AsyncMock()   # #dropDownAccountPort button
    page.evaluate.return_value = inventory
    return page


async def _run_scrape(page, switch_result=None):
    """Run scrape_portfolio() with browser/login/popup paths patched (no OTP)."""
    with patch.object(type(trademan_driver), "page", new_callable=PropertyMock, return_value=page):
        with patch.object(trademan_driver, "ensure_browser_ready", new_callable=AsyncMock):
            with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new_callable=AsyncMock):
                if switch_result is None:
                    return await trademan_driver.scrape_portfolio()
                with patch.object(trademan_driver, "_select_account_on_page",
                                  new_callable=AsyncMock, return_value=switch_result):
                    return await trademan_driver.scrape_portfolio()


@pytest.mark.asyncio
async def test_scrape_portfolio_maps_rows_by_header_and_sets_account_no():
    margin_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN
    page = _mock_portfolio_page(_runbook_inventory())

    holdings = await _run_scrape(page)

    assert len(holdings) == 15                      # totals row excluded
    assert trademan_driver.portfolio_scrape_authenticated is True
    assert trademan_driver.active_account_no == margin_no
    assert {h["account_no"] for h in holdings} == {margin_no}
    assert "Total" not in {h["raw_symbol"] for h in holdings}
    assert len({h["raw_symbol"] for h in holdings}) == 15        # no dedupe of LONG/SHORT

    cpall = holdings[0]
    assert cpall["symbol"] == "CPALL"
    assert cpall["on_hand"] == 1010 and cpall["volume"] == 1010
    assert cpall["avg_cost"] == 10.0 and cpall["current_price"] == 11.0
    assert cpall["cost_value"] == 10_000.0
    assert cpall["market_value"] == 11_000.0
    assert cpall["unrealized_pnl"] == 1_000.0
    assert cpall["pnl_pct"] == 10.0
    assert cpall["position_type"] == "UNKNOWN"      # RCA-002: no "(S)"/"(B)" marker → unknown side

    borrowed = [h for h in holdings if h["position_type"] == "BORROWED"]
    assert [h["symbol"] for h in borrowed] == ["BCPG", "VGI"]
    page.goto.assert_awaited()                      # re-loaded even though URL had /Portfolio


@pytest.mark.asyncio
async def test_scrape_portfolio_side_markers_short_borrowed_unknown():
    """RCA-002: ``(S)``/``(B)`` set the side; an unmarked symbol must stay UNKNOWN."""
    def cells(sym):
        return [sym, "1,000", "1,000", "10.00", "11.00",
                "10,000.00", "11,000.00", "1,000.00", "10.00%", "0"]

    inventory = [
        {"headers": list(_HEADERS), "rows": [], "in_scroll": False, "has_thead": True},
        {"headers": [], "rows": [cells("LH(S)"), cells("MTC"), cells("BCPG(B)")],
         "in_scroll": True, "has_thead": False},
    ]
    page = _mock_portfolio_page(inventory)

    holdings = await _run_scrape(page)

    by_sym = {h["symbol"]: h for h in holdings}
    assert by_sym["LH"]["position_type"] == "SHORT"
    assert by_sym["LH"]["raw_symbol"] == "LH(S)"
    assert by_sym["MTC"]["position_type"] == "UNKNOWN"      # no marker → never assume LONG
    assert by_sym["BCPG"]["position_type"] == "BORROWED"


@pytest.mark.asyncio
async def test_scrape_portfolio_returns_empty_and_not_live_when_session_expired():
    page = _mock_portfolio_page(_runbook_inventory(), url="https://trademan.in.th/SignIn")

    holdings = await _run_scrape(page)

    assert holdings == []
    assert trademan_driver.portfolio_scrape_authenticated is False
    page.goto.assert_not_awaited()
    page.evaluate.assert_not_awaited()              # never scrapes a SignIn page


@pytest.mark.asyncio
async def test_scrape_portfolio_returns_empty_when_account_switch_fails():
    page = _mock_portfolio_page(_runbook_inventory())

    holdings = await _run_scrape(page, switch_result={"success": False, "error": "ACCOUNT_SWITCH_FAILED"})

    assert holdings == []
    assert trademan_driver.portfolio_scrape_authenticated is False
    page.evaluate.assert_not_awaited()              # wrong/unconfirmed account -> no rows


@pytest.mark.asyncio
async def test_scrape_portfolio_returns_empty_and_not_live_without_holdings_table():
    page = _mock_portfolio_page(_runbook_inventory()[1:2])   # watchlist only

    holdings = await _run_scrape(page)

    assert holdings == []
    assert trademan_driver.portfolio_scrape_authenticated is False


# ==========================================
# RCA-013: on-page summary row -> portfolio_totals
# ==========================================

def _totals_inventory(cost="200,000.00", market="220,000.00", unreal="20,000.00"):
    """``_runbook_inventory()`` with the summary-table cells overridden."""
    inv = _runbook_inventory()
    inv[-1]["rows"] = [["Total", "20,000", "20,000", "-", "-", cost, market, unreal,
                        "10.00%", "0"]]
    return inv


@pytest.mark.asyncio
async def test_scrape_portfolio_reads_totals_from_summary_table():
    margin_no = settings.TRADEMAN_ACCOUNT_NO_MARGIN
    page = _mock_portfolio_page(_runbook_inventory())

    holdings = await _run_scrape(page)

    assert len(holdings) == 15                      # summary row is still not a holding
    assert trademan_driver.portfolio_totals == {
        "amount": 200_000.0,
        "market_value": 220_000.0,
        "unrealized_pnl": 20_000.0,
        "account_no": margin_no,
    }


@pytest.mark.asyncio
async def test_scrape_portfolio_totals_none_when_summary_cells_blank():
    """An all-``-`` summary row yields None per field — never 0.00 (Anti-Mock)."""
    page = _mock_portfolio_page(_totals_inventory(cost="-", market="-", unreal="-"))

    await _run_scrape(page)

    assert trademan_driver.portfolio_totals == {
        "amount": None, "market_value": None, "unrealized_pnl": None,
        "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
    }


@pytest.mark.asyncio
async def test_scrape_portfolio_totals_none_without_summary_table():
    inventory = [t for t in _runbook_inventory() if "2rem" not in (t.get("cls") or "")]
    page = _mock_portfolio_page(inventory)

    await _run_scrape(page)

    assert trademan_driver.portfolio_totals == {
        "amount": None, "market_value": None, "unrealized_pnl": None,
        "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
    }


@pytest.mark.asyncio
async def test_scrape_portfolio_clears_stale_totals_on_unauthenticated_session():
    page = _mock_portfolio_page(_runbook_inventory(), url="https://trademan.in.th/SignIn")
    trademan_driver.portfolio_totals = {"amount": 1.0, "market_value": 1.0,
                                        "unrealized_pnl": 1.0, "account_no": "x"}

    await _run_scrape(page)

    assert trademan_driver.portfolio_totals is None
