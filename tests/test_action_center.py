import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.action_center_service import action_center_service, ActionCenterService
from app.browser.popup_manager import popup_manager
from app.browser.auth_driver import auth_driver
from app.services.line_service import line_service


@pytest.fixture(autouse=True)
def clean_action_center():
    action_center_service.reject_all()
    yield
    action_center_service.reject_all()


def test_action_center_queue_and_card_generation():
    """Tests adding items to Action Center, queue counting, and Flex Card formatting."""
    # 1. Initially empty
    assert action_center_service.get_pending_count() == 0
    empty_card = action_center_service.build_action_center_card()
    assert empty_card["type"] == "flex"
    assert "ไม่มีรายการรออนุมัติ" in str(empty_card)

    # 2. Add pending items
    act1 = action_center_service.add_pending_action({
        "symbol": "AOT",
        "action": "SELL",
        "volume": 600,
        "price": 61.25,
        "reason": "SL_HIT",
        "message": "AOT breached Stop Loss"
    })
    assert act1 == "ACT-AOT-SELL"
    assert action_center_service.get_pending_count() == 1

    act2 = action_center_service.add_pending_action({
        "symbol": "CPALL",
        "action": "BUY",
        "volume": 800,
        "price": 45.50,
        "reason": "TP_HIT",
        "message": "CPALL Take Profit"
    })
    assert act2 == "ACT-CPALL-BUY"
    assert action_center_service.get_pending_count() == 2

    # 3. Build Card with multiple items
    card = action_center_service.build_action_center_card()
    assert card["type"] == "flex"
    card_str = str(card)
    assert "AOT" in card_str
    assert "CPALL" in card_str
    assert "approve_all_actions" in card_str
    assert "reject_all_actions" in card_str

    # 4. Lunchtime reminder card
    lunch_card = action_center_service.build_lunchtime_reminder_card()
    assert lunch_card["type"] == "flex"
    assert "พักเที่ยง" in str(lunch_card)
    assert "2 รายการ" in str(lunch_card)

    # 5. Reject single item
    assert action_center_service.reject_single("ACT-AOT-SELL") is True
    assert action_center_service.get_pending_count() == 1
    assert action_center_service.reject_single("NON_EXISTENT") is False

    # 6. Reject all
    cleared = action_center_service.reject_all()
    assert cleared == 1
    assert action_center_service.get_pending_count() == 0


@pytest.mark.asyncio
async def test_action_center_approval_execution(db_session):
    """Tests approve_single and approve_all executing orders via TradeDispatcher."""
    action_center_service.add_pending_action({
        "symbol": "AOT",
        "action": "SELL",
        "volume": 600,
        "price": 61.25,
        "reason": "SL_HIT"
    })
    action_center_service.add_pending_action({
        "symbol": "CPALL",
        "action": "BUY",
        "volume": 800,
        "price": 45.50,
        "reason": "TP_HIT"
    })

    # Test approve single
    with patch("app.services.trade_dispatcher.trade_dispatcher.dispatch_order", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = {"success": True, "status": "MATCHED", "broker_order_no": "ORD-123"}
        res = await action_center_service.approve_single("ACT-AOT-SELL", db_session)
        assert res["success"] is True
        assert res["symbol"] == "AOT"
        assert action_center_service.get_pending_count() == 1

    # Test approve all remaining
    with patch("app.services.trade_dispatcher.trade_dispatcher.dispatch_order", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = {"success": True, "status": "MATCHED", "broker_order_no": "ORD-456"}
        results = await action_center_service.approve_all(db_session)
        assert len(results) == 1
        assert results[0]["symbol"] == "CPALL"
        assert action_center_service.get_pending_count() == 0


@pytest.mark.asyncio
async def test_line_webhook_action_center_interaction(db_session):
    """Tests that sending 'action' text returns the Action Center card, and postbacks trigger approvals."""
    action_center_service.add_pending_action({
        "symbol": "AOT",
        "action": "SELL",
        "volume": 600,
        "price": 61.25,
        "reason": "SL_HIT"
    })

    with patch.object(line_service, "_send_reply", new_callable=AsyncMock) as mock_reply:
        # 1. Text message "action"
        res = await line_service._handle_text_message(
            db=db_session,
            text="action",
            raw_event={"replyToken": "test_reply_token"}
        )
        assert res["status"] == "ACTION_CENTER_DISPLAYED"
        assert res["pending_count"] == 1
        mock_reply.assert_called_once()

        # 2. Postback "approve_action"
        mock_reply.reset_mock()
        with patch("app.services.trade_dispatcher.trade_dispatcher.dispatch_order", new_callable=AsyncMock) as mock_dispatch:
            mock_dispatch.return_value = {"success": True, "status": "MATCHED", "broker_order_no": "ORD-999"}
            pb_res = await line_service._handle_postback(
                db=db_session,
                data="action=approve_action&id=ACT-AOT-SELL",
                raw_event={"replyToken": "pb_token"}
            )
            assert pb_res["status"] == "ACTION_APPROVED"
            assert action_center_service.get_pending_count() == 0


@pytest.mark.asyncio
async def test_popup_manager_dont_show_again_checkbox():
    """Tests that PopupManager checks the 'Don't show again' checkbox when present."""
    mock_page = MagicMock()
    mock_checkbox = MagicMock()
    mock_checkbox.is_visible = AsyncMock(return_value=True)
    mock_checkbox.evaluate = AsyncMock(return_value="input")
    mock_checkbox.is_checked = AsyncMock(return_value=False)
    mock_checkbox.check = AsyncMock()

    mock_page.query_selector = AsyncMock(return_value=mock_checkbox)

    checked = await popup_manager._check_dont_show_again(mock_page)
    assert checked is True
    mock_checkbox.check.assert_called_once()


@pytest.mark.asyncio
async def test_auth_driver_session_reuse_active_tab():
    """Tests that auth_driver.verify_saved_session reuses an active TradeMan tab without navigating to SSO."""
    mock_page = MagicMock()
    mock_page.is_closed = MagicMock(return_value=False)
    mock_page.url = "https://trademan.in.th/Portfolio"
    mock_page.evaluate = AsyncMock(return_value="TradeMan - Portfolio")
    mock_page.goto = AsyncMock()
    mock_el = MagicMock()
    mock_el.is_visible = AsyncMock(return_value=True)
    mock_page.query_selector = AsyncMock(return_value=mock_el)

    auth_driver.page = mock_page
    auth_driver.status = "DISCONNECTED"

    try:
        reused = await auth_driver.verify_saved_session()
        assert reused is True
        assert auth_driver.status == "AUTHENTICATED"
        # Crucial: verify that goto was NOT called because active tab was reused!
        mock_page.goto.assert_not_called()
    finally:
        auth_driver.page = None
        auth_driver.status = "DISCONNECTED"
