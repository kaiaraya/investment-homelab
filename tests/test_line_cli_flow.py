"""
End-to-end tests for the LINE slash-command CLI (TASK-line-cli).

Drives the real handler entrypoint ``app.services.line_cli.handlers.handle`` with
a fake messaging service (captures replies/pushes) and mocked broker edges, so
every assertion is against real handler logic — not a stub. Broker calls are
mocked at the ``line_cli.handlers`` boundary (``_broker_*``), which is exactly
where Broker Isolation lives.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.services.line_cli import handlers
from app.services.line_cli import parser as cli_parser


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
