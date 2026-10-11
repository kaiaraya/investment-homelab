import pytest
from unittest.mock import AsyncMock
from app.browser.popup_manager import popup_manager


@pytest.mark.asyncio
async def test_is_overlay_present():
    mock_page = AsyncMock()
    mock_page.is_closed.return_value = False
    mock_el = AsyncMock()
    mock_el.is_visible.return_value = True
    mock_page.query_selector.return_value = mock_el

    assert await popup_manager.is_overlay_present(mock_page) is True

    # No overlay
    mock_page.query_selector.return_value = None
    assert await popup_manager.is_overlay_present(mock_page) is False


@pytest.mark.asyncio
async def test_dismiss_via_fast_rules_success():
    mock_page = AsyncMock()
    mock_btn = AsyncMock()
    mock_btn.is_visible.return_value = True

    mock_page.query_selector.side_effect = lambda sel: mock_btn if "ปิด" in sel else None

    res = await popup_manager._dismiss_via_fast_rules(mock_page)
    assert res is True
    mock_btn.click.assert_awaited_once()




@pytest.mark.asyncio
async def test_reconnect_if_connection_lost_clicks_reconnect():
    """'Connection Lost' dialog -> Tier 0 clicks 'Reconnect' (no Gemini needed)."""
    mock_page = AsyncMock()
    mock_page.is_closed.return_value = False
    mock_btn = AsyncMock()
    mock_btn.is_visible.return_value = True
    mock_page.query_selector.side_effect = lambda sel: mock_btn if "Reconnect" in sel else None

    res = await popup_manager._reconnect_if_connection_lost(mock_page)

    assert res is True
    mock_btn.click.assert_awaited_once()
    mock_page.wait_for_timeout.assert_awaited()


@pytest.mark.asyncio
async def test_reconnect_if_connection_lost_no_dialog_is_noop():
    """No 'Connection Lost' dialog -> returns False and performs no action."""
    mock_page = AsyncMock()
    mock_page.is_closed.return_value = False
    mock_page.query_selector.return_value = None

    res = await popup_manager._reconnect_if_connection_lost(mock_page)

    assert res is False
    mock_page.wait_for_timeout.assert_not_awaited()
