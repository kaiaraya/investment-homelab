import pytest
from datetime import date
from unittest.mock import AsyncMock
from app.db.models import BrokerAccount, Position, SBLBorrowLot
from app.services.line_cli import cards, handlers, parser


def test_port_row_long_generates_sell_button():
    row = {
        "symbol": "PTT",
        "volume": 100,
        "cost": 33.0,
        "last": 34.0,
        "pnl_pct": 3.03,
        "position_type": "LONG",
        "broker": "lib",
    }
    box = cards._port_row(row, actionable=True)
    box_str = str(box)
    assert "LIB" in box_str
    assert "/sell lib PTT 100" in box_str
    assert "ขาย (ต่อราคา)" in box_str


def test_port_row_short_generates_cover_button():
    row = {
        "symbol": "TISCO",
        "volume": 500,
        "cost": 98.0,
        "last": 97.0,
        "pnl_pct": 1.02,
        "position_type": "SHORT",
        "broker": "kss",
    }
    box = cards._port_row(row, actionable=True)
    box_str = str(box)
    assert "KSS" in box_str
    assert "/cover kss TISCO 500" in box_str
    assert "Cover (ต่อราคา)" in box_str


def test_borrowed_row_generates_short_and_return_buttons():
    borrowed = {"symbol": "PTT", "volume": 100, "broker": "kss"}
    box = cards._borrowed_row(borrowed)
    box_str = str(box)
    assert "KSS" in box_str
    assert "/short kss PTT 100" in box_str
    assert "/return PTT all" in box_str


def test_portfolio_action_buttons_parse_valid_trade_orders():
    from app.services.line_cli import parser
    # Verify all button command strings generated in portfolio views parse cleanly
    cmds = [
        "/sell lib PTT 100",
        "/cover kss TISCO 500",
        "/short kss PTT 100",
        "/return PTT all",
    ]
    for c in cmds:
        res = parser.parse(c)
        assert not isinstance(res, parser.CliError), f"Failed to parse {c}: {res}"
        if c != "/return PTT all":
            assert isinstance(res, parser.TradeOrder)
            assert res.price is None
            assert res.volume in (100, 500)


def test_port_row_unresolved_broker_actionable_false_has_no_buttons():
    row = {
        "symbol": "ORPH",
        "volume": 50,
        "cost": 10.0,
        "last": 11.0,
        "pnl_pct": 10.0,
        "position_type": "LONG",
        "broker": "",
    }
    box = cards._port_row(row, actionable=False)
    box_str = str(box)
    assert "/sell" not in box_str
    assert "/cover" not in box_str
    assert "/short" not in box_str


def test_portfolio_multi_broker_card_unresolved_section_has_no_action_buttons():
    brokers_data = [
        {
            "broker": "kss",
            "account": "DB snapshot · MARGIN",
            "amount": 50000.0,
            "pnl_value": 1000.0,
            "pnl_pct": 2.0,
            "rows": [{"symbol": "TISCO", "volume": 500, "cost": 98.0, "last": 96.0, "pnl_pct": 1.0, "position_type": "SHORT", "broker": "kss"}],
            "borrowed": [],
        },
        {
            "broker": "unresolved",
            "account": "DB snapshot · ไม่ระบุโบรกเกอร์",
            "amount": 500.0,
            "pnl_value": 50.0,
            "pnl_pct": 10.0,
            "rows": [{"symbol": "ORPH", "volume": 50, "cost": 10.0, "last": 11.0, "pnl_pct": 10.0, "position_type": "LONG", "broker": ""}],
            "borrowed": [],
            "actionable": False,
        },
    ]
    card = cards.portfolio_multi_broker_card(brokers_data=brokers_data)
    card_str = str(card)
    assert "/cover kss TISCO 500" in card_str
    assert "/sell" not in card_str  # ORPH long has actionable=False so no /sell


class FakeService:
    def __init__(self):
        self.sent = []

    async def _send_reply(self, token, payload):
        self.sent.append(payload)

    async def push_message(self, message, to_user_id=None):
        self.sent.append(message)
        return True


def _extract_button_commands(payload: dict) -> list[str]:
    cmds = []

    def walk(node):
        if isinstance(node, dict):
            action = node.get("action")
            if isinstance(action, dict) and action.get("type") == "message" and action.get("text"):
                cmds.append(action["text"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return cmds


@pytest.fixture
def fake_portfolio_env(monkeypatch):
    """Deterministic mocks for account resolution, passive quotes, SBL risk, and CDP sync."""
    def fake_resolve_account(broker, account):
        b = (broker or "").lower()
        a = (account or "cash").lower()
        if b == "lib" and a == "cash":
            return "LIB001"
        if b == "kss" and a == "margin":
            return "KSS001"
        return None

    monkeypatch.setattr(handlers, "_resolve_account_no", fake_resolve_account)

    async def fake_quote(broker, symbol):
        return {"success": True, "bid_1": 64.75, "offer_1": 65.25, "last": 65.0, "source": "stub"}

    monkeypatch.setattr(handlers, "_broker_quote", fake_quote)
    monkeypatch.setattr(handlers, "_broker_sync_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.brokers.krungsri.sbl_realtime_driver.krungsri_sbl_driver.check_symbol_risk",
        lambda sym: {"is_blocked": False, "verdict": "BORROW_ALLOWED"},
    )


@pytest.mark.asyncio
async def test_roundtrip_long_sell_button_to_draft(fake_portfolio_env, db_session):
    # Seed LONG position for Liberator
    db_session.add_all([
        BrokerAccount(account_no="LIB001", broker="lib", account_type="CASH_BALANCE", line_available=1_000_000.0),
        Position(symbol="CPALL", account_no="LIB001", position_type="LONG", volume=200, avg_cost=60.0, current_price=65.0),
    ])
    await db_session.commit()

    # Render portfolio card
    card = cards.port_card(
        broker="lib",
        account="Cash Balance",
        amount=13000.0,
        pnl_value=1000.0,
        pnl_pct=8.33,
        snapshot_label="15:00:00",
        stale=False,
        live=True,
        rows=[{
            "symbol": "CPALL",
            "volume": 200,
            "cost": 60.0,
            "last": 65.0,
            "pnl_pct": 8.33,
            "position_type": "LONG",
            "broker": "lib",
        }],
        borrowed=[],
        actionable=True,
    )
    cmds = _extract_button_commands(card)
    sell_cmd = next(c for c in cmds if c.startswith("/sell"))
    assert sell_cmd == "/sell lib CPALL 200"

    parsed = parser.parse(sell_cmd)
    assert isinstance(parsed, parser.TradeOrder)

    svc = FakeService()
    res = await handlers._handle_trade_order(parsed, svc, "tok", None, db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert len(svc.sent) == 1
    assert "action=trade_draft_confirm" in str(svc.sent[-1])


@pytest.mark.asyncio
async def test_roundtrip_short_cover_button_to_draft(fake_portfolio_env, db_session):
    # Seed SHORT position for Krungsri Margin
    db_session.add_all([
        BrokerAccount(account_no="KSS001", broker="kss", account_type="CREDIT_BALANCE", line_available=1_000_000.0),
        Position(symbol="TISCO", account_no="KSS001", position_type="SHORT", volume=500, avg_cost=98.0, current_price=96.0),
    ])
    await db_session.commit()

    # Render portfolio card
    card = cards.port_card(
        broker="kss",
        account="Margin",
        amount=48000.0,
        pnl_value=1000.0,
        pnl_pct=2.04,
        snapshot_label="15:00:00",
        stale=False,
        live=True,
        rows=[{
            "symbol": "TISCO",
            "volume": 500,
            "cost": 98.0,
            "last": 96.0,
            "pnl_pct": 2.04,
            "position_type": "SHORT",
            "broker": "kss",
        }],
        borrowed=[],
        actionable=True,
    )
    cmds = _extract_button_commands(card)
    cover_cmd = next(c for c in cmds if c.startswith("/cover"))
    assert cover_cmd == "/cover kss TISCO 500"

    parsed = parser.parse(cover_cmd)
    assert isinstance(parsed, parser.TradeOrder)

    svc = FakeService()
    res = await handlers._handle_trade_order(parsed, svc, "tok", None, db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert len(svc.sent) == 1
    assert "action=trade_draft_confirm" in str(svc.sent[-1])


@pytest.mark.asyncio
async def test_roundtrip_borrowed_short_button_to_draft(fake_portfolio_env, db_session):
    # Seed active SBL borrow lot
    db_session.add_all([
        BrokerAccount(account_no="KSS001", broker="kss", account_type="CREDIT_BALANCE", line_available=1_000_000.0),
        SBLBorrowLot(
            lot_id="LOT_PTT_001",
            symbol="PTT",
            borrow_qty=100,
            remaining_qty=100,
            borrow_price=33.0,
            borrow_fee_rate=3.5,
            borrow_date=date(2026, 10, 1),
            status="ACTIVE",
        ),
    ])
    await db_session.commit()

    # Render borrowed row in portfolio card
    card = cards.port_card(
        broker="kss",
        account="Margin",
        amount=0.0,
        pnl_value=0.0,
        pnl_pct=0.0,
        snapshot_label="15:00:00",
        stale=False,
        live=True,
        rows=[],
        borrowed=[{"symbol": "PTT", "volume": 100, "broker": "kss"}],
        actionable=True,
    )
    cmds = _extract_button_commands(card)
    short_cmd = next(c for c in cmds if c.startswith("/short"))
    assert short_cmd == "/short kss PTT 100"

    parsed = parser.parse(short_cmd)
    assert isinstance(parsed, parser.TradeOrder)

    svc = FakeService()
    res = await handlers._handle_trade_order(parsed, svc, "tok", None, db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert len(svc.sent) == 1
    assert "action=trade_draft_confirm" in str(svc.sent[-1])


@pytest.mark.asyncio
async def test_roundtrip_borrowed_return_button_to_draft(fake_portfolio_env, db_session):
    # Seed active SBL borrow lot
    db_session.add_all([
        BrokerAccount(account_no="KSS001", broker="kss", account_type="CREDIT_BALANCE", line_available=1_000_000.0),
        SBLBorrowLot(
            lot_id="LOT_PTT_002",
            symbol="PTT",
            borrow_qty=500,
            remaining_qty=500,
            borrow_price=33.0,
            borrow_fee_rate=3.5,
            borrow_date=date(2026, 10, 1),
            status="ACTIVE",
        ),
    ])
    await db_session.commit()

    # Render borrowed row in portfolio card
    card = cards.port_card(
        broker="kss",
        account="Margin",
        amount=0.0,
        pnl_value=0.0,
        pnl_pct=0.0,
        snapshot_label="15:00:00",
        stale=False,
        live=True,
        rows=[],
        borrowed=[{"symbol": "PTT", "volume": 500, "broker": "kss"}],
        actionable=True,
    )
    cmds = _extract_button_commands(card)
    return_cmd = next(c for c in cmds if c.startswith("/return"))
    assert return_cmd == "/return PTT all"

    parsed = parser.parse(return_cmd)
    assert isinstance(parsed, parser.SblReturnOrder)

    svc = FakeService()
    res = await handlers._handle_sbl_return(parsed, svc, "tok", None, db_session)
    assert res["status"] == "CLI_SBL_RETURN_DRAFTED"
    assert len(svc.sent) == 1
    assert "action=sbl_return_confirm" in str(svc.sent[-1])


@pytest.mark.asyncio
async def test_roundtrip_no_quote_fails_closed_e_no_quote(fake_portfolio_env, db_session, monkeypatch):
    db_session.add_all([
        BrokerAccount(account_no="LIB001", broker="lib", account_type="CASH_BALANCE", line_available=1_000_000.0),
        Position(symbol="CPALL", account_no="LIB001", position_type="LONG", volume=200, avg_cost=60.0, current_price=65.0),
    ])
    await db_session.commit()

    async def no_quote(broker, symbol):
        return {"success": False, "source": "unavailable"}

    monkeypatch.setattr(handlers, "_broker_quote", no_quote)

    order = parser.parse("/sell lib CPALL 200")
    assert isinstance(order, parser.TradeOrder)
    assert order.price is None

    svc = FakeService()
    res = await handlers._handle_trade_order(order, svc, "tok", None, db_session)
    assert res["status"] == "CLI_TRADE_REJECTED"
    assert res["code"] == "E_NO_QUOTE"


@pytest.mark.asyncio
async def test_roundtrip_multi_broker_card_buttons_reach_draft(fake_portfolio_env, db_session):
    db_session.add_all([
        BrokerAccount(account_no="LIB001", broker="lib", account_type="CASH_BALANCE", line_available=1_000_000.0),
        BrokerAccount(account_no="KSS001", broker="kss", account_type="CREDIT_BALANCE", line_available=1_000_000.0),
        Position(symbol="CPALL", account_no="LIB001", position_type="LONG", volume=200, avg_cost=60.0, current_price=65.0),
        Position(symbol="TISCO", account_no="KSS001", position_type="SHORT", volume=500, avg_cost=98.0, current_price=96.0),
        SBLBorrowLot(
            lot_id="LOT_PTT_MULTI",
            symbol="PTT",
            borrow_qty=300,
            remaining_qty=300,
            borrow_price=33.0,
            borrow_fee_rate=3.5,
            borrow_date=date(2026, 10, 1),
            status="ACTIVE",
        ),
    ])
    await db_session.commit()

    brokers_data = [
        {
            "broker": "lib",
            "account": "Cash Balance",
            "amount": 13000.0,
            "pnl_value": 1000.0,
            "pnl_pct": 8.33,
            "rows": [{"symbol": "CPALL", "volume": 200, "cost": 60.0, "last": 65.0, "pnl_pct": 8.33, "position_type": "LONG", "broker": "lib"}],
            "borrowed": [],
            "actionable": True,
        },
        {
            "broker": "kss",
            "account": "Margin",
            "amount": 48000.0,
            "pnl_value": 1000.0,
            "pnl_pct": 2.04,
            "rows": [{"symbol": "TISCO", "volume": 500, "cost": 98.0, "last": 96.0, "pnl_pct": 2.04, "position_type": "SHORT", "broker": "kss"}],
            "borrowed": [{"symbol": "PTT", "volume": 300, "broker": "kss"}],
            "actionable": True,
        },
    ]
    card = cards.portfolio_multi_broker_card(brokers_data=brokers_data)
    cmds = _extract_button_commands(card)
    assert "/sell lib CPALL 200" in cmds
    assert "/cover kss TISCO 500" in cmds
    assert "/short kss PTT 300" in cmds
    assert "/return PTT all" in cmds

    for cmd in cmds:
        parsed = parser.parse(cmd)
        svc = FakeService()
        if isinstance(parsed, parser.TradeOrder):
            res = await handlers._handle_trade_order(parsed, svc, "tok", None, db_session)
            assert res["status"] == "CLI_TRADE_DRAFTED"
            assert "action=trade_draft_confirm" in str(svc.sent[-1])
        elif isinstance(parsed, parser.SblReturnOrder):
            res = await handlers._handle_sbl_return(parsed, svc, "tok", None, db_session)
            assert res["status"] == "CLI_SBL_RETURN_DRAFTED"
            assert "action=sbl_return_confirm" in str(svc.sent[-1])

