"""Per-stock ``/port all sync`` card layout + summary (Loop 1)."""

from app.services.line_cli import cards


def _brokers_data():
    """KSS (LONG + SHORT + borrowed) then LIB (LONG)."""
    return [
        {"broker": "kss", "account": "MARGIN", "actionable": True,
         "amount": 500000.0, "pnl_value": 10000.0, "pnl_pct": 2.0,
         "rows": [
             {"symbol": "PTT", "position_type": "LONG", "volume": 1000,
              "cost": 30.0, "last": 31.0, "pnl_pct": 3.33, "broker": "kss"},
             {"symbol": "TISCO", "position_type": "SHORT", "volume": 500,
              "cost": 90.0, "last": 88.0, "pnl_pct": 2.27, "broker": "kss"},
         ],
         "borrowed": [{"symbol": "BCPG", "volume": 200, "broker": "kss"}]},
        {"broker": "lib", "account": "CASH", "actionable": True,
         "amount": 200000.0, "pnl_value": -4000.0, "pnl_pct": -2.0,
         "rows": [
             {"symbol": "CPALL", "position_type": "LONG", "volume": 300,
              "cost": 55.0, "last": 54.0, "pnl_pct": -1.82, "broker": "lib"},
         ],
         "borrowed": []},
    ]


def _unwrap(msg):
    c = msg["contents"]
    return c["contents"] if c.get("type") == "carousel" else [c]


def _all_bubbles(msgs):
    out = []
    for m in msgs:
        out += _unwrap(m)
    return out


def _title(bubble):
    return bubble["header"]["contents"][0]["contents"][0]["text"]


def _buttons(bubble):
    return [b["action"]["text"] for b in bubble.get("footer", {}).get("contents", [])]


def _all_text(node):
    out = []
    if isinstance(node, dict):
        if "text" in node:
            out.append(str(node["text"]))
        for v in node.values():
            if isinstance(v, (dict, list)):
                out += _all_text(v)
    elif isinstance(node, list):
        for v in node:
            out += _all_text(v)
    return out


def test_one_bubble_per_position_kss_block_then_lib():
    msgs = cards.portfolio_stock_cards(brokers_data=_brokers_data())
    assert len(msgs) == 1          # 4 bubbles < 12 → carousel เดียว
    bubbles = _all_bubbles(msgs)
    assert len(bubbles) == 4
    assert [_title(b) for b in bubbles] == [
        "📊 [KSS] PTT", "📊 [KSS] TISCO (S)", "📊 [KSS] BCPG (B)", "📊 [LIB] CPALL",
    ]  # KSS block ก่อน แล้ว LIB — แยกกลุ่ม


def test_buttons_by_position_type():
    bubbles = _all_bubbles(cards.portfolio_stock_cards(brokers_data=_brokers_data()))
    by = {_title(b): b for b in bubbles}
    assert _buttons(by["📊 [KSS] PTT"]) == []               # KSS LONG → ไม่มีปุ่ม (decision 2026-11-03)
    assert _buttons(by["📊 [KSS] TISCO (S)"]) == ["/cover kss TISCO 500"]
    assert _buttons(by["📊 [KSS] BCPG (B)"]) == ["/short kss BCPG 200", "/return BCPG all"]
    assert _buttons(by["📊 [LIB] CPALL"]) == ["/sell lib CPALL 300"]


def test_summary_card_keeps_per_broker_totals():
    summary = cards.portfolio_summary_card(brokers_data=_brokers_data())
    assert summary is not None
    body = " ".join(_all_text(summary))
    assert "[KSS] Amount" in body and "500,000.00" in body
    assert "[KSS] P/L" in body and "+10,000.00" in body
    assert "[LIB] Amount" in body and "200,000.00" in body
    assert "[LIB] P/L" in body and "-4,000.00" in body


def test_paginates_into_multiple_carousels():
    rows = [{"symbol": f"S{i}", "position_type": "LONG", "volume": 100,
             "cost": 10.0, "last": 11.0, "pnl_pct": 10.0, "broker": "lib"}
            for i in range(13)]
    data = [{"broker": "lib", "account": "CASH", "actionable": True,
             "rows": rows, "borrowed": []}]
    msgs = cards.portfolio_stock_cards(brokers_data=data, per_carousel=5)
    assert len(msgs) == 3
    assert len(_unwrap(msgs[0])) == 5
    assert len(_unwrap(msgs[2])) == 3


def test_empty_or_non_actionable_returns_empty():
    assert cards.portfolio_stock_cards(brokers_data=[]) == []
    assert cards.portfolio_stock_cards(brokers_data=None) == []
    data = [{"broker": "xxx", "account": "?", "actionable": True,
             "rows": [], "borrowed": []}]
    assert cards.portfolio_stock_cards(brokers_data=data) == []
    assert cards.portfolio_summary_card(brokers_data=data) is None


def test_borrowed_bubble_has_no_fabricated_cost():
    data = [{"broker": "kss", "account": "MARGIN", "actionable": True,
             "rows": [], "borrowed": [{"symbol": "BCPG", "volume": 200, "broker": "kss"}]}]
    bubble = _all_bubbles(cards.portfolio_stock_cards(brokers_data=data))[0]
    body_texts = " ".join(_all_text(bubble["body"]))
    assert "0.00" not in body_texts   # borrowed ไม่มี cost/last/pnl — ห้าม fabricate
    assert "หุ้นยืม" in body_texts
