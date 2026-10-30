import pytest
from app.services.line_cli import cards


def test_portfolio_multi_broker_card_carousel():
    kss_rows = [
        {"symbol": "PTT", "position_type": "SHORT", "volume": 100,
         "cost": 33.0, "last": 32.0, "pnl_pct": 3.03, "broker": "kss"}
    ]
    lib_rows = [
        {"symbol": "CPALL", "position_type": "LONG", "volume": 200,
         "cost": 60.0, "last": 65.0, "pnl_pct": 8.33, "broker": "lib"}
    ]
    borrowed = [
        {"symbol": "MTC", "volume": 1000, "broker": "kss"}
    ]
    brokers_data = [
        {"broker": "kss", "account": "MARGIN", "amount": 3300.0,
         "pnl_value": 100.0, "pnl_pct": 3.03, "rows": kss_rows, "borrowed": borrowed},
        {"broker": "lib", "account": "CASH", "amount": 12000.0,
         "pnl_value": 1000.0, "pnl_pct": 8.33, "rows": lib_rows, "borrowed": []},
    ]

    msg = cards.portfolio_multi_broker_card(brokers_data=brokers_data, snapshot_label="10:00")
    assert msg.get("type") == "flex"
    contents = msg.get("contents", {})
    assert contents.get("type") == "carousel"
    bubbles = contents.get("contents", [])
    assert len(bubbles) == 2
    assert "KSS" in str(bubbles[0]["header"])
    assert "LIB" in str(bubbles[1]["header"])

    kss_body_str = str(bubbles[0]["body"])
    assert "/cover kss PTT 100" in kss_body_str
    assert "/short kss MTC 1000" in kss_body_str
    assert "/return MTC all" in kss_body_str

    lib_body_str = str(bubbles[1]["body"])
    assert "/sell lib CPALL 200" in lib_body_str
