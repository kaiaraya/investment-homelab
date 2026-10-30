"""
Unit tests for value-based trade orders (Loop 2).

Covers:
- Value parsing with suffixes: 'k', 'm', 'b', '฿', 'baht', 'บาท'
- Optional price for value-based orders
- Broker and account resolution
- Error handling for invalid amounts
"""

import pytest
from app.services.line_cli import parser as p


def test_value_order_basic_k_suffix():
    o = p.parse("/buy PTT 50k")
    assert isinstance(o, p.TradeOrder)
    assert o.cmd == "buy"
    assert o.symbol == "PTT"
    assert o.amount_mode == "value"
    assert o.target_value == 50000.0
    assert o.volume == 0
    assert o.price is None
    assert o.broker == "lib"
    assert o.account == "cash"


def test_value_order_with_explicit_price():
    o = p.parse("/buy PTT 50k 34.50")
    assert isinstance(o, p.TradeOrder)
    assert o.amount_mode == "value"
    assert o.target_value == 50000.0
    assert o.price == 34.50


def test_value_order_m_suffix():
    o = p.parse("/cover ADVANC 1.2m")
    assert isinstance(o, p.TradeOrder)
    assert o.cmd == "cover"
    assert o.symbol == "ADVANC"
    assert o.amount_mode == "value"
    assert o.target_value == 1200000.0
    assert o.broker == "kss"
    assert o.account == "margin"


def test_value_order_b_suffix():
    o = p.parse("/short KBANK 100000b")
    assert isinstance(o, p.TradeOrder)
    assert o.cmd == "short"
    assert o.symbol == "KBANK"
    assert o.amount_mode == "value"
    assert o.target_value == 100000.0
    assert o.broker == "kss"
    assert o.account == "margin"


def test_value_order_baht_and_thai_symbol():
    o = p.parse("/buy CPALL 30000฿")
    assert isinstance(o, p.TradeOrder)
    assert o.target_value == 30000.0

    o2 = p.parse("/buy CPALL 30,000บาท")
    assert isinstance(o2, p.TradeOrder)
    assert o2.target_value == 30000.0


def test_value_order_with_override():
    o = p.parse("/buy kss:margin PTT 50k 35.0")
    assert isinstance(o, p.TradeOrder)
    assert o.broker == "kss"
    assert o.account == "margin"
    assert o.target_value == 50000.0
    assert o.price == 35.0


def test_value_order_with_override_no_price():
    o = p.parse("/buy lib:cash PTT 50k")
    assert isinstance(o, p.TradeOrder)
    assert o.broker == "lib"
    assert o.account == "cash"
    assert o.target_value == 50000.0
    assert o.price is None


def test_invalid_value_amounts():
    err1 = p.parse("/buy PTT 0k")
    assert isinstance(err1, p.CliError)
    assert err1.code == p.E_BAD_VOLUME

    err2 = p.parse("/buy PTT -50k")
    assert isinstance(err2, p.CliError)
    assert err2.code == p.E_BAD_VOLUME

    err3 = p.parse("/buy PTT 50xyz")
    assert isinstance(err3, p.CliError)
    assert err3.code == p.E_BAD_VOLUME


def test_value_order_leading_currency_symbol():
    o = p.parse("/buy PTT ฿30000")
    assert isinstance(o, p.TradeOrder)
    assert o.target_value == 30000.0


@pytest.mark.asyncio
async def test_value_order_board_lot_resolution(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import BrokerAccount

    acc = BrokerAccount(
        account_no="1234567",
        broker="LIBERATOR",
        account_type="CASH",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)
    await db_session.commit()

    order = p.parse("/buy PTT 50k")

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="1234567"):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.25, "offer_1": 34.50, "last": 34.00}

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # 50,000 / 34.25 = 1,459.85 -> 1,400 shares (passive lure at bid_1)
        assert chk["resolved_volume"] == 1400
        assert chk["resolved_price"] == 34.25


@pytest.mark.asyncio
async def test_value_order_insufficient_budget(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check

    order = p.parse("/buy PTT 1k")

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="1234567"):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.25, "offer_1": 34.50, "last": 34.00}

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_INSUFFICIENT_BUDGET"
        assert "ไม่พอซื้อขั้นต่ำ 100 หุ้น" in chk["message"]
        assert "34.25" in chk["message"]


@pytest.mark.asyncio
async def test_value_order_sell_uses_best_bid(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import Position

    pos = Position(
        account_no="1234567",
        symbol="PTT",
        position_type="LONG",
        volume=2000,
        avg_cost=30.0,
    )
    db_session.add(pos)
    await db_session.commit()

    order = p.parse("/sell PTT 50k")

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="1234567"):
        # Best Bid is 34.00, Best Offer is 34.50
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.00, "offer_1": 34.50, "last": 34.25}

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # Under lure pricing, sell queues at best offer (34.50), never crosses spread
        # 50,000 / 34.50 = 1,449.27 -> 1,400 shares
        assert chk["resolved_volume"] == 1400
        assert chk["resolved_price"] == 34.50


def test_value_order_combined_prefix_suffix():
    o1 = p.parse("/buy PTT ฿50k")
    assert isinstance(o1, p.TradeOrder)
    assert o1.target_value == 50000.0

    o2 = p.parse("/short KBANK b100k")
    assert isinstance(o2, p.TradeOrder)
    assert o2.target_value == 100000.0


@pytest.mark.asyncio
async def test_value_order_float_precision_exact_boundary(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import BrokerAccount

    acc = BrokerAccount(
        account_no="1234567",
        broker="LIBERATOR",
        account_type="CASH",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)
    await db_session.commit()

    # 1760.0 / 17.60 in Python float = 99.99999999999999 -> without epsilon rounds to 0
    order = p.parse("/buy PTT 1760b 17.60")

    with patch("app.services.line_cli.handlers._resolve_account_no", return_value="1234567"):
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        assert chk["resolved_volume"] == 100
        assert chk["resolved_price"] == 17.60


@pytest.mark.asyncio
async def test_value_order_sell_insufficient_budget_action_word(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import Position

    pos = Position(
        account_no="1234567",
        symbol="PTT",
        position_type="LONG",
        volume=2000,
        avg_cost=30.0,
    )
    db_session.add(pos)
    await db_session.commit()

    order = p.parse("/sell PTT 1k")

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="1234567"):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.00, "offer_1": 34.50, "last": 34.25}

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is False
        assert chk["code"] == "E_INSUFFICIENT_BUDGET"
        assert "ไม่พอขายขั้นต่ำ 100 หุ้น" in chk["message"]


def test_value_order_detached_currency_units():
    o1 = p.parse("/buy PTT 50,000 บาท 35.00")
    assert isinstance(o1, p.TradeOrder)
    assert o1.amount_mode == "value"
    assert o1.target_value == 50000.0
    assert o1.price == 35.00

    o2 = p.parse("/buy PTT 500 baht")
    assert isinstance(o2, p.TradeOrder)
    assert o2.amount_mode == "value"
    assert o2.target_value == 500.0
    assert o2.price is None

    o3 = p.parse("/short kss:margin PTT 50k บาท 34.00")
    assert isinstance(o3, p.TradeOrder)
    assert o3.amount_mode == "value"
    assert o3.target_value == 50000.0
    assert o3.price == 34.00


@pytest.mark.asyncio
async def test_broker_quote_js_snippet_first_priority():
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _broker_quote

    js_quote = {
        "symbol": "BCPG",
        "success": True,
        "status": "OK",
        "source": "streaming_js",
        "bid_1": 6.75,
        "offer_1": 6.80,
        "last": 6.80,
        "prior_close": 6.75,
        "ceiling": 8.75,
        "floor": 4.74,
        "board_lot": 100,
        "flag": None,
    }

    with patch("scripts.broker_cdp.js_runner.get_quote_js", new_callable=AsyncMock) as mock_js, \
         patch("app.browser.trademan_driver.trademan_driver.get_market_bid_offer", new_callable=AsyncMock) as mock_tm:
        mock_js.return_value = js_quote
        res = await _broker_quote("kss", "BCPG")
        assert res["success"] is True
        assert res["source"] == "streaming_js"
        assert res["bid_1"] == 6.75
        assert res["offer_1"] == 6.80
        mock_js.assert_awaited_once_with(broker="kss", symbol="BCPG", timeout_s=5.0)
        mock_tm.assert_not_called()


@pytest.mark.asyncio
async def test_broker_quote_fails_closed_when_cdp_unavailable():
    """KSS quotes must fail closed without TradeMan fallback (100% CDP :9333 alignment)."""
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _broker_quote

    with patch("scripts.broker_cdp.js_runner.get_quote_js", new_callable=AsyncMock) as mock_js:
        mock_js.return_value = {"success": False, "source": "unavailable"}
        res = await _broker_quote("kss", "BCPG")
        assert res["success"] is False
        assert res["status"] == "QUOTE_UNAVAILABLE"
        assert "Streaming CDP :9333" in res["error"]


@pytest.mark.asyncio
async def test_broker_quote_liberator_fallback():
    """Liberator quotes fallback to liberator_plugin when JS is unavailable."""
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _broker_quote

    with patch("scripts.broker_cdp.js_runner.get_quote_js", new_callable=AsyncMock) as mock_js, \
         patch("app.brokers.liberator_plugin.get_market_bid_offer", new_callable=AsyncMock) as mock_lib:
        mock_js.return_value = {"success": False, "source": "unavailable"}
        mock_lib.return_value = {
            "symbol": "BCPG",
            "success": True,
            "bid_1": 6.75,
            "offer_1": 6.80,
            "last": 6.75,
        }
        res = await _broker_quote("lib", "BCPG")
        assert res["success"] is True
        assert res["bid_1"] == 6.75
        mock_lib.assert_awaited_once_with("BCPG")


@pytest.mark.asyncio
async def test_value_order_bcpg_50k_sizing_via_js_quote(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import BrokerAccount

    acc = BrokerAccount(
        account_no="3024959",
        broker="KRUNGSRI",
        account_type="MARGIN",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)
    await db_session.commit()

    order = p.parse("/buy kss:margin BCPG 50k")
    assert isinstance(order, p.TradeOrder)

    js_quote = {
        "symbol": "BCPG",
        "success": True,
        "status": "OK",
        "source": "streaming_js",
        "bid_1": 6.75,
        "offer_1": 6.80,
        "last": 6.75,
        "prior_close": 6.75,
        "ceiling": 8.75,
        "floor": 4.74,
        "board_lot": 100,
        "flag": None,
    }

    with patch("scripts.broker_cdp.js_runner.get_quote_js", new_callable=AsyncMock) as mock_js, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="3024959"):
        mock_js.return_value = js_quote

        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # 50,000 / 6.75 = 7,407.41 -> 7,400 shares @ 6.75 (floor to board lot 100, lure at bid_1)
        assert chk["resolved_volume"] == 7400
        assert chk["resolved_price"] == 6.75


@pytest.mark.asyncio
async def test_value_order_short_lure_price_and_uptick(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import BrokerAccount, SBLBorrowLot

    acc = BrokerAccount(
        account_no="3024959",
        broker="KRUNGSRI",
        account_type="MARGIN",
        line_available=500000.0,
        cash_balance=500000.0,
    )
    db_session.add(acc)
    from datetime import date
    lot = SBLBorrowLot(
        lot_id="LOT-PTT-1",
        symbol="PTT",
        borrow_qty=10000,
        remaining_qty=10000,
        borrow_date=date.today(),
        status="ACTIVE",
    )
    db_session.add(lot)
    await db_session.commit()

    order = p.parse("/short kss:margin PTT 50k")
    assert isinstance(order, p.TradeOrder)

    # Case 1: offer_1 (34.50) > last (34.25) -> uses offer_1
    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="3024959"), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk", return_value={"is_blocked": False, "verdict": "OK"}):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.00, "offer_1": 34.50, "last": 34.25}
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # 50,000 / 34.50 = 1,449.27 -> 1,400 shares
        assert chk["resolved_volume"] == 1400
        assert chk["resolved_price"] == 34.50

    # Case 2: offer_1 (34.00) <= last (34.00) -> uptick rule steps up to 34.25
    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="3024959"), \
         patch("app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk", return_value={"is_blocked": False, "verdict": "OK"}):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 33.75, "offer_1": 34.00, "last": 34.00}
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # 50,000 / 34.25 = 1,459.85 -> 1,400 shares
        assert chk["resolved_volume"] == 1400
        assert chk["resolved_price"] == 34.25


@pytest.mark.asyncio
async def test_value_order_cover_uses_lure_bid(db_session):
    from unittest.mock import patch, AsyncMock
    from app.services.line_cli.handlers import _pre_trade_check
    from app.db.models import Position

    pos = Position(
        account_no="3024959",
        symbol="PTT",
        position_type="SHORT",
        volume=2000,
        avg_cost=35.0,
    )
    db_session.add(pos)
    await db_session.commit()

    order = p.parse("/cover kss:margin PTT 50k")
    assert isinstance(order, p.TradeOrder)

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q, \
         patch("app.services.line_cli.handlers._resolve_account_no", return_value="3024959"):
        mock_q.return_value = {"symbol": "PTT", "bid_1": 34.25, "offer_1": 34.50, "last": 34.00}
        chk = await _pre_trade_check(order, db_session)
        assert chk["ok"] is True
        # Cover passive lure joins bid_1 (34.25)
        # 50,000 / 34.25 = 1,459.85 -> 1,400 shares
        assert chk["resolved_volume"] == 1400
        assert chk["resolved_price"] == 34.25


def test_parse_size_command():
    cmd = p.parse("/size PTT")
    assert isinstance(cmd, p.SizeCommand)
    assert cmd.cmd == "size"
    assert cmd.symbol == "PTT"

    calc_cmd = p.parse("/calc bcpg")
    assert isinstance(calc_cmd, p.SizeCommand)
    assert calc_cmd.symbol == "BCPG"

    thai_cmd = p.parse("/คำนวณ advanc")
    assert isinstance(thai_cmd, p.SizeCommand)
    assert thai_cmd.symbol == "ADVANC"

    err_missing = p.parse("/size")
    assert isinstance(err_missing, p.CliError)
    assert err_missing.code == p.E_MISSING_ARG

    err_bad = p.parse("/size 12345")
    assert isinstance(err_bad, p.CliError)
    assert err_bad.code == p.E_BAD_SYMBOL


@pytest.mark.asyncio
async def test_handle_size_command(db_session):
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.services.line_cli import handlers

    cmd = p.parse("/size PTT")
    assert isinstance(cmd, p.SizeCommand)

    service = MagicMock()
    service._send_reply = AsyncMock()

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = {"success": True, "offer_1": 34.50, "last": 34.25, "bid_1": 34.00}
        res = await handlers.handle(cmd, db=db_session, raw_event={"replyToken": "tok1", "source": {"userId": "u1"}}, service=service)
        assert res["status"] == "CLI_SIZE_CALCULATED"
        assert res["symbol"] == "PTT"
        assert res["price"] == 34.50
        assert len(res["tiers"]) == 3
        # 50k: floor(50,000 / 34.50 / 100) * 100 = 1400
        assert res["tiers"][0]["shares"] == 1400
        assert res["tiers"][0]["actual_cost"] == 1400 * 34.50
        # 75k: floor(75,000 / 34.50 / 100) * 100 = 2100
        assert res["tiers"][1]["shares"] == 2100
        assert res["tiers"][1]["actual_cost"] == 2100 * 34.50
        # 100k: floor(100,000 / 34.50 / 100) * 100 = 2800
        assert res["tiers"][2]["shares"] == 2800
        assert res["tiers"][2]["actual_cost"] == 2800 * 34.50

        service._send_reply.assert_awaited_once()
        sent_card = service._send_reply.await_args[0][1]
        assert sent_card["type"] == "flex"
        assert "คำนวณขนาดซื้อ PTT" in sent_card["altText"]
        assert len(sent_card["quickReply"]["items"]) == 3


@pytest.mark.asyncio
async def test_handle_size_command_quote_unavailable(db_session):
    from unittest.mock import patch, AsyncMock, MagicMock
    from app.services.line_cli import handlers

    cmd = p.parse("/size PTT")
    service = MagicMock()
    service._send_reply = AsyncMock()

    with patch("app.services.line_cli.handlers._broker_quote", new_callable=AsyncMock) as mock_q:
        mock_q.return_value = {"success": False}
        res = await handlers.handle(cmd, db=db_session, raw_event={"replyToken": "tok1", "source": {"userId": "u1"}}, service=service)
        assert res["status"] == "CLI_QUOTE_UNAVAILABLE"
        service._send_reply.assert_awaited_once()
