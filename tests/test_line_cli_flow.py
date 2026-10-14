"""
End-to-end tests for the LINE slash-command CLI (TASK-line-cli).

Drives the real handler entrypoint ``app.services.line_cli.handlers.handle`` with
a fake messaging service (captures replies/pushes) and mocked broker edges, so
every assertion is against real handler logic — not a stub. Broker calls are
mocked at the ``line_cli.handlers`` boundary (``_broker_*``), which is exactly
where Broker Isolation lives.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.services.line_cli import handlers
from app.services.line_cli import parser as cli_parser

#: The autouse `_broker_edges` fixture stubs ``handlers._live_card`` — keep a real
#: reference so the card-content tests below exercise the actual builder.
REAL_LIVE_CARD = handlers._live_card


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
class FakeService:
    """Captures what the handlers would send to LINE."""

    def __init__(self):
        self.replies = []
        self.pushes = []

    async def _send_reply(self, reply_token, message_or_text):
        self.replies.append(message_or_text)

    async def push_message(self, message_or_text, to_user_id=None):
        self.pushes.append((message_or_text, to_user_id))
        return True

    # convenience
    def last_text(self):
        return _text_of(self.replies[-1]) if self.replies else ""


def _text_of(msg):
    if isinstance(msg, str):
        return msg
    return msg.get("text") or msg.get("altText") or ""


def _event(*, user_id="U_OP", source_type="user", group_id=None, reply_token="tok-cli"):
    src = {"type": source_type}
    if user_id:
        src["userId"] = user_id
    if group_id:
        src["groupId"] = group_id
    return {"source": src, "replyToken": reply_token}


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture(autouse=True)
def _broker_edges(monkeypatch):
    """Default (happy, TEST-mode) broker edges — individual tests override as needed."""
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=True))
    monkeypatch.setattr(handlers, "_broker_open_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value={
        "symbol": "PTT", "bid_1": 34.25, "offer_1": 34.50, "last": 34.00, "source": "test",
    }))
    monkeypatch.setattr(handlers, "_broker_modify", AsyncMock(return_value={"success": True}))
    monkeypatch.setattr(handlers, "_broker_health", AsyncMock(return_value={
        "authenticated": True, "heartbeat": "10:41", "account": "MARGIN",
    }))
    monkeypatch.setattr(handlers, "_live_card", AsyncMock(return_value={"type": "flex", "altText": "live"}))
    monkeypatch.setattr(handlers, "_in_nego_window", lambda now=None: True)
    handlers._LOCKS.clear()
    handlers._STARTED.clear()


async def _run(service, text, *, db, **ev):
    parsed = cli_parser.parse(text)
    return await handlers.handle(parsed, db=db, raw_event=_event(**ev), service=service)


# --------------------------------------------------------------------------- #
# /help /status / authorization
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_help_lists_commands(service, db_session):
    res = await _run(service, "/help", db=db_session)
    assert res["status"] == "CLI_HELP"
    assert "คำสั่ง Homelab" in service.last_text()


@pytest.mark.asyncio
async def test_status_card_reflects_kill_and_relay(service, db_session, monkeypatch):
    from app.services.otp_relay_readiness import OtpRelayReadiness
    from app.services.kill_switch_service import kill_switch_service

    from app.services import otp_relay_readiness as relay_mod
    monkeypatch.setattr(kill_switch_service, "is_active", lambda: True)
    monkeypatch.setattr(relay_mod.otp_relay_readiness, "check",
                        AsyncMock(return_value=OtpRelayReadiness(ready=True, channel="line_group", reason="ok")))
    res = await _run(service, "/status", db=db_session)
    assert res["status"] == "CLI_STATUS"
    assert res["kill_active"] is True and res["relay_ready"] is True
    assert service.replies[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_unauthorized_sender_is_denied(service, db_session, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    res = await _run(service, "/status", db=db_session, source_type="room")
    assert res["status"] == "CLI_UNAUTHORIZED"
    assert "ไม่มีสิทธิ์" in service.last_text()


@pytest.mark.asyncio
async def test_unknown_command_returns_error_with_suggestion(service, db_session):
    res = await _run(service, "/prot", db=db_session)
    assert res["status"] == "CLI_ERROR" and res["code"] == cli_parser.E_UNKNOWN_CMD
    assert "port" in service.last_text()


# --------------------------------------------------------------------------- #
# /login /logout
# --------------------------------------------------------------------------- #
def _patch_relay(monkeypatch, ready=True, reason="ok", channel="line_group"):
    from app.services import otp_relay_readiness as relay_mod
    from app.services.otp_relay_readiness import OtpRelayReadiness
    monkeypatch.setattr(
        relay_mod.otp_relay_readiness, "check",
        AsyncMock(return_value=OtpRelayReadiness(ready=ready, channel=channel, reason=reason)),
    )


@pytest.mark.asyncio
async def test_login_never_fires_sms_when_relay_not_ready(service, db_session, monkeypatch):
    login = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("app.mcp.pillars.pillar1_session.session_login_broker", login)
    _patch_relay(monkeypatch, ready=False, reason="relay down")

    res = await _run(service, "/login kss", db=db_session)
    assert res["status"] == "CLI_RELAY_NOT_READY"
    login.assert_not_awaited()                       # Invariant 9
    assert "ยังไม่ส่ง SMS" in service.last_text()


@pytest.mark.asyncio
async def test_login_kss_acks_then_pushes_success(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    login = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("app.mcp.pillars.pillar1_session.session_login_broker", login)
    _patch_relay(monkeypatch, ready=True)

    res = await _run(service, "/login kss", db=db_session)
    assert res["status"] == "CLI_LOGIN" and res["results"][0]["status"] == "ok"
    assert "กำลังเข้าระบบ" in service.last_text()      # ack first (reply)
    assert any("สำเร็จ" in _text_of(m) for m, _ in service.pushes)
    login.assert_awaited_once()
    assert login.await_args.kwargs["platform"] == "TRADEMAN"


@pytest.mark.asyncio
async def test_login_skips_when_already_alive_without_force(service, db_session, monkeypatch):
    login = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("app.mcp.pillars.pillar1_session.session_login_broker", login)
    _patch_relay(monkeypatch, ready=True)

    res = await _run(service, "/login kss", db=db_session)   # fixture: session alive
    assert res["results"][0]["status"] == "already_alive"
    login.assert_not_awaited()
    assert any("เชื่อมต่ออยู่แล้ว" in _text_of(m) for m, _ in service.pushes)


@pytest.mark.asyncio
async def test_login_all_is_sequential_kss_then_lib(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    login = AsyncMock(return_value={"success": True})
    monkeypatch.setattr("app.mcp.pillars.pillar1_session.session_login_broker", login)
    _patch_relay(monkeypatch, ready=True)

    res = await _run(service, "/login all", db=db_session)
    assert [r["broker"] for r in res["results"]] == ["kss", "lib"]
    platforms = [c.kwargs["platform"] for c in login.await_args_list]
    assert platforms == ["TRADEMAN", "LIBERATOR"]


@pytest.mark.asyncio
async def test_login_pushes_error_when_broker_raises(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))

    def boom(*a, **k):
        raise NameError("name 'os' is not defined")

    monkeypatch.setattr("app.mcp.pillars.pillar1_session.session_login_broker", boom)
    _patch_relay(monkeypatch, ready=True)

    res = await _run(service, "/login lib", db=db_session)
    assert res["status"] == "CLI_LOGIN"
    assert res["results"][0]["status"] == "failed"
    assert any("เข้าระบบไม่สำเร็จ" in _text_of(m) and "NameError" in _text_of(m)
               for m, _ in service.pushes)


@pytest.mark.asyncio
async def test_logout_lib_closes_liberator(service, db_session, monkeypatch):
    from app.brokers import liberator_plugin
    close = AsyncMock()
    monkeypatch.setattr(liberator_plugin, "close", close)

    res = await _run(service, "/logout lib", db=db_session)
    assert res["status"] == "CLI_LOGOUT"
    close.assert_awaited_once()
    assert "ออกจากระบบ LIB" in service.last_text()


@pytest.mark.asyncio
async def test_logout_when_not_logged_in(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    res = await _run(service, "/logout kss", db=db_session)
    assert "ไม่ได้เข้าระบบอยู่แล้ว" in service.last_text()


# --------------------------------------------------------------------------- #
# /port /orders /cash
# --------------------------------------------------------------------------- #
async def _seed_position(db, symbol="PTT", volume=1000, avg_cost=13.20, current_price=13.50):
    from app.db.models import Position
    db.add(Position(symbol=symbol, position_type="LONG", volume=volume, avg_cost=avg_cost,
                    current_price=current_price, unrealized_pnl=(current_price - avg_cost) * volume))
    await db.commit()


async def _seed_order(db, order_id="ORD-1", symbol="PTT", side="BUY", volume=1000, price=34.0, status="OPEN"):
    from app.db.models import Order
    db.add(Order(order_id=order_id, symbol=symbol, side=side, volume=volume, price=price,
                 status=status, source="test_seed"))
    await db.commit()


@pytest.mark.asyncio
async def test_port_default_reads_db_snapshot(service, db_session):
    await _seed_position(db_session, "PTT", volume=1000, avg_cost=13.20, current_price=13.50)
    res = await _run(service, "/port kss", db=db_session)
    assert res["status"] == "CLI_PORT" and res["count"] == 1
    assert service.replies[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_port_without_snapshot_is_honest(service, db_session):
    res = await _run(service, "/port kss", db=db_session)
    assert res["status"] == "CLI_NO_DATA"
    assert "ยังไม่มี snapshot" in service.last_text()


@pytest.mark.asyncio
async def test_port_sync_refuses_when_session_down(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    res = await _run(service, "/port kss sync", db=db_session)
    assert res["status"] == "CLI_SESSION_DOWN"
    assert "session หลุด" in service.last_text()          # Invariant 7 — no auto-login


@pytest.mark.asyncio
async def test_port_sync_acks_then_pushes_live_card(service, db_session):
    res = await _run(service, "/port kss sync", db=db_session)
    assert res["status"] == "CLI_SYNC"
    assert "กำลังดึงข้อมูลสด" in service.last_text()          # ack via reply
    assert service.pushes and service.pushes[0][1] == "U_OP"  # pushed to the sender


@pytest.mark.asyncio
async def test_orders_default_reads_db_ledger(service, db_session):
    await _seed_order(db_session, "ORD-1", symbol="PTT", status="OPEN")
    await _seed_order(db_session, "ORD-2", symbol="AOT", status="MATCHED")
    res = await _run(service, "/orders kss", db=db_session)
    assert res["status"] == "CLI_ORDERS" and res["count"] == 2
    assert service.replies[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_cash_without_snapshot_is_honest(service, db_session):
    res = await _run(service, "/cash lib", db=db_session)
    assert res["status"] == "CLI_NO_DATA"
    assert "sync" in service.last_text()


@pytest.mark.asyncio
async def test_sync_duplicate_is_busy(service, db_session):
    lock = handlers._lock_for("port", "kss")
    await lock.acquire()
    try:
        res = await _run(service, "/port kss sync", db=db_session)
    finally:
        lock.release()
    assert res["status"] == "CLI_BUSY"
    assert "กำลังทำงานอยู่" in service.last_text()


# --------------------------------------------------------------------------- #
# /nego — guardrails G1–G6
# --------------------------------------------------------------------------- #
def _open_order(order_no="12345", symbol="PTT", side="BUY", price=34.00, balance=1000):
    return {"broker_order_no": order_no, "symbol": symbol, "side": side,
            "price": price, "balance": balance, "volume": balance, "status": "Open"}


def _quote(bid_1=None, offer_1=None, last=None, source="test"):
    return {"symbol": "PTT", "bid_1": bid_1, "offer_1": offer_1, "last": last, "source": source}


@pytest.mark.asyncio
async def test_nego_g1_kill_switch_blocks(service, db_session, monkeypatch):
    from app.services.kill_switch_service import kill_switch_service
    monkeypatch.setattr(kill_switch_service, "is_active", lambda: True)
    res = await _run(service, "/nego kss", db=db_session)
    assert res["status"] == "CLI_KILL_SWITCH"
    assert "KILL-SWITCH" in service.last_text()


@pytest.mark.asyncio
async def test_nego_g2_out_of_hours_blocks(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_in_nego_window", lambda now=None: False)
    res = await _run(service, "/nego kss", db=db_session)
    assert res["status"] == "CLI_OUT_OF_HOURS"


@pytest.mark.asyncio
async def test_nego_g3_session_down_blocks(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    res = await _run(service, "/nego kss", db=db_session)
    assert res["status"] == "CLI_SESSION_DOWN"


@pytest.mark.asyncio
async def test_nego_amends_order_and_audits(service, db_session, monkeypatch):
    from app.db.models import SessionLog
    from sqlalchemy import select
    monkeypatch.setattr(handlers, "_broker_open_orders", AsyncMock(return_value=[_open_order()]))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value=_quote(bid_1=34.25, offer_1=34.50, last=34.00)))

    res = await _run(service, "/nego kss", db=db_session)
    assert res["status"] == "CLI_NEGO" and res["ok"] == 1 and res["failed"] == 0
    handlers._broker_modify.assert_awaited_once()
    assert handlers._broker_modify.await_args.args[0] == "kss"      # broker isolation
    assert service.pushes and service.pushes[-1][0]["type"] == "flex"
    logs = (await db_session.execute(select(SessionLog).where(SessionLog.event_type == "LINE_CLI_NEGO"))).scalars().all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_nego_g5_too_many_ticks_is_skipped(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_open_orders", AsyncMock(return_value=[_open_order(price=34.00)]))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value=_quote(bid_1=36.00, offer_1=36.25)))

    res = await _run(service, "/nego kss", db=db_session)
    assert res["skipped"] == 1 and res["ok"] == 0
    handlers._broker_modify.assert_not_awaited()


@pytest.mark.asyncio
async def test_nego_fails_closed_when_quote_unavailable(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_open_orders", AsyncMock(return_value=[_open_order()]))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value=_quote(source="unavailable")))

    res = await _run(service, "/nego lib", db=db_session)
    assert res["skipped"] == 1 and res["ok"] == 0
    handlers._broker_modify.assert_not_awaited()


@pytest.mark.asyncio
async def test_nego_g6_short_uptick_is_skipped(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, "_broker_open_orders",
                        AsyncMock(return_value=[_open_order(side="SHORT", price=33.50)]))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value=_quote(offer_1=34.00, last=34.25)))

    res = await _run(service, "/nego kss", db=db_session)
    assert res["skipped"] == 1 and res["ok"] == 0
    handlers._broker_modify.assert_not_awaited()


@pytest.mark.asyncio
async def test_nego_filters_by_target_symbol(service, db_session, monkeypatch):
    orders = [_open_order(order_no="1", symbol="PTT"), _open_order(order_no="2", symbol="AOT")]
    monkeypatch.setattr(handlers, "_broker_open_orders", AsyncMock(return_value=orders))
    monkeypatch.setattr(handlers, "_broker_quote", AsyncMock(return_value=_quote(bid_1=34.25)))

    res = await _run(service, "/nego kss PTT", db=db_session)
    assert res["ok"] == 1
    assert handlers._broker_modify.await_args.kwargs["symbol"] == "PTT"


@pytest.mark.asyncio
async def test_nego_empty_queue_is_honest(service, db_session):
    res = await _run(service, "/nego kss", db=db_session)
    assert res["status"] == "CLI_NEGO_EMPTY"
    assert "ไม่มีออเดอร์ค้าง" in service.last_text()


@pytest.mark.asyncio
async def test_nego_duplicate_is_busy(service, db_session):
    lock = handlers._lock_for("nego", "kss")
    await lock.acquire()
    try:
        res = await _run(service, "/nego kss", db=db_session)
    finally:
        lock.release()
    assert res["status"] == "CLI_BUSY"


# --------------------------------------------------------------------------- #
# Webhook E2E — the router really runs inside _handle_text_message
# --------------------------------------------------------------------------- #
HEADERS = {"X-Line-Signature": "mock_signature"}


def _webhook_payload(text, *, user_id="U_OP", source_type="user"):
    return {"events": [{
        "type": "message", "timestamp": 1718000000000,
        "source": {"type": source_type, "userId": user_id},
        "replyToken": "tok-cli-webhook",
        "message": {"type": "text", "id": "msg-cli", "text": text},
    }]}


@pytest.mark.asyncio
async def test_webhook_routes_slash_status_to_cli(client, db_session, monkeypatch):
    from app.services.line_service import line_service
    monkeypatch.setattr(line_service, "_send_reply", AsyncMock())
    _patch_relay(monkeypatch, ready=True)

    resp = await client.post("/api/v1/webhook/line", json=_webhook_payload("/status"), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results and results[0]["status"] == "CLI_STATUS"


@pytest.mark.asyncio
async def test_webhook_still_ignores_plain_text(client, db_session, monkeypatch):
    from app.services.line_service import line_service
    monkeypatch.setattr(line_service, "_send_reply", AsyncMock())

    resp = await client.post("/api/v1/webhook/line", json=_webhook_payload("hello homelab"), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results and results[0]["status"] == "IGNORED"


# --------------------------------------------------------------------------- #
# RCA-006b / RCA-009 — live /port|cash cards must never claim 🟢 on unreadable data
# --------------------------------------------------------------------------- #
def _flex_text(card) -> str:
    return json.dumps(card, ensure_ascii=False)


@pytest.mark.asyncio
async def test_live_port_card_shows_dom_account_when_authenticated(monkeypatch):
    from app.browser.trademan_driver import trademan_driver
    from app.mcp.pillars import pillar2_portfolio as pillar2

    holdings = AsyncMock(return_value={"holdings": [
        {"symbol": "PTT", "volume": 1000, "avg_cost": 34.0, "current_price": 35.0}]})
    monkeypatch.setattr(pillar2, "portfolio_holdings", holdings)
    monkeypatch.setattr(trademan_driver, "portfolio_scrape_authenticated", True, raising=False)
    monkeypatch.setattr(trademan_driver, "portfolio_totals", None, raising=False)
    monkeypatch.setattr(trademan_driver, "active_account_no", "3024959", raising=False)

    card = await REAL_LIVE_CARD("port", "kss")

    holdings.assert_awaited_with(platform="TRADEMAN")
    text = _flex_text(card)
    assert "3024959" in text        # account number read from the DOM
    assert "🟢 live" in text
    assert "อ่านไม่ได้" not in text


@pytest.mark.asyncio
async def test_live_port_card_is_unavailable_when_scrape_not_authenticated(monkeypatch):
    from app.browser.trademan_driver import trademan_driver
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_holdings", AsyncMock(return_value={"holdings": []}))
    monkeypatch.setattr(trademan_driver, "portfolio_scrape_authenticated", False, raising=False)

    card = await REAL_LIVE_CARD("port", "kss")

    text = _flex_text(card)
    assert "อ่านไม่ได้" in text and "session หมดอายุ" in text
    assert "/login kss" in text
    assert "🟢 live" not in text
    assert "มูลค่ารวม" not in text   # no fabricated totals for a failed scrape
    assert "Amount" not in text      # RCA-013: nor the new summary labels


@pytest.mark.asyncio
async def test_live_cash_card_is_unavailable_when_balances_unauthenticated(monkeypatch):
    from app.mcp.pillars import pillar2_portfolio as pillar2

    balances = AsyncMock(return_value={
        "platform": "KRUNGSRI", "authenticated": False,
        "accounts": [{"account_type": "MARGIN", "cash_balance": None, "line_available": None,
                      "excess_equity": None, "is_active": True}]})
    monkeypatch.setattr(pillar2, "portfolio_get_balances", balances)

    card = await REAL_LIVE_CARD("cash", "kss")

    balances.assert_awaited_with(platform="TRADEMAN")
    text = _flex_text(card)
    assert "อ่านไม่ได้" in text and "/login kss" in text
    assert "🟢 live" not in text
    assert "0.00" not in text        # anti-mock: never a fabricated 0.00 balance


@pytest.mark.asyncio
async def test_live_cash_card_is_unavailable_when_every_field_unreadable(monkeypatch):
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value={
        "platform": "KRUNGSRI", "authenticated": True,
        "accounts": [{"account_type": "CASH", "cash_balance": None, "line_available": None,
                      "excess_equity": None, "is_active": True}]}))

    card = await REAL_LIVE_CARD("cash", "kss")

    text = _flex_text(card)
    assert "อ่านไม่ได้" in text
    assert "🟢 live" not in text

# --------------------------------------------------------------------------- #
# RCA-002 — P/L must follow the position side (LONG vs SHORT vs BORROWED)
# --------------------------------------------------------------------------- #
def test_normalise_holdings_pnl_follows_side():
    from app.services.line_cli.handlers import _normalise_holdings

    rows = {r["symbol"]: r for r in _normalise_holdings([
        {"symbol": "LONGOK", "position_type": "LONG", "volume": 100, "avg_cost": 10.0, "current_price": 11.0},
        {"symbol": "SHORTOK", "position_type": "SHORT", "volume": 100, "avg_cost": 10.0, "current_price": 9.0},
        {"symbol": "SHORTLOSS", "position_type": "SHORT", "volume": 100, "avg_cost": 10.0, "current_price": 11.0},
        {"symbol": "BORROWED", "position_type": "BORROWED", "volume": 100, "avg_cost": 0.0, "current_price": 11.0},
        {"symbol": "UNKNOWN", "position_type": "UNKNOWN", "volume": 100, "avg_cost": 10.0, "current_price": 11.0},
    ])}

    assert rows["LONGOK"]["pnl_pct"] == pytest.approx(10.0)
    assert rows["SHORTOK"]["pnl_pct"] == pytest.approx(10.0)      # price fell → short gains
    assert rows["SHORTLOSS"]["pnl_pct"] == pytest.approx(-10.0)   # price rose → short loses
    assert rows["BORROWED"]["pnl_pct"] is None                    # no cost base → "—"
    assert rows["UNKNOWN"]["pnl_pct"] is None                     # side unreadable → "—"


def test_normalise_holdings_defaults_missing_side_to_long():
    """LIBERATOR ``PositionItem`` has no side field → LONG, never UNKNOWN."""
    from app.services.line_cli.handlers import _normalise_holdings

    row = _normalise_holdings([{"symbol": "cpall", "volume": 100, "avg_cost": 10.0, "market_price": 12.0}])[0]

    assert row["position_type"] == "LONG"
    assert row["pnl_pct"] == pytest.approx(20.0)


def test_portfolio_totals_prefers_dom_pnl_and_inverts_short_fallback():
    from app.services.line_cli.handlers import _normalise_holdings, _portfolio_totals

    rows = _normalise_holdings([
        {"symbol": "A", "position_type": "LONG", "volume": 10, "avg_cost": 10.0, "current_price": 11.0,
         "unrealized_pnl": 10.0, "market_value": 110.0},
        {"symbol": "B", "position_type": "SHORT", "volume": 10, "avg_cost": 10.0, "current_price": 12.0,
         "unrealized_pnl": -20.0, "market_value": 120.0},
    ])
    total, pnl = _portfolio_totals(rows)
    assert total == pytest.approx(230.0)
    assert pnl == pytest.approx(-10.0)

    fallback = _normalise_holdings([
        {"symbol": "S", "position_type": "SHORT", "volume": 10, "avg_cost": 10.0, "current_price": 12.0}])
    total, pnl = _portfolio_totals(fallback)
    assert total == pytest.approx(120.0)
    assert pnl == pytest.approx(-20.0)   # short at a loss → negative total


def test_port_card_paginates_into_carousel_and_drops_overflow_teaser():
    from app.services.line_cli import cards

    rows = [{"symbol": f"S{i}", "position_type": "LONG", "volume": 100, "cost": 10.0, "last": 11.0,
             "pnl_pct": 10.0} for i in range(15)]
    card = cards.port_card(broker="KSS", account="3024959", amount=15000.0,
                           pnl_value=1500.0, pnl_pct=10.0, rows=rows, snapshot_label="10:00",
                           stale=False, live=True)

    assert card["contents"]["type"] == "carousel"
    assert len(card["contents"]["contents"]) == 2      # 12 rows + 3 rows
    text = _flex_text(card)
    assert "และอีก" not in text                        # every row is rendered
    assert "Unrealized P/L" in text
    assert "P/L วันนี้" not in text


def test_port_card_tags_short_side_and_shows_dash_for_unreadable_pnl():
    from app.services.line_cli import cards

    rows = [{"symbol": "BCPG", "position_type": "SHORT", "volume": 100, "cost": 10.0, "last": 9.0,
             "pnl_pct": 10.0},
            {"symbol": "MTC", "position_type": "UNKNOWN", "volume": 100, "cost": 0.0, "last": 9.0,
             "pnl_pct": None}]
    card = cards.port_card(broker="KSS", account="3024959", amount=1000.0,
                           pnl_value=100.0, pnl_pct=5.0, rows=rows, snapshot_label="10:00",
                           stale=False, live=True)

    text = _flex_text(card)
    assert "BCPG (S)" in text
    assert "MTC (B)" not in text                       # (B) lives in its own section (D2)
    assert "—" in text
    assert card["contents"]["type"] == "bubble"        # a short book stays a single bubble


# --------------------------------------------------------------------------- #
# CLI-RCA-013 — the card header mirrors the app (Amount + Unrealized P/L)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_live_port_card_prefers_dom_totals_row(monkeypatch):
    """RCA-013: KSS shows the on-page Amount; Market Value is not rendered (D1)."""
    from app.browser.trademan_driver import trademan_driver
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_holdings", AsyncMock(return_value={"holdings": [
        {"symbol": "PTT", "volume": 1000, "avg_cost": 34.0, "current_price": 35.0}]}))
    monkeypatch.setattr(trademan_driver, "portfolio_scrape_authenticated", True, raising=False)
    monkeypatch.setattr(trademan_driver, "active_account_no", "3024959", raising=False)
    monkeypatch.setattr(trademan_driver, "portfolio_totals",
                        {"amount": 33_750.0, "market_value": 35_100.0,
                         "unrealized_pnl": 1_350.0, "account_no": "3024959"}, raising=False)

    card = await REAL_LIVE_CARD("port", "kss")

    text = _flex_text(card)
    assert "33,750.00" in text                              # the DOM row, not the computed 34,000
    assert "34,000.00" not in text and "35,100.00" not in text
    assert "Market Value" not in text
    assert "🟢 live" in text


@pytest.mark.asyncio
async def test_live_port_card_lib_never_shows_a_borrowed_section(monkeypatch):
    """Broker isolation: LIB has no (B) loans — the section is KSS-only."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_holdings", AsyncMock(return_value={"holdings": [
        {"symbol": "BCH", "volume": 4000, "avg_cost": 20.0, "current_price": 21.0}]}))

    card = await REAL_LIVE_CARD("port", "lib")

    text = _flex_text(card)
    assert "หุ้นยืมคงเหลือ" not in text
    assert "Unrealized P/L" in text


def test_port_card_header_labels_match_the_app():
    from app.services.line_cli import cards

    rows = [{"symbol": "DOHOME", "position_type": "SHORT", "volume": 100, "cost": 10.0,
             "last": 9.0, "pnl_pct": 10.0}]
    card = cards.port_card(broker="KSS", account="3024959", amount=1000.0,
                           pnl_value=100.0, pnl_pct=11.11, rows=rows, snapshot_label="10:00",
                           stale=False, live=True)

    body = card["contents"]["body"]["contents"]
    labels = [c["contents"][0]["text"] for c in body
              if c.get("type") == "box" and c.get("layout") == "horizontal"][:2]
    assert labels == ["Amount", "Unrealized P/L"]
    text = _flex_text(card)
    assert "1,000.00" in text
    assert "Market Value" not in text and "มูลค่ารวม" not in text


def test_port_card_totals_render_dash_when_the_page_exposed_nothing():
    """Anti-Mock: an unknown Amount renders — , never a fabricated 0.00."""
    from app.services.line_cli import cards

    card = cards.port_card(broker="KSS", account="3024959", amount=None,
                           pnl_value=-889.59, pnl_pct=-0.17, rows=[], snapshot_label="10:00",
                           stale=False, live=True)

    body = card["contents"]["body"]["contents"]
    shown = {c["contents"][0]["text"]: c["contents"][1]["text"] for c in body
             if c.get("type") == "box" and c.get("layout") == "horizontal"
             and c["contents"][0]["text"] == "Amount"}
    assert shown == {"Amount": "—"}


def test_port_card_renders_borrowed_section_below_the_pl_line():
    """D2/D3: (B) rows leave the table and show as ``หุ้นยืมคงเหลือ (B)`` — qty only."""
    from app.services.line_cli import cards

    rows = [{"symbol": "DOHOME", "position_type": "SHORT", "volume": 2000, "cost": 8.0,
             "last": 8.5, "pnl_pct": 6.25}]
    card = cards.port_card(broker="KSS", account="3024959", amount=531_932.40,
                           pnl_value=-889.59, pnl_pct=-0.17, rows=rows,
                           borrowed=[{"symbol": "MTC", "volume": 1700}],
                           snapshot_label="10:00", stale=False, live=True)

    body = card["contents"]["body"]["contents"]
    keys = [c["contents"][0]["text"] for c in body
            if c.get("type") == "box" and c.get("layout") == "horizontal"]
    assert keys[:3] == ["Amount", "Unrealized P/L", "MTC"]   # loans sit right under P/L
    text = _flex_text(card)
    assert "หุ้นยืมคงเหลือ (B)" in text and "1,700 หุ้น" in text
    assert "DOHOME (S)" in text                             # main table keeps the (S) row
    assert "Market Value" not in text


def test_port_card_omits_borrowed_section_when_there_are_no_loans():
    """D3: no (B) rows → no ``หุ้นยืมคงเหลือ (B)`` heading (long-only / LIB books)."""
    from app.services.line_cli import cards

    rows = [{"symbol": "PTT", "position_type": "LONG", "volume": 1000, "cost": 34.0,
             "last": 35.0, "pnl_pct": 2.94}]
    card = cards.port_card(broker="LIB", account="CASH", amount=34_000.0, pnl_value=1_000.0,
                           pnl_pct=2.94, rows=rows, borrowed=[], snapshot_label="10:00",
                           stale=False, live=True)

    assert "หุ้นยืมคงเหลือ" not in _flex_text(card)


def test_money_formats_thb_and_dash():
    from app.services.line_cli.cards import _money

    assert _money(None) == "—"
    assert _money(0.0) == "0.00"
    assert _money(531932.4) == "531,932.40"


def test_portfolio_amount_excludes_borrowed_but_totals_include_it():
    """Amount = Σ vol×avg of non-BORROWED; the page-level total still counts (B)."""
    from app.services.line_cli.handlers import (
        _normalise_holdings,
        _portfolio_amount,
        _portfolio_totals,
    )

    rows = _normalise_holdings([
        {"symbol": "S1", "position_type": "SHORT", "volume": 10, "avg_cost": 10.0, "current_price": 9.0},
        {"symbol": "S2", "position_type": "SHORT", "volume": 20, "avg_cost": 5.0, "current_price": 6.0},
        {"symbol": "B1", "position_type": "BORROWED", "volume": 10, "avg_cost": 0.0, "current_price": 7.0},
    ])
    assert _portfolio_amount(rows) == pytest.approx(10 * 10.0 + 20 * 5.0)   # (B) excluded
    total, _ = _portfolio_totals(rows)
    assert total == pytest.approx(10 * 9.0 + 20 * 6.0 + 10 * 7.0)           # (B) included


def test_portfolio_amount_is_none_without_any_cost_base():
    from app.services.line_cli.handlers import _normalise_holdings, _portfolio_amount

    rows = _normalise_holdings([{"symbol": "B1", "position_type": "BORROWED",
                                 "volume": 10, "avg_cost": 0.0, "current_price": 7.0}])
    assert _portfolio_amount(rows) is None


def test_split_borrowed_moves_borrowed_out_and_drops_zero_volume():
    """D2/D3: ``(B)`` rows leave the main table; a zero-volume loan is dropped."""
    from app.services.line_cli.handlers import _normalise_holdings, _split_borrowed

    rows = _normalise_holdings([
        {"symbol": "S1", "position_type": "SHORT", "volume": 10, "avg_cost": 10.0, "current_price": 9.0},
        {"symbol": "S2", "position_type": "SHORT", "volume": 20, "avg_cost": 5.0, "current_price": 6.0},
        {"symbol": "MTC", "position_type": "BORROWED", "volume": 1700, "avg_cost": 0.0, "current_price": 28.75},
        {"symbol": "BCPG", "position_type": "BORROWED", "volume": 0, "avg_cost": 0.0, "current_price": 0.0},
    ])
    main, borrowed = _split_borrowed(rows)

    assert [r["symbol"] for r in main] == ["S2", "S1"]      # (B) gone, vol×last order kept
    assert borrowed == [{"symbol": "MTC", "volume": 1700}]  # BCPG (0) dropped


def test_split_borrowed_is_empty_without_borrowed_rows():
    """LIB / long-only books: nothing is moved out, no ``(B)`` section."""
    from app.services.line_cli.handlers import _normalise_holdings, _split_borrowed

    rows = _normalise_holdings([{"symbol": "PTT", "volume": 1000, "avg_cost": 34.0,
                                 "current_price": 35.0}])
    main, borrowed = _split_borrowed(rows)

    assert [r["symbol"] for r in main] == ["PTT"]
    assert borrowed == []


def test_port_card_keeps_long_symbol_with_suffix_unclipped():
    """RCA-012: a long symbol + its side suffix stay in one wrapping text node."""
    from app.services.line_cli import cards

    rows = [{"symbol": "DOHOME", "position_type": "SHORT", "volume": 2000, "cost": 8.0,
             "last": 8.5, "pnl_pct": 6.25}]
    card = cards.port_card(broker="KSS", account="3024959", amount=16_000.0,
                           pnl_value=1_000.0, pnl_pct=6.25, rows=rows,
                           snapshot_label="10:00", stale=False, live=True)

    body = card["contents"]["body"]["contents"]
    boxes = [c for c in body if c.get("type") == "box" and c.get("layout") == "horizontal"]
    header_row = next(c for c in boxes if c["contents"][0].get("text") == "หุ้น")
    symbol_cell = next(c for c in boxes if c["contents"][0].get("text") == "DOHOME (S)")

    assert header_row["contents"][0]["flex"] == 4        # symbol gets the room
    assert header_row["contents"][1]["flex"] == 2        # qty column yields it
    assert symbol_cell["contents"][0]["wrap"] is True    # wraps instead of clipping
    assert symbol_cell["contents"][0]["flex"] == 4
    assert symbol_cell["contents"][1]["flex"] == 2
    assert symbol_cell["contents"][0]["size"] == "xs"    # numbers/labels not shrunk




@pytest.mark.asyncio
async def test_live_cash_card_lib_uses_liberator_balances(monkeypatch):
    """RCA-007 regression at the CLI layer: /cash lib asks LIBERATOR, never Click2Win.

    Also covers the raw-enum leak: LIBERATOR reports ``account_type="CASH_BALANCE"``,
    which must render as a human label — never the raw code.
    """
    from app.mcp.pillars import pillar2_portfolio as pillar2

    balances = AsyncMock(return_value={
        "platform": "LIBERATOR", "authenticated": True,
        "accounts": [{"account_type": "CASH_BALANCE", "cash_balance": 123456.78,
                      "line_available": 200000.0, "excess_equity": 100000.0, "is_active": True}]})
    monkeypatch.setattr(pillar2, "portfolio_get_balances", balances)

    card = await REAL_LIVE_CARD("cash", "lib")

    balances.assert_awaited_with(platform="LIBERATOR")
    text = _flex_text(card)
    assert "LIB" in text
    assert "123,456.78" in text
    assert "🟢 live" in text
    assert "อ่านไม่ได้" not in text
    assert "Cash Balance" in text          # human label in the card header
    assert "CASH_BALANCE" not in text      # raw enum never leaks to LINE


def test_account_type_label_maps_raw_codes():
    from app.services.line_cli.handlers import _account_type_label

    assert _account_type_label("CASH_BALANCE") == "Cash Balance"
    assert _account_type_label("margin") == "Margin"
    assert _account_type_label(None) == "CASH"
    assert _account_type_label("WEIRD_CODE") == "WEIRD_CODE"   # unknown → pass through honestly


# --------------------------------------------------------------------------- #
# CLI-RCA-011 (P2a) — /cash kss binds each figure to the account read off the dropdown
# --------------------------------------------------------------------------- #
def _kss_balances(account_type, *, values_bound=True, line_available=None,
                  cash_balance=None, excess_equity=None, authenticated=True):
    """``portfolio_get_balances()`` payload for one bound (or unbound) KSS account."""
    return {
        "platform": "KRUNGSRI", "authenticated": authenticated,
        "scraped_account_no": "3024959" if values_bound else None,
        "accounts": [{"account_type": account_type, "values_bound": values_bound,
                      "line_available": line_available, "cash_balance": cash_balance,
                      "excess_equity": excess_equity, "is_active": True}],
    }


@pytest.mark.asyncio
async def test_live_cash_card_kss_margin_shows_ee_or_dash(monkeypatch):
    """(a) MARGIN bound + EE unreadable -> ``Excess Equity`` with ``—``; header is Margin and
    the old ``Cash balance`` / ``Buying power`` rows are gone (CLI-RCA-011 D3)."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "MARGIN", line_available=250_000.0, excess_equity=None)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "Line Available" in text and "250,000.00" in text
    assert "Excess Equity" in text and "—" in text
    assert "Margin" in text
    assert "Buying power" not in text
    assert "Cash balance" not in text


@pytest.mark.asyncio
async def test_live_cash_card_kss_margin_shows_ee_value_when_readable(monkeypatch):
    """(a cont.) a readable EE renders as a figure, not the ``—`` placeholder."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "MARGIN", line_available=250_000.0, excess_equity=900_000.0)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "Excess Equity" in text and "900,000.00" in text
    assert "—" not in text


@pytest.mark.asyncio
async def test_live_cash_card_kss_cash_has_no_ee_row(monkeypatch):
    """(c) CASH bound -> a single Line Available row, never an Excess Equity row."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "CASH", line_available=42_000.0)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "42,000.00" in text
    assert "Excess Equity" not in text
    assert "Margin" not in text
    assert "Cash balance" not in text      # P2b: the CASH account exposes no such row


@pytest.mark.asyncio
async def test_live_cash_card_kss_margin_shows_cash_balance_when_readable(monkeypatch):
    """CLI-RCA-011 (P2b): a readable Account Info "Cash Balance" gets its own row.

    It must be a distinct figure from Line Available (PP) — conflating the two was the
    original CLI-RCA-011 bug.
    """
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "MARGIN", line_available=250_000.0, cash_balance=88_000.0, excess_equity=900_000.0)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "Line Available" in text and "250,000.00" in text
    assert "Excess Equity" in text and "900,000.00" in text
    assert "Cash balance" in text and "88,000.00" in text


@pytest.mark.asyncio
async def test_live_cash_card_kss_omits_cash_balance_when_unreadable(monkeypatch):
    """CLI-RCA-011 (P2b): no "Cash balance" row unless the driver read a value (Anti-Mock)."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "CASH", line_available=42_000.0, cash_balance=None)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "Line Available" in text and "42,000.00" in text
    assert "Cash balance" not in text


@pytest.mark.asyncio
async def test_live_cash_card_kss_unbound_account_is_unavailable(monkeypatch):
    """(b) no account bound to the dropdown number -> honest ``อ่านไม่ได้``, never 🟢 live."""
    from app.mcp.pillars import pillar2_portfolio as pillar2

    monkeypatch.setattr(pillar2, "portfolio_get_balances", AsyncMock(return_value=_kss_balances(
        "MARGIN", values_bound=False, line_available=None)))

    text = _flex_text(await REAL_LIVE_CARD("cash", "kss"))

    assert "อ่านไม่ได้" in text and "/login kss" in text
    assert "🟢 live" not in text
    assert "Line Available" not in text




# --------------------------------------------------------------------------- #
# /negotiate — Quick Trade in-place amendment (Pillar 6)
# --------------------------------------------------------------------------- #
def _patch_negotiate(monkeypatch, result):
    import app.services.quicktrade_negotiation_service as svc
    monkeypatch.setattr(svc, 'negotiate_order_price', AsyncMock(return_value=result))
    return svc


@pytest.mark.asyncio
async def test_negotiate_requires_an_order_no(service, db_session):
    res = await _run(service, '/negotiate', db=db_session)
    assert res['status'] == 'CLI_NEGOTIATE_BAD_ARGS'
    assert 'รูปแบบ' in service.last_text()


@pytest.mark.asyncio
async def test_negotiate_kill_switch_blocks(service, db_session, monkeypatch):
    from app.services.kill_switch_service import kill_switch_service
    monkeypatch.setattr(kill_switch_service, 'is_active', lambda: True)
    res = await _run(service, '/negotiate 11008198', db=db_session)
    assert res['status'] == 'CLI_KILL_SWITCH'
    assert 'KILL-SWITCH' in service.last_text()


@pytest.mark.asyncio
async def test_negotiate_out_of_hours_blocks(service, db_session, monkeypatch):
    monkeypatch.setattr(handlers, '_in_nego_window', lambda now=None: False)
    res = await _run(service, '/negotiate 11008198', db=db_session)
    assert res['status'] == 'CLI_OUT_OF_HOURS'


@pytest.mark.asyncio
async def test_negotiate_amends_in_place_and_pushes_card(service, db_session, monkeypatch):
    from app.db.models import SessionLog
    from sqlalchemy import select
    svc = _patch_negotiate(monkeypatch, {
        'success': True, 'order_no': '11008198', 'symbol': 'MTC', 'side': 'SHORT',
        'outcome': 'OK', 'current_price': 29.25, 'target_price': 29.50, 'volume': 500,
        'reason': '', 'amendment': {'success': True, 'submitted': True, 'dry_run': False},
    })

    res = await _run(service, '/negotiate 11008198', db=db_session)
    assert res['status'] == 'CLI_NEGOTIATE' and res['outcome'] == 'OK'
    svc.negotiate_order_price.assert_awaited_once_with('11008198')
    card, target = service.pushes[-1]
    assert card['type'] == 'flex' and 'ต่อราคา #11008198' in card['altText']
    assert target == 'U_OP'
    logs = (await db_session.execute(
        select(SessionLog).where(SessionLog.event_type == 'LINE_CLI_NEGO'))).scalars().all()
    assert any('11008198' in (l.details or '') for l in logs)


@pytest.mark.asyncio
async def test_negotiate_uptick_violation_is_shown_as_failure(service, db_session, monkeypatch):
    _patch_negotiate(monkeypatch, {
        'success': False, 'order_no': '11008198', 'symbol': 'MTC', 'side': 'SHORT',
        'outcome': 'UPTICK_VIOLATION', 'current_price': 29.25, 'target_price': None,
        'volume': 500, 'reason': 'offer_1 29.00 < last 29.25', 'amendment': None,
        'error': 'offer_1 29.00 < last 29.25',
    })

    res = await _run(service, '/negotiate 11008198', db=db_session)
    assert res['outcome'] == 'UPTICK_VIOLATION' and res['success'] is False
    card = service.pushes[-1][0]
    assert card['type'] == 'flex' and 'ผิดกฎ Uptick' in card['altText']


@pytest.mark.asyncio
async def test_negotiate_dry_run_card_never_claims_a_live_submission(service, db_session, monkeypatch):
    """Anti-Mock: a staged DRY-RUN amendment must read `จัดเตรียมไว้`, never `ส่งเข้าตลาดแล้ว`.

    `submitted` is deliberately absent at the top level — the handler must read it from
    `amendment`, and the card must never infer a live submission from `success`.
    """
    _patch_negotiate(monkeypatch, {
        'success': True, 'order_no': '11008198', 'symbol': 'MTC', 'side': 'BUY',
        'outcome': 'OK', 'current_price': 29.00, 'target_price': 29.25, 'volume': 100,
        'reason': '', 'amendment': {'success': True, 'submitted': False, 'dry_run': True,
                                    'status': 'STAGED_DRY_RUN'},
    })

    res = await _run(service, '/negotiate 11008198', db=db_session)
    assert res['status'] == 'CLI_NEGOTIATE' and res['outcome'] == 'OK'
    card = service.pushes[-1][0]
    assert 'จัดเตรียมไว้ (TEST/DRY-RUN)' in str(card)
    assert 'ส่งเข้าตลาดแล้ว' not in str(card)

