"""
End-to-end tests for the per-user LINE conversation flow (2026-10-12).

Drives the REAL webhook `/api/v1/webhook/line` → `line_service._handle_text_message`
→ `conversation_state` engine → terminal DB report, with seeded DB rows so every
assertion is against real data (Anti-Mock).

Covered: happy path (3 turns), `QUERY <SYM>` fast-path, invalid-answer retry,
CANCEL, RESTART, TTL timeout, per-user isolation, the authorization gate
(denial + 1:1 allow), honest "no data", and regressions for the pre-existing
single-shot commands when a `source.userId` is present.

See `docs/handoff/TASK-line-conversation-state.md`.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.db.models import Order, Position, SBLBorrowLot, WatchlistTrigger
from app.services import conversation_state as conv
from app.services.line_service import line_service

HEADERS = {"X-Line-Signature": "mock_signature"}
T = conv.CONVERSATION_TTL_SECONDS

@pytest.fixture(autouse=True)
def _clean_conversations():
    conv.conversation_state.reset()
    conv.conversation_state.set_ttl(T)
    yield
    conv.conversation_state.reset()
    conv.conversation_state.set_ttl(T)


@pytest.fixture
def reply_mock(monkeypatch):
    """Capture the reply text instead of pushing to LINE."""
    mock = AsyncMock()
    monkeypatch.setattr(line_service, "_send_reply", mock)
    return mock


@pytest.fixture
def frozen_clock(monkeypatch):
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(conv, "_now", lambda: clock["t"])
    return clock


def _payload(text, *, user_id="U_OP", source_type="user", group_id=None, reply_token="tok-conv"):
    source = {"type": source_type}
    if user_id:
        source["userId"] = user_id
    if group_id:
        source["groupId"] = group_id
    return {
        "events": [
            {
                "type": "message",
                "timestamp": 1718000000000,
                "source": source,
                "replyToken": reply_token,
                "message": {"type": "text", "id": "msg-conv", "text": text},
            }
        ]
    }


async def _send(client: AsyncClient, reply_mock, text, **kwargs):
    """POST one text message and return `(result_dict, reply_text)`."""
    reply_mock.reset_mock()
    resp = await client.post("/api/v1/webhook/line", json=_payload(text, **kwargs), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    result = results[0] if results else {}
    reply_text = ""
    if reply_mock.await_args is not None:
        args, _ = reply_mock.await_args
        reply_text = args[1] if len(args) > 1 else ""
    return result, reply_text


async def _seed_position(db_session, symbol="PTT", **over):
    pos = Position(
        symbol=symbol,
        position_type=over.get("position_type", "LONG"),
        volume=over.get("volume", 1000),
        avg_cost=over.get("avg_cost", 13.20),
        current_price=over.get("current_price", 13.50),
        unrealized_pnl=over.get("unrealized_pnl", 300.0),
        take_profit_price=over.get("take_profit_price", 14.00),
        stop_loss_price=over.get("stop_loss_price", 12.50),
    )
    db_session.add(pos)
    await db_session.commit()
    return pos


async def _seed_order(db_session, symbol="PTT", side="BUY", volume=1000, price=13.20, status="MATCHED"):
    order = Order(
        order_id=f"ORD-TEST-{symbol}-{side}",
        symbol=symbol,
        side=side,
        volume=volume,
        price=price,
        status=status,
        source="test_seed",
        created_at=datetime(2026, 10, 12, 10, 30),
    )
    db_session.add(order)
    await db_session.commit()
    return order


# --------------------------------------------------------------------------- #
# Happy path + fast path
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_symbol_query_happy_path_three_turns(client: AsyncClient, db_session, reply_mock):
    await _seed_position(db_session, "PTT", volume=1000, avg_cost=13.20, current_price=13.50,
                         unrealized_pnl=300.0, take_profit_price=14.00, stop_loss_price=12.50)

    # 1) trigger
    res, reply = await _send(client, reply_mock, "query")
    assert res["status"] == "CONVERSATION_STARTED"
    assert res["step"] == "await_symbol"
    assert "สัญลักษณ์" in reply

    # 2) symbol
    res, reply = await _send(client, reply_mock, "ptt")
    assert res["status"] == "CONVERSATION_STEP"
    assert res["step"] == "await_metric"
    assert res["slots"]["symbol"] == "PTT"       # normalized to upper-case
    assert "เลือกข้อมูล" in reply

    # 3) metric → terminal report
    res, reply = await _send(client, reply_mock, "1")
    assert res["status"] == "CONVERSATION_COMPLETED"
    assert res["result"]["symbol"] == "PTT"
    assert res["result"]["data_found"] is True
    assert res["result"]["has_position"] is True
    # the reply must carry the SEEDED values, not placeholders
    assert "PTT" in reply and "1,000" in reply and "13.20" in reply
    assert "+300.00" in reply and "14.00" in reply and "12.50" in reply
    assert conv.conversation_state.is_active("U_OP") is False


@pytest.mark.asyncio
async def test_fast_path_symbol_skips_the_symbol_step(client: AsyncClient, db_session, reply_mock):
    await _seed_position(db_session, "AOT")
    res, reply = await _send(client, reply_mock, "QUERY AOT")
    assert res["status"] == "CONVERSATION_STARTED"
    assert res["step"] == "await_metric"
    assert res["slots"]["symbol"] == "AOT"
    assert "เลือกข้อมูล" in reply


@pytest.mark.asyncio
async def test_orders_metric_lists_seeded_orders(client: AsyncClient, db_session, reply_mock):
    await _seed_position(db_session, "PTT")
    await _seed_order(db_session, "PTT", side="SELL", volume=500, price=13.75, status="MATCHED")

    await _send(client, reply_mock, "query")
    await _send(client, reply_mock, "PTT")
    res, reply = await _send(client, reply_mock, "2")
    assert res["status"] == "CONVERSATION_COMPLETED"
    assert res["result"]["recent_orders"] == 1
    assert "SELL 500" in reply and "13.75" in reply and "MATCHED" in reply


@pytest.mark.asyncio
async def test_unknown_symbol_is_reported_honestly(client: AsyncClient, db_session, reply_mock):
    await _send(client, reply_mock, "query")
    await _send(client, reply_mock, "ZZZZ")
    res, reply = await _send(client, reply_mock, "1")
    assert res["status"] == "CONVERSATION_COMPLETED"
    assert res["result"]["data_found"] is False
    assert "ไม่พบข้อมูลหุ้น ZZZZ" in reply


# --------------------------------------------------------------------------- #
# Retry / cancel / restart / timeout
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_invalid_answer_reprompts_without_advancing(client: AsyncClient, db_session, reply_mock):
    await _send(client, reply_mock, "query")
    res, reply = await _send(client, reply_mock, "!!!not-a-symbol!!!")
    assert res["status"] == "CONVERSATION_RETRY"
    assert res["step"] == "await_symbol"
    assert "สัญลักษณ์ไม่ถูกต้อง" in reply
    assert conv.conversation_state.get("U_OP").step == "await_symbol"

    # the metric step rejects junk the same way
    await _send(client, reply_mock, "PTT")
    res, _ = await _send(client, reply_mock, "9")
    assert res["status"] == "CONVERSATION_RETRY"
    assert res["step"] == "await_metric"


@pytest.mark.asyncio
async def test_cancel_clears_the_active_flow(client: AsyncClient, db_session, reply_mock):
    await _send(client, reply_mock, "query")
    res, reply = await _send(client, reply_mock, "ยกเลิก")
    assert res["status"] == "CONVERSATION_CANCELLED"
    assert "ยกเลิก" in reply
    assert conv.conversation_state.is_active("U_OP") is False


@pytest.mark.asyncio
async def test_restart_resets_the_flow_to_step_one(client: AsyncClient, db_session, reply_mock):
    await _send(client, reply_mock, "query")
    await _send(client, reply_mock, "PTT")
    res, _ = await _send(client, reply_mock, "restart")
    assert res["status"] == "CONVERSATION_STARTED"
    assert res["step"] == "await_symbol"
    assert res["slots"] == {}


@pytest.mark.asyncio
async def test_timeout_expires_state_and_next_input_falls_through(
    client: AsyncClient, db_session, reply_mock, frozen_clock
):
    await _send(client, reply_mock, "query")
    assert conv.conversation_state.is_active("U_OP") is True

    frozen_clock["t"] += T + 1                         # past the flow deadline
    res, _ = await _send(client, reply_mock, "PTT")    # not a trigger on its own
    assert res["status"] == "IGNORED"                  # the stale flow no longer owns it
    assert conv.conversation_state.is_active("U_OP") is False


# --------------------------------------------------------------------------- #
# Per-user isolation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_two_users_do_not_share_slots(client: AsyncClient, db_session, reply_mock):
    await _seed_position(db_session, "PTT", volume=1000)
    await _seed_position(db_session, "AOT", volume=2000)

    await _send(client, reply_mock, "query", user_id="U_A")
    await _send(client, reply_mock, "query", user_id="U_B")
    await _send(client, reply_mock, "PTT", user_id="U_A")
    await _send(client, reply_mock, "AOT", user_id="U_B")

    res_a, reply_a = await _send(client, reply_mock, "1", user_id="U_A")
    res_b, reply_b = await _send(client, reply_mock, "1", user_id="U_B")
    assert res_a["result"]["symbol"] == "PTT" and "1,000" in reply_a
    assert res_b["result"]["symbol"] == "AOT" and "2,000" in reply_b


# --------------------------------------------------------------------------- #
# Authorization gate (Decision A)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unauthorized_sender_is_denied_and_creates_no_state(
    client: AsyncClient, db_session, reply_mock, monkeypatch
):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    res, reply = await _send(client, reply_mock, "query", source_type="room")
    assert res["status"] == "CONVERSATION_UNAUTHORIZED"
    assert "ผู้ดูแลระบบ" in reply
    assert conv.conversation_state.snapshot()["active_count"] == 0


@pytest.mark.asyncio
async def test_one_to_one_oa_chat_is_authorized(
    client: AsyncClient, db_session, reply_mock, monkeypatch
):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    res, _ = await _send(client, reply_mock, "query", source_type="user")
    assert res["status"] == "CONVERSATION_STARTED"


@pytest.mark.asyncio
async def test_only_the_configured_group_is_authorized(
    client: AsyncClient, db_session, reply_mock, monkeypatch
):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_OP_GROUP")

    res, _ = await _send(client, reply_mock, "query", source_type="group", group_id="C_OP_GROUP")
    assert res["status"] == "CONVERSATION_STARTED"

    res2, _ = await _send(client, reply_mock, "query", source_type="group", group_id="C_OTHER")
    assert res2["status"] == "CONVERSATION_UNAUTHORIZED"
    # the unauthorized turn must not have touched the authorized user's flow
    assert conv.conversation_state.is_active("U_OP") is True


# --------------------------------------------------------------------------- #
# Regressions: the pre-existing single-shot commands must behave as before
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_idle_non_trigger_text_is_still_ignored(client: AsyncClient, db_session, reply_mock):
    res, _ = await _send(client, reply_mock, "hello homelab")
    assert res["status"] == "IGNORED"
    assert conv.conversation_state.snapshot()["active_count"] == 0


@pytest.mark.asyncio
async def test_close_command_still_works_when_a_sender_is_present(
    client: AsyncClient, db_session, reply_mock
):
    res, reply = await _send(client, reply_mock, "Close AP")
    assert res["status"] == "COMMAND_DISPATCHED"
    assert res["symbol"] == "AP"
    assert "AP" in reply
    assert conv.conversation_state.snapshot()["active_count"] == 0
