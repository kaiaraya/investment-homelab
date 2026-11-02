"""
Integration and handler tests for SBL and Quick Trade in LINE CLI (Loop 2).
Uses Krungsri SBL Real Time driver and SQLite test session.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.line_cli.handlers import handle, handle_postback, _pre_trade_check
from app.services.line_cli.parser import parse
from app.db.models import SBLBorrowLot, Position


@pytest.mark.asyncio
async def test_handle_sbl_pool(db_session):
    parsed = parse("/sbl pool PTT")
    service = MagicMock()
    service._send_reply = AsyncMock()

    raw_event = {
        "replyToken": "reply_token_test",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.scrape_sbl_available_inventory", new_callable=AsyncMock) as mock_pool:
        mock_pool.return_value = 500000

        res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)

        assert res["status"] == "CLI_SBL_POOL"
        assert res["symbol"] == "PTT"
        assert res["available_qty"] == 500000
        service._send_reply.assert_called_once()


@pytest.mark.asyncio
async def test_handle_sbl_borrow_draft(db_session):
    parsed = parse("/borrow CPALL 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()

    raw_event = {
        "replyToken": "reply_token_test",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False):

        res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)

        assert res["status"] == "CLI_SBL_BORROW_DRAFTED"
        assert "draft_id" in res
        service._send_reply.assert_called_once()


@pytest.mark.asyncio
async def test_handle_sbl_borrow_confirm_postback(db_session):
    # Setup draft
    parsed = parse("/borrow CPALL 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()

    raw_event = {
        "replyToken": "reply_token_test",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False):
        draft_res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)
        draft_id = draft_res["draft_id"]

    # Now postback confirm
    postback_data = f"action=sbl_borrow_confirm&draft_id={draft_id}"
    raw_postback_event = {
        "replyToken": "reply_token_postback",
        "source": {"type": "user", "userId": "test_admin"},
        "postback": {"data": postback_data}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.execute_sbl_borrow", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"success": True, "status": "SBL_BORROW_DRY_RUN", "transaction_id": "TEST_TX_123"}

        pb_res = await handle_postback(postback_data, db=db_session, raw_event=raw_postback_event, service=service)

        assert pb_res["status"] == "SBL_BORROWED"
        assert pb_res["symbol"] == "CPALL"
        assert pb_res["volume"] == 1000
        service.push_message.assert_called_once()


@pytest.mark.asyncio
async def test_quick_trade_menu_postback(db_session):
    service = MagicMock()
    service._send_reply = AsyncMock()

    postback_data = "action=quick_trade_menu"
    raw_postback_event = {
        "replyToken": "reply_token_postback",
        "source": {"type": "user", "userId": "test_admin"},
        "postback": {"data": postback_data}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        pb_res = await handle_postback(postback_data, db=db_session, raw_event=raw_postback_event, service=service)

        assert pb_res["status"] == "QUICK_TRADE_MENU_DISPLAYED"
        service._send_reply.assert_called_once()


def test_quick_trade_selector_buttons_are_all_parseable():
    """Every selector button must send a command the parser actually accepts.

    Two of the four shipped a form the parser rejects (``/short PTT 1000`` /
    ``/cover PTT 1000`` — both need a price), so tapping them produced
    ``E_MISSING_ARG`` and no card. A message button sends instantly and cannot be
    edited, so the shipped text IS the command.
    """
    import json

    from app.services.line_cli.cards import quick_trade_selector_card
    from app.services.line_cli.parser import parse

    card = quick_trade_selector_card()
    texts = []

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "button":
                action = node.get("action") or {}
                if action.get("type") == "message":
                    texts.append(action["text"])
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(card)
    json.dumps(card)  # payload stays serialisable

    assert len(texts) == 4, texts
    for text in texts:
        parsed = parse(text)
        assert not isinstance(parsed, Exception), f"{text!r} does not parse: {parsed}"
        assert getattr(parsed, "cmd", None), f"{text!r} parsed to {parsed!r}"
    assert {p.cmd for p in (parse(t) for t in texts)} == {"buy", "sell", "short", "cover"}


@pytest.mark.asyncio
async def test_short_pre_trade_check_missing_sbl(db_session):
    # Pre-trade check for short without any SBL lots in DB on stock with no XD risk (fresh cache)
    order = parse("/short CPALL 1000 65.00")

    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "CPALL",
            "is_blocked": False,
            "verdict": "BORROW_ALLOWED",
        }
        chk = await _pre_trade_check(order, db_session)

        assert chk["ok"] is False
        assert chk["code"] == "E_NO_SBL"
        assert "ไม่มีหุ้นยืม SBL" in chk["message"]
        assert len(chk["quick_reply"]) > 0


@pytest.mark.asyncio
async def test_short_stale_cache_blocks_pre_trade_check_even_with_existing_lots(db_session):
    """
    2.11c: SBL cache stale must block /short with E_SBL_STALE_CACHE even when user has active DB lots.
    This prevents shorting into a missed XD/XR corporate action when cache is outdated.
    """
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="SBL-PTT-STALE",
        broker_tx_id="TX_PTT",
        symbol="PTT",
        borrow_qty=1000,
        remaining_qty=1000,
        borrow_price=34.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    order = parse("/short PTT 1000 34.00")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "PTT",
            "is_blocked": True,
            "verdict": "CACHE_STALE",
            "reason": "⚠️ ข้อมูลคลัง SBL เก่าเกิน 24 ชม.",
            "operator_hint": "พิมพ์ /sbl sync ก่อน",
        }
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_SBL_STALE_CACHE"
        assert "พิมพ์ /sbl sync ก่อน" in chk["message"]
        assert "/sbl sync" in chk["quick_reply"]


@pytest.mark.asyncio
async def test_short_cache_miss_blocks_pre_trade_check(db_session):
    """
    2.11c: SBL cache miss (empty) must block /short with E_SBL_STALE_CACHE.
    """
    order = parse("/short PTT 1000 34.00")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "PTT",
            "is_blocked": True,
            "verdict": "CACHE_MISS",
            "reason": "⚠️ ยังไม่มีข้อมูลคลังหุ้นยืม SBL",
            "operator_hint": "พิมพ์ /sbl sync ก่อน",
        }
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_SBL_STALE_CACHE"
        assert "พิมพ์ /sbl sync ก่อน" in chk["message"]


@pytest.mark.asyncio
async def test_short_fresh_cache_not_in_pool_passes_if_user_holds_db_lots(db_session):
    """
    2.11c: NOT_IN_POOL verdict (is_blocked: True) means unlisted in pool, but if user
    already holds confirmed SBL lots in DB on fresh cache (no XD/XR), /short must pass.
    """
    from datetime import date
    from app.db.models import BrokerAccount
    acc = BrokerAccount(
        account_no="3024959",
        broker="KRUNGSRI",
        account_type="MARGIN",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)

    lot = SBLBorrowLot(
        lot_id="SBL-UNLISTED-1",
        broker_tx_id="TX_UNLISTED",
        symbol="MOCK",
        borrow_qty=1000,
        remaining_qty=1000,
        borrow_price=20.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    order = parse("/short MOCK 1000 20.00")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "MOCK",
            "is_blocked": True,
            "verdict": "NOT_IN_POOL",
            "reason": "หุ้น MOCK ไม่ได้อยู่ในหมวด SET50/SET100/NEWSEC",
        }
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        assert chk["resolved_volume"] == 1000


@pytest.mark.asyncio
async def test_short_fresh_cache_not_in_pool_blocks_if_no_lots(db_session):
    """
    2.11c: NOT_IN_POOL with 0 DB lots returns E_NO_SBL.
    """
    order = parse("/short MOCK 1000 20.00")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "MOCK",
            "is_blocked": True,
            "verdict": "NOT_IN_POOL",
            "reason": "หุ้น MOCK ไม่ได้อยู่ในหมวด SET50/SET100/NEWSEC",
        }
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_NO_SBL"


@pytest.mark.asyncio
async def test_borrow_xd_hard_block(db_session):
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
    with patch.object(krungsri_sbl_driver, "check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "DELTA",
            "is_blocked": True,
            "verdict": "HARD_BLOCKED_XD_XR",
            "reason": "⛔ ห้ามเปิดสถานะขายชอร์ตเด็ดขาด ติด XD",
        }
        res = await krungsri_sbl_driver.execute_sbl_borrow("DELTA", 1000)
        assert res["success"] is False
        assert res["status"] == "BLOCKED_BY_XD_XR"
        assert "ติด XD" in res["error"]


@pytest.mark.asyncio
async def test_short_xd_hard_block(db_session):
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="SBL-DELTA-1",
        broker_tx_id="TX_DELTA",
        symbol="DELTA",
        borrow_qty=1000,
        remaining_qty=1000,
        borrow_price=70.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    order = parse("/short DELTA 1000 75.0")

    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "DELTA",
            "is_blocked": True,
            "verdict": "HARD_BLOCKED_XD_XR",
            "reason": "⛔ ห้ามเปิดสถานะชอร์ต: ติดเครื่องหมาย XD",
        }

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_SBL_XD_BLOCKED"
        assert "ติดเครื่องหมาย XD" in chk["message"]


@pytest.mark.asyncio
async def test_handle_sbl_status_and_command(db_session):
    parsed = parse("/sbl status")
    service = MagicMock()
    service._send_reply = AsyncMock()

    raw_event = {
        "replyToken": "reply_token_test",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)
        assert res["status"] == "CLI_SBL_STATUS"
        service._send_reply.assert_called_once()


@pytest.mark.asyncio
async def test_quicktrade_command(db_session):
    parsed = parse("/quicktrade")
    service = MagicMock()
    service._send_reply = AsyncMock()

    raw_event = {
        "replyToken": "reply_token_test",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)
        assert res["status"] == "QUICK_TRADE_MENU_DISPLAYED"
        service._send_reply.assert_called_once()


@pytest.mark.asyncio
async def test_sbl_return_draft_and_postback(db_session):
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="SBL-PTT-TEST-1",
        broker_tx_id="TX123",
        symbol="PTT",
        borrow_qty=1000,
        remaining_qty=1000,
        borrow_price=34.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {
        "replyToken": "tok_return",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        cmd = parse("/return PTT 500")
        draft_res = await handle(cmd, db=db_session, raw_event=raw_event, service=service)
        assert draft_res["status"] == "CLI_SBL_RETURN_DRAFTED"
        draft_id = draft_res["draft_id"]

        postback_data = f"action=sbl_return_confirm&draft_id={draft_id}"
        raw_pb = {
            "replyToken": "tok_return_pb",
            "source": {"type": "user", "userId": "test_admin"},
            "postback": {"data": postback_data}
        }
        with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.return_sbl_shares", new_callable=AsyncMock) as mock_ret:
            mock_ret.return_value = {"success": True, "status": "SBL_RETURN_DRY_RUN"}
            pb_res = await handle_postback(postback_data, db=db_session, raw_event=raw_pb, service=service)
            assert pb_res["status"] == "SBL_RETURNED"
            assert pb_res["volume"] == 500
            service.push_message.assert_called_once()

            await db_session.refresh(lot)
            assert lot.remaining_qty == 500


@pytest.mark.asyncio
async def test_borrow_command_xd_hard_block(db_session):
    """
    R3: /borrow command must reject immediately when symbol has XD/XR risk.
    """
    cmd = parse("/borrow DELTA 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()
    raw_event = {
        "replyToken": "tok_borrow_xd",
        "source": {"type": "user", "userId": "test_admin"}
    }

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False), \
         patch("app.services.sbl_intelligence_service.sbl_intelligence_service.check_xd_risk", new_callable=AsyncMock) as mock_xd:
        mock_xd.return_value = {
            "xd_risk": True,
            "xd_date": "10/10/2026",
            "type": "XD",
            "reason": "⛔ ห้ามยืมหุ้น DELTA ติดเครื่องหมาย XD"
        }

        res = await handle(cmd, db=db_session, raw_event=raw_event, service=service)
        assert res["status"] == "CLI_SBL_REJECTED"
        assert res["code"] == "E_SBL_XD_BLOCKED"
        service._send_reply.assert_called_once()
        args, _ = service._send_reply.call_args
        msg_obj = args[1] if len(args) > 1 else args[0]
        text_val = msg_obj.get("text", "") if isinstance(msg_obj, dict) else str(msg_obj)
        assert "ติดเครื่องหมาย XD" in text_val


@pytest.mark.asyncio
async def test_short_command_xd_hard_block_without_existing_lots(db_session):
    """
    R3: /short command must reject with XD hard-block FIRST even when user has 0 SBL lots.
    """
    order = parse("/short DELTA 1000 75.0")

    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk") as mock_risk:
        mock_risk.return_value = {
            "symbol": "DELTA",
            "is_blocked": True,
            "verdict": "HARD_BLOCKED_XD_XR",
            "reason": "⛔ ห้ามเปิดสถานะชอร์ต: ติดเครื่องหมาย XD",
        }

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_SBL_XD_BLOCKED"
        assert "ติดเครื่องหมาย XD" in chk["message"]


@pytest.mark.asyncio
async def test_line_service_webhook_postback_routes_sbl_borrow_confirm(client, db_session, monkeypatch):
    """
    R4 / Bug Fix: Verify line_service._handle_postback routes action=sbl_borrow_confirm correctly.
    """
    import time
    from app.services.line_service import line_service
    from app.services.line_cli.handlers import _store_draft

    draft_id = "DRAFT-SBL-TEST"
    draft = {
        "draft_id": draft_id,
        "type": "sbl_borrow",
        "symbol": "PTT",
        "volume": 500,
        "fee_rate": 3.50,
        "broker": "kss",
        "account": "margin",
        "created_at": time.time(),
    }
    _store_draft(draft)

    mock_push = AsyncMock(return_value=True)
    monkeypatch.setattr(line_service, "push_message", mock_push)

    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.execute_sbl_borrow", new_callable=AsyncMock) as mock_exec, \
         patch("app.services.sbl_intelligence_service.sbl_intelligence_service.check_xd_risk", new_callable=AsyncMock) as mock_xd:
        mock_xd.return_value = {"xd_risk": False}
        mock_exec.return_value = {"success": True, "status": "SBL_BORROW_DRY_RUN", "transaction_id": "TX_WEBHOOK_123"}

        payload = {
            "events": [
                {
                    "type": "postback",
                    "timestamp": 1718000000000,
                    "replyToken": "tok-pb-sbl",
                    "source": {"type": "user", "userId": "U_SBL_POSTBACK_USER"},
                    "postback": {"data": f"action=sbl_borrow_confirm&draft_id={draft_id}"},
                }
            ]
        }

        resp = await client.post("/api/v1/webhook/line", json=payload, headers={"X-Line-Signature": "mock_signature"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "SBL_BORROWED"
        assert data["results"][0]["symbol"] == "PTT"
        assert data["results"][0]["volume"] == 500
        mock_push.assert_called_once()


def test_sbl_driver_cache_invalidation():
    """
    Edge case: Verify driver cache invalidation resets in-memory cache.
    """
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
    krungsri_sbl_driver._cached_data = {"test": 123}
    assert krungsri_sbl_driver.get_cached_data() == {"test": 123}
    krungsri_sbl_driver.invalidate_cache()
    assert krungsri_sbl_driver._cached_data is None


@pytest.mark.asyncio
async def test_short_multi_lot_sbl_inventory_passes_check(db_session):
    """
    R3 Bug Fix: User holds 2 lots of 500 shares (total 1000).
    A short order of 1000 shares must pass pre-trade check (was previously blocked).
    """
    from datetime import date
    from app.db.models import BrokerAccount
    acc = BrokerAccount(
        account_no="3024959",
        broker="KRUNGSRI",
        account_type="MARGIN",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)

    lot1 = SBLBorrowLot(
        lot_id="SBL-MULTI-1",
        broker_tx_id="TX_M1",
        symbol="PTT",
        borrow_qty=500,
        remaining_qty=500,
        borrow_price=34.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    lot2 = SBLBorrowLot(
        lot_id="SBL-MULTI-2",
        broker_tx_id="TX_M2",
        symbol="PTT",
        borrow_qty=500,
        remaining_qty=500,
        borrow_price=34.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add_all([lot1, lot2])
    await db_session.commit()

    order = parse("/short PTT 1000 34.00")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk", return_value={"is_blocked": False}):
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        assert chk["resolved_volume"] == 1000


@pytest.mark.asyncio
async def test_sbl_multi_lot_fifo_return_deduction(db_session):
    """
    R3 Bug Fix: Returning 500 shares across Lot 1 (300) and Lot 2 (500)
    must deduct Lot 1 completely and deduct 200 from Lot 2 in FIFO order.
    """
    from datetime import date, timedelta
    lot1 = SBLBorrowLot(
        lot_id="SBL-FIFO-1",
        broker_tx_id="TX_F1",
        symbol="BBL",
        borrow_qty=300,
        remaining_qty=300,
        borrow_price=135.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today() - timedelta(days=2),
        status="ACTIVE"
    )
    lot2 = SBLBorrowLot(
        lot_id="SBL-FIFO-2",
        broker_tx_id="TX_F2",
        symbol="BBL",
        borrow_qty=500,
        remaining_qty=500,
        borrow_price=136.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today() - timedelta(days=1),
        status="ACTIVE"
    )
    db_session.add_all([lot1, lot2])
    await db_session.commit()

    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()

    raw_event = {"replyToken": "tok_ret_fifo", "source": {"type": "user", "userId": "U_TEST"}}
    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        cmd = parse("/return BBL 500")
        draft_res = await handle(cmd, db=db_session, raw_event=raw_event, service=service)
        assert draft_res["status"] == "CLI_SBL_RETURN_DRAFTED"
        draft_id = draft_res["draft_id"]

        pb_data = f"action=sbl_return_confirm&draft_id={draft_id}"
        with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.return_sbl_shares", new_callable=AsyncMock) as mock_ret:
            mock_ret.return_value = {"success": True, "status": "SBL_RETURN_DRY_RUN"}
            pb_res = await handle_postback(pb_data, db=db_session, raw_event={"replyToken": "tok_pb", "source": {"type": "user", "userId": "U_TEST"}, "postback": {"data": pb_data}}, service=service)
            assert pb_res["status"] == "SBL_RETURNED"
            assert pb_res["volume"] == 500

            await db_session.refresh(lot1)
            await db_session.refresh(lot2)
            assert lot1.remaining_qty == 0
            assert lot1.status == "FULLY_RETURNED"
            assert lot2.remaining_qty == 300
            assert lot2.status == "PARTIAL_RETURNED"


@pytest.mark.asyncio
async def test_sbl_return_postback_broker_failure_rolls_back(db_session):
    """
    R3 Bug Fix / Anti-Mock: If return_sbl_shares fails, DB lots must NOT be mutated.
    """
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="SBL-FAIL-1",
        broker_tx_id="TX_FAIL",
        symbol="SCB",
        borrow_qty=1000,
        remaining_qty=1000,
        borrow_price=105.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()

    raw_event = {"replyToken": "tok_ret_fail", "source": {"type": "user", "userId": "U_TEST"}}
    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        cmd = parse("/return SCB 500")
        draft_res = await handle(cmd, db=db_session, raw_event=raw_event, service=service)
        draft_id = draft_res["draft_id"]

        pb_data = f"action=sbl_return_confirm&draft_id={draft_id}"
        with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.return_sbl_shares", new_callable=AsyncMock) as mock_ret:
            mock_ret.return_value = {"success": False, "status": "NETWORK_ERROR", "error": "Connection to SBL Real Time failed"}
            pb_res = await handle_postback(pb_data, db=db_session, raw_event={"replyToken": "tok_pb", "source": {"type": "user", "userId": "U_TEST"}, "postback": {"data": pb_data}}, service=service)
            assert pb_res["status"] == "SBL_RETURN_FAILED"
            assert "Connection to SBL" in pb_res["error"]

            await db_session.refresh(lot)
            assert lot.remaining_qty == 1000
            assert lot.status == "ACTIVE"


@pytest.mark.asyncio
async def test_sbl_return_volume_exceeds_held_rejected(db_session):
    """
    R3 Bug Fix: Asking to return more shares than held in SBL is rejected cleanly.
    """
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="SBL-EXCEED-1",
        broker_tx_id="TX_EXCEED",
        symbol="KTB",
        borrow_qty=500,
        remaining_qty=500,
        borrow_price=18.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="ACTIVE"
    )
    db_session.add(lot)
    await db_session.commit()

    service = MagicMock()
    service._send_reply = AsyncMock()
    raw_event = {"replyToken": "tok_exceed", "source": {"type": "user", "userId": "U_TEST"}}
    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True):
        cmd = parse("/return KTB 1000")
        res = await handle(cmd, db=db_session, raw_event=raw_event, service=service)
        assert res["status"] == "CLI_SBL_INSUFFICIENT_LOT"
        assert res["held"] == 500
        assert res["requested"] == 1000
        service._send_reply.assert_called_once()
        args, _ = service._send_reply.call_args
        msg = args[1] if len(args) > 1 else args[0]
        text_val = msg.get("text", "") if isinstance(msg, dict) else str(msg)
        assert "แค่ 500 หุ้น" in text_val


@pytest.mark.asyncio
async def test_pre_trade_check_position_type_matching(db_session):
    """
    Bug Fix: /cover must not match a LONG position, and /sell must not match a SHORT position.
    """
    # Seed only LONG position
    pos_long = Position(
        account_no="3024959",
        symbol="PTTEP",
        position_type="LONG",
        volume=1000,
        avg_cost=150.0,
    )
    db_session.add(pos_long)
    await db_session.commit()

    with patch("app.services.line_cli.handlers._resolve_account_no", return_value="3024959"):
        order_cover = parse("/cover PTTEP 500 155.00")
        chk_cover = await _pre_trade_check(order_cover, db_session)
        assert chk_cover["ok"] is False
        assert chk_cover["code"] == "E_NO_POSITION"
        assert "SHORT" in chk_cover["message"]

        # /sell should pass with the LONG position
        order_sell = parse("/sell PTTEP 500 155.00")
        chk_sell = await _pre_trade_check(order_sell, db_session)
        assert chk_sell["ok"] is True


@pytest.mark.asyncio
async def test_short_and_cover_rejects_non_kss_margin_broker_isolation(db_session):
    """
    Broker Isolation Invariant: /short and /cover are strictly Krungsri MARGIN 3024959.
    Attempting to route to Liberator or cash account must be rejected with E_BAD_BROKER.
    """
    order_short_lib = parse("/short lib PTT 100 35.00")
    chk_s = await _pre_trade_check(order_short_lib, db_session)
    assert chk_s["ok"] is False
    assert chk_s["code"] == "E_BAD_BROKER"
    assert "Margin 3024959" in chk_s["message"]

    order_cover_lib = parse("/cover lib PTT 100 35.00")
    chk_c = await _pre_trade_check(order_cover_lib, db_session)
    assert chk_c["ok"] is False
    assert chk_c["code"] == "E_BAD_BROKER"
    assert "Margin 3024959" in chk_c["message"]


@pytest.mark.asyncio
async def test_sbl_status_and_short_includes_partial_returned_lots(db_session):
    """
    Lots with status PARTIAL_RETURNED and remaining_qty > 0 must be included
    in /sbl status and /short pre-trade check.
    """
    from datetime import date
    from app.db.models import BrokerAccount
    acc = BrokerAccount(
        account_no="3024959",
        broker="KRUNGSRI",
        account_type="MARGIN",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)

    lot = SBLBorrowLot(
        lot_id="SBL-PARTIAL-1",
        broker_tx_id="TX_P1",
        symbol="ADVANC",
        borrow_qty=1000,
        remaining_qty=400,
        borrow_price=200.0,
        borrow_fee_rate=3.5,
        borrow_date=date.today(),
        status="PARTIAL_RETURNED"
    )
    db_session.add(lot)
    await db_session.commit()

    # Pre-trade check for short 400 shares should pass using this PARTIAL_RETURNED lot
    order = parse("/short ADVANC 400 200.0")
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk", return_value={"is_blocked": False}):
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        assert chk["resolved_volume"] == 400

    # /sbl status should also include this lot
    cmd_status = parse("/sbl")
    service = MagicMock()
    service._send_reply = AsyncMock()
    res = await handle(cmd_status, db=db_session, raw_event={"replyToken": "tok_sbl"}, service=service)
    assert res["status"] == "CLI_SBL_STATUS"
    assert res["count"] == 1


@pytest.mark.asyncio
async def test_sbl_multi_lot_return_accrued_fee_fifo_calculation(db_session):
    """
    Returning 500 shares across Lot 1 (300 shares @ 10 days) and Lot 2 (500 shares @ 2 days)
    must calculate accrued interest using exact FIFO lot durations.
    """
    from datetime import date, timedelta
    lot1 = SBLBorrowLot(
        lot_id="SBL-FEE-1",
        broker_tx_id="TX_FEE1",
        symbol="CPALL",
        borrow_qty=300,
        remaining_qty=300,
        borrow_price=60.0,
        borrow_fee_rate=3.65,  # 3.65% per year -> 0.01% per day
        borrow_date=date.today() - timedelta(days=10),
        status="ACTIVE"
    )
    lot2 = SBLBorrowLot(
        lot_id="SBL-FEE-2",
        broker_tx_id="TX_FEE2",
        symbol="CPALL",
        borrow_qty=500,
        remaining_qty=500,
        borrow_price=60.0,
        borrow_fee_rate=3.65,
        borrow_date=date.today() - timedelta(days=2),
        status="ACTIVE"
    )
    db_session.add_all([lot1, lot2])
    await db_session.commit()

    service = MagicMock()
    service._send_reply = AsyncMock()
    cmd = parse("/return CPALL 500")
    res = await handle(cmd, db=db_session, raw_event={"replyToken": "tok_fee"}, service=service)
    assert res["status"] == "CLI_SBL_RETURN_DRAFTED"
    draft_id = res["draft_id"]

    from app.services.line_cli.handlers import _take_draft
    draft = _take_draft(draft_id)
    assert draft is not None
    assert draft["volume"] == 500
    # Expected fee:
    # Lot 1: 300 * 60.0 * 0.0365 / 365 * 10 days = 18.0 THB
    # Lot 2: 200 * 60.0 * 0.0365 / 365 * 2 days = 2.4 THB
    # Total = 20.4 THB
    assert abs(draft["accrued_fee"] - 20.4) < 1e-4


# --------------------------------------------------------------------------- #
# 2.2 — a DRY-RUN borrow must not persist an ACTIVE lot (no phantom inventory)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_dry_run_borrow_does_not_persist_active_lot(db_session, monkeypatch):
    from sqlalchemy import select
    from app.core.config import settings

    monkeypatch.setattr(settings, "DRY_RUN_MODE", True, raising=False)

    parsed = parse("/borrow CPALL 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()

    raw_event = {"replyToken": "tok", "source": {"type": "user", "userId": "test_admin"}}
    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False):
        drafted = await handle(parsed, db=db_session, raw_event=raw_event, service=service)

    postback_data = f"action=sbl_borrow_confirm&draft_id={drafted['draft_id']}"
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.execute_sbl_borrow",
               new_callable=AsyncMock) as mock_exec, \
         patch("app.services.sbl_intelligence_service.sbl_intelligence_service.check_xd_risk",
               new_callable=AsyncMock, return_value={"xd_risk": False}):
        mock_exec.return_value = {"success": True, "status": "SBL_BORROW_DRY_RUN",
                                  "transaction_id": "DRY-1"}
        res = await handle_postback(postback_data, db=db_session, raw_event=raw_event, service=service)

    assert res["status"] == "SBL_BORROWED"
    assert res["persisted"] is False
    rows = (await db_session.execute(select(SBLBorrowLot))).scalars().all()
    assert rows == [], "dry-run borrow must not create an ACTIVE SBL lot"


@pytest.mark.asyncio
async def test_live_borrow_persists_active_lot(db_session, monkeypatch):
    from sqlalchemy import select
    from app.core.config import settings

    monkeypatch.setattr(settings, "DRY_RUN_MODE", False, raising=False)

    parsed = parse("/borrow CPALL 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {"replyToken": "tok", "source": {"type": "user", "userId": "test_admin"}}

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False):
        drafted = await handle(parsed, db=db_session, raw_event=raw_event, service=service)

    postback_data = f"action=sbl_borrow_confirm&draft_id={drafted['draft_id']}"
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.execute_sbl_borrow",
               new_callable=AsyncMock) as mock_exec, \
         patch("app.services.sbl_intelligence_service.sbl_intelligence_service.check_xd_risk",
               new_callable=AsyncMock, return_value={"xd_risk": False}):
        mock_exec.return_value = {"success": True, "status": "SUBMITTED", "transaction_id": "B123"}
        res = await handle_postback(postback_data, db=db_session, raw_event=raw_event, service=service)

    assert res["persisted"] is True
    rows = (await db_session.execute(select(SBLBorrowLot))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "ACTIVE"


# --------------------------------------------------------------------------- #
# 2.4 — postback routing: cancel paths reach the CLI handlers
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sbl_borrow_cancel_postback(db_session):
    parsed = parse("/borrow CPALL 1000")
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {"replyToken": "tok", "source": {"type": "user", "userId": "test_admin"}}

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.services.kill_switch_service.kill_switch_service.is_active", return_value=False):
        drafted = await handle(parsed, db=db_session, raw_event=raw_event, service=service)

    res = await handle_postback(f"action=sbl_borrow_cancel&draft_id={drafted['draft_id']}",
                                db=db_session, raw_event=raw_event, service=service)
    assert res["status"] == "SBL_BORROW_CANCELLED"
    service.push_message.assert_called_once()


@pytest.mark.asyncio
async def test_quick_trade_menu_postback_uses_reply(db_session):
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {"replyToken": "tok", "source": {"type": "user", "userId": "test_admin"}}

    res = await handle_postback("action=quick_trade_menu", db=db_session,
                                raw_event=raw_event, service=service)
    assert res["status"] == "QUICK_TRADE_MENU_DISPLAYED"
    service._send_reply.assert_called_once()
    service.push_message.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_postback_returns_none(db_session):
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {"replyToken": "tok", "source": {"type": "user", "userId": "test_admin"}}

    res = await handle_postback("action=approve_all_actions", db=db_session,
                                raw_event=raw_event, service=service)
    assert res is None          # falls through to line_service's own handlers


def test_sbl_pool_card_renders_stale_cache_message():
    """
    2.11c: sbl_pool_card renders 'ยังไม่มีข้อมูล — /sbl sync ก่อน' when snapshot is missing/stale.
    """
    from app.services.line_cli import cards
    card = cards.sbl_pool_card("DELTA", available_qty=0, status_message="ข้อมูลคลัง SBL เก่าเกิน 24 ชม.")
    alt_text = card.get("altText", "")
    assert "ยังไม่มีข้อมูล — /sbl sync ก่อน" in alt_text
    quick = card.get("quickReply", {}).get("items", [])
    quick_texts = [item.get("action", {}).get("text", "") for item in quick]
    assert "/sbl sync" in quick_texts


@pytest.mark.asyncio
async def test_sbl_borrow_confirm_blocked_by_stale_cache(db_session):
    """
    2.11c: SBL borrow confirm postback returns E_SBL_STALE_CACHE when driver rejects stale cache.
    """
    from app.services.line_cli.handlers import _store_draft
    import time
    draft_id = "DRAFT-STALE-BORROW"
    _store_draft({
        "draft_id": draft_id,
        "type": "sbl_borrow",
        "symbol": "DELTA",
        "volume": 500,
        "fee_rate": 3.5,
        "created_at": time.time(),
    })
    service = MagicMock()
    service._send_reply = AsyncMock()
    service.push_message = AsyncMock()
    raw_event = {"replyToken": "tok_pb", "source": {"type": "user", "userId": "test_admin"}}

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.execute_sbl_borrow", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {
            "success": False,
            "status": "BLOCKED_BY_STALE_CACHE",
            "error": "ข้อมูลคลัง SBL ยังไม่สด — พิมพ์ /sbl sync ก่อนยืมหุ้น",
        }
        res = await handle_postback(f"action=sbl_borrow_confirm&draft_id={draft_id}", db=db_session,
                                    raw_event=raw_event, service=service)
        assert res["status"] == "SBL_BORROW_FAILED"
        assert res["code"] == "E_SBL_STALE_CACHE"
        assert "ข้อมูลคลัง SBL ยังไม่สด" in res["error"]


@pytest.mark.asyncio
async def test_handle_sbl_pool_with_stale_cache_renders_hint(db_session):
    """
    2.11c: /sbl pool <sym> on stale cache passes status_message to sbl_pool_card without raising.
    """
    parsed = parse("/sbl pool DELTA")
    service = MagicMock()
    service._send_reply = AsyncMock()
    raw_event = {"replyToken": "tok_pool", "source": {"type": "user", "userId": "test_admin"}}

    with patch("app.services.conversation_state.conversation_state.is_authorized", return_value=True), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.scrape_sbl_available_inventory", new_callable=AsyncMock, return_value=0), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.cache_status", return_value={"state": "CACHE_STALE", "message": "ข้อมูลคลัง SBL เก่าเกิน 24 ชม."}):
        res = await handle(parsed, db=db_session, raw_event=raw_event, service=service)
        assert res["status"] == "CLI_SBL_POOL"
        assert res["symbol"] == "DELTA"
        assert res["available_qty"] == 0
        service._send_reply.assert_called_once()
        reply_card = service._send_reply.call_args[0][1]
        assert "ยังไม่มีข้อมูล — /sbl sync ก่อน" in reply_card.get("altText", "")



# ── `all` volume resolve must never crash and never over-commit ────────────────


def _ledger_patch(rows):
    return patch(
        "app.services.broker_cdp.sync_service.scrape_orders_from_cdp",
        new_callable=AsyncMock,
        return_value={"orders": rows},
    )


@pytest.mark.asyncio
async def test_short_all_subtracts_volume_already_committed(db_session):
    """`/short PTT all` = borrowed remaining − what is already on a SHORT order."""
    from datetime import date
    from app.db.models import BrokerAccount

    db_session.add(BrokerAccount(
        account_no="3024959", broker="KRUNGSRI", account_type="MARGIN",
        line_available=500000.0, cash_balance=500000.0,
    ))
    db_session.add(SBLBorrowLot(
        lot_id="SBL-ALL-1", broker_tx_id="TX_ALL_1", symbol="PTT",
        borrow_qty=1000, remaining_qty=1000, borrow_price=34.0,
        borrow_fee_rate=3.5, borrow_date=date.today(), status="ACTIVE",
    ))
    await db_session.commit()

    order = parse("/short PTT all 34.00")
    ledger = [{
        "symbol": "PTT", "side": "Short", "volume": 400,
        "matched_volume": 0, "status": "Queuing(O)",
    }]
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk",
               return_value={"is_blocked": False}), _ledger_patch(ledger):
        chk = await _pre_trade_check(order, db_session)

    assert chk["ok"] is True, chk
    assert chk["resolved_volume"] == 600


@pytest.mark.asyncio
async def test_short_all_rejects_when_borrowed_shares_fully_committed(db_session):
    """Second `/short all` must not double-short the same borrowed lot."""
    from datetime import date
    from app.db.models import BrokerAccount

    db_session.add(BrokerAccount(
        account_no="3024959", broker="KRUNGSRI", account_type="MARGIN",
        line_available=500000.0, cash_balance=500000.0,
    ))
    db_session.add(SBLBorrowLot(
        lot_id="SBL-ALL-2", broker_tx_id="TX_ALL_2", symbol="PTT",
        borrow_qty=1000, remaining_qty=1000, borrow_price=34.0,
        borrow_fee_rate=3.5, borrow_date=date.today(), status="ACTIVE",
    ))
    await db_session.commit()

    order = parse("/short PTT all 34.00")
    ledger = [{
        "symbol": "PTT", "side": "Short", "volume": 1000,
        "matched_volume": 0, "status": "Queuing(O)",
    }]
    with patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk",
               return_value={"is_blocked": False}), _ledger_patch(ledger):
        chk = await _pre_trade_check(order, db_session)

    assert chk["ok"] is False
    assert chk["code"] == "E_NO_UNSHORTED_SHARES"


@pytest.mark.asyncio
async def test_cover_all_reads_live_ledger_when_positions_table_is_stale(db_session):
    """No Position row at all, but the broker ledger shows a filled short → allow."""
    from app.db.models import BrokerAccount

    db_session.add(BrokerAccount(
        account_no="3024959", broker="KRUNGSRI", account_type="MARGIN",
        line_available=500000.0, cash_balance=500000.0,
    ))
    await db_session.commit()

    order = parse("/cover TIDLOR all 16.20")
    ledger = [{
        "symbol": "TIDLOR", "side": "Short", "volume": 3000,
        "matched_volume": 3000, "status": "Matched(M)",
    }]
    with _ledger_patch(ledger):
        chk = await _pre_trade_check(order, db_session)

    assert chk["ok"] is True, chk
    assert chk["resolved_volume"] == 3000


@pytest.mark.asyncio
async def test_cover_all_rejects_when_ledger_has_no_short(db_session):
    from app.db.models import BrokerAccount

    db_session.add(BrokerAccount(
        account_no="3024959", broker="KRUNGSRI", account_type="MARGIN",
        line_available=500000.0, cash_balance=500000.0,
    ))
    await db_session.commit()

    order = parse("/cover BCPG all 6.70")
    with _ledger_patch([]), patch(
        "app.services.broker_cdp.sync_service.scrape_portfolio_from_cdp",
        new_callable=AsyncMock,
        return_value={"holdings": []},
    ):
        chk = await _pre_trade_check(order, db_session)

    assert chk["ok"] is False
    assert chk["code"] == "E_NO_SHORT_POSITION"
