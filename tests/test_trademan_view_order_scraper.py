"""
Regression tests for the Krungsri TradeMan 'View Order' ledger scraper.

Guards KSS-RCA-014: the legacy scraper used a broad ``table tbody tr`` selector which
swallowed the Watchlist / fund tables and shifted columns, producing ``symbol=UNKNOWN``
and ``status=<time>``. The scrapers now anchor on the header table's ``<thead>`` labels
('Order No.' | 'Side' | 'Symbol' | ...) and map the verified 10-column layout, with the
TradeMan side codes (B/S/H/C) normalized via ``TRADEMAN_SIDE_CODE_MAP``.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.browser.trademan_driver import trademan_driver, TRADEMAN_SIDE_CODE_MAP


# Raw cells captured from the live TradeMan 'View Order' DOM (MARGIN 3024959, 2026-10-07):
# [Order No., Side, Symbol, Volume, Price, Matched, Status, Time, Quote, actions]
LIVE_ROWS = [
    ["11023608", "H", "TISCO", "300", "126", "0", "Canceled", "16:13:32", "Y", ""],
    ["11021964", "C", "BJC", "2,300", "18.80", "2,300", "Matched", "15:26:50", "Y", ""],
    ["11017582", "H", "GPSC", "1,000", "49.75", "1,000", "Matched", "11:59:50", "Y", ""],
    ["11017574", "H", "GPSC", "1,000", "50", "0", "Reject", "11:59:38", "B", ""],
]


def _make_page(evaluate_result):
    page = AsyncMock()
    page.is_closed = Mock(return_value=False)
    page.url = "https://trademan.in.th/Portfolio"
    page.evaluate = AsyncMock(return_value=evaluate_result)
    # switch_tab's subtab loop awaits wait_for_selector; return None so no element click
    # is attempted (the scrapers read the table via page.evaluate regardless).
    page.wait_for_selector = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock()
    return page


@pytest.mark.asyncio
async def test_scrape_all_orders_maps_columns_and_side_codes():
    page = _make_page({"ok": True, "rows": LIVE_ROWS})
    saved = getattr(trademan_driver, "page_override", None)
    trademan_driver.page_override = page
    try:
        with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new=AsyncMock()):
            orders = await trademan_driver.scrape_all_orders()
    finally:
        trademan_driver.page_override = saved

    assert len(orders) == 4
    first = orders[0]
    assert first["broker_order_no"] == "11023608"
    assert first["symbol"] == "TISCO"          # NOT "UNKNOWN"
    assert first["side"] == "SHORT"            # H -> SHORT
    assert first["volume"] == 300
    assert first["price"] == 126.0
    assert first["matched_volume"] == 0
    assert first["balance"] == 300
    assert first["status"] == "Canceled"       # status is a word, NOT the time
    assert first["time"] == "16:13:32"         # time has its own column now

    # Cover code + comma-formatted volume
    cover = orders[1]
    assert cover["side"] == "COVER"            # C -> COVER
    assert cover["volume"] == 2300
    assert cover["matched_volume"] == 2300
    assert cover["balance"] == 0
    assert cover["status"] == "Matched"

    # Rejected row keeps its raw status for Pillar 2 classification
    assert orders[3]["status"] == "Reject"
    assert orders[3]["side"] == "SHORT"


@pytest.mark.asyncio
async def test_scrape_unmatched_orders_excludes_terminal_rows():
    page = _make_page({"ok": True, "rows": LIVE_ROWS})
    saved = getattr(trademan_driver, "page_override", None)
    trademan_driver.page_override = page
    try:
        with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new=AsyncMock()):
            unmatched = await trademan_driver.scrape_unmatched_orders()
    finally:
        trademan_driver.page_override = saved

    # LIVE_ROWS has no open/partial non-terminal row -> nothing is "unmatched".
    assert unmatched == []


@pytest.mark.asyncio
async def test_scrape_unmatched_orders_includes_partial_and_open_only():
    rows = [
        ["1", "B", "PTT", "1,000", "34", "1,000", "Matched", "10:00:00", "Y", ""],
        ["2", "S", "AOT", "1,000", "60", "0", "Open", "10:01:00", "Y", ""],
        ["3", "B", "IVL", "1,000", "30", "400", "Partial", "10:02:00", "Y", ""],
        ["4", "H", "DELTA", "500", "100", "0", "Canceled", "10:03:00", "Y", ""],
    ]
    page = _make_page({"ok": True, "rows": rows})
    saved = getattr(trademan_driver, "page_override", None)
    trademan_driver.page_override = page
    try:
        with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new=AsyncMock()):
            unmatched = await trademan_driver.scrape_unmatched_orders()
    finally:
        trademan_driver.page_override = saved

    ids = [o["broker_order_no"] for o in unmatched]
    assert ids == ["2", "3"]  # Open + Partial; Matched-full and Canceled dropped


@pytest.mark.asyncio
async def test_scrape_all_orders_returns_empty_when_view_order_table_missing():
    page = _make_page({"ok": False, "reason": "no_view_order_header"})
    saved = getattr(trademan_driver, "page_override", None)
    trademan_driver.page_override = page
    try:
        with patch("app.browser.trademan_driver.popup_manager.dismiss_popups", new=AsyncMock()):
            orders = await trademan_driver.scrape_all_orders()
    finally:
        trademan_driver.page_override = saved
    assert orders == []


def test_side_code_map_is_canonical():
    assert TRADEMAN_SIDE_CODE_MAP == {"B": "BUY", "S": "SELL", "H": "SHORT", "C": "COVER"}
