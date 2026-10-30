import pytest
from app.services.line_cli import cards


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
