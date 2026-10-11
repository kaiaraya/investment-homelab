"""
Unit tests for Centralized BrowserTabManager.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.browser.tab_manager import BrowserTabManager


@pytest.fixture
def tab_manager():
    return BrowserTabManager()


def test_register_and_get_tab(tab_manager):
    mock_page = MagicMock()
    mock_page.is_closed.return_value = False
    mock_page.url = "https://trademan.in.th/Portfolio"

    tab_manager.register_tab("trademan", mock_page)
    retrieved = tab_manager.get_tab("trademan")

    assert retrieved == mock_page
    assert "trademan" in tab_manager.list_active_tabs()


def test_closed_tab_cleanup(tab_manager):
    mock_page = MagicMock()
    mock_page.is_closed.return_value = True
    mock_page.url = "https://trademan.in.th/Portfolio"

    tab_manager.register_tab("trademan", mock_page)
    # get_tab should detect closed and clean it up
    retrieved = tab_manager.get_tab("trademan")

    assert retrieved is None
    assert "trademan" not in tab_manager.list_active_tabs()


def test_classify_page(tab_manager):
    p1 = MagicMock()
    p1.is_closed.return_value = False
    p1.url = "https://www.krungsrisecurities.com/th/main/default.aspx"
    assert tab_manager._classify_page(p1) == "krungsri_portal"

    p2 = MagicMock()
    p2.is_closed.return_value = False
    p2.url = "https://trademan.in.th/Portfolio"
    assert tab_manager._classify_page(p2) == "trademan"

    p3 = MagicMock()
    p3.is_closed.return_value = False
    p3.url = "https://www.krungsrisecurities.com/th/discliaimer-sbl/Default.aspx?start=sbl"
    assert tab_manager._classify_page(p3) == "sbl"


@pytest.mark.asyncio
async def test_ping_keepalive(tab_manager):
    p1 = MagicMock()
    p1.is_closed.return_value = False
    p1.evaluate = AsyncMock(return_value="TradeMan Portfolio")

    p2 = MagicMock()
    p2.is_closed.return_value = False
    p2.evaluate = AsyncMock(return_value="Krungsri Securities")

    tab_manager.register_tab("trademan", p1)
    tab_manager.register_tab("krungsri_portal", p2)

    results = await tab_manager.ping_keepalive()

    assert results.get("trademan") is True
    assert results.get("krungsri_portal") is True
    assert p1.evaluate.called
    assert p2.evaluate.called
