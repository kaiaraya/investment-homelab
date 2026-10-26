"""
Flow tests for the Phase-B order draft (B.5): ``/buy /sell /short /cover`` →
pre-trade check → draft (TTL 3 min) → confirmation card → confirm/cancel postback.

Drives the real ``app.services.line_cli.handlers.handle`` / ``handle_postback`` with a
fake messaging service, exactly like ``test_line_cli_flow.py``. Broker edges are mocked
at the ``handlers`` boundary; the DB (``broker_accounts`` / ``positions`` /
``sbl_borrow_lots``) is seeded per test so the pre-trade check reads real rows.
"""

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.services.line_cli import handlers
from app.services.line_cli import parser as cli_parser


# --------------------------------------------------------------------------- #
# Fake service / event helpers
# --------------------------------------------------------------------------- #
class FakeService:
    def __init__(self):
        self.replies = []
        self.pushes = []

    async def _send_reply(self, reply_token, message_or_text):
        self.replies.append(message_or_text)

    async def push_message(self, message_or_text, to_user_id=None):
        self.pushes.append((message_or_text, to_user_id))
        return True

    def last_text(self):
        m = self.replies[-1] if self.replies else ""
        if isinstance(m, str):
            return m
        return m.get("text") or m.get("altText") or ""


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


def _card_text(card):
    return json.dumps(card, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def service():
    return FakeService()


@pytest.fixture(autouse=True)
def _edges(monkeypatch):
    """Mock the broker edge + kill-switch so a draft never touches a browser."""
    monkeypatch.setattr(handlers, "_broker_sync_cdp", AsyncMock(return_value=None))
    handlers._DRAFTS.clear()
    handlers._LOCKS.clear()
    handlers._STARTED.clear()
    yield
    handlers._DRAFTS.clear()


async def _run(service, text, *, db, **ev):
    parsed = cli_parser.parse(text)
    return await handlers.handle(parsed, db=db, raw_event=_event(**ev), service=service)


# --------------------------------------------------------------------------- #
# Seed helpers
# --------------------------------------------------------------------------- #
async def _seed_account(db, account_no="7055938", broker="LIBERATOR",
                        account_type="CASH_BALANCE", line_available=50_000.0):
    from app.db.models import BrokerAccount
    from sqlalchemy import select
    existing = (await db.execute(
        select(BrokerAccount).where(BrokerAccount.account_no == account_no))).scalar_one_or_none()
    if existing is None:
        db.add(BrokerAccount(account_no=account_no, broker=broker,
                             account_type=account_type, line_available=line_available))
        await db.commit()


async def _seed_position(db, symbol="PTT", account_no="7055938",
                         position_type="LONG", volume=500):
    from app.db.models import Position
    db.add(Position(account_no=account_no, symbol=symbol, position_type=position_type,
                    volume=volume, avg_cost=12.0))
    await db.commit()


async def _seed_sbl(db, symbol="TISCO", remaining_qty=1000):
    from app.db.models import SBLBorrowLot
    db.add(SBLBorrowLot(lot_id=f"LOT-{symbol}", symbol=symbol, borrow_qty=remaining_qty,
                        remaining_qty=remaining_qty, borrow_date=date.today(), status="ACTIVE"))
    await db.commit()


# --------------------------------------------------------------------------- #
# /buy → draft → confirmation card (happy path)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_buy_drafts_and_shows_confirmation_card(service, db_session):
    await _seed_account(db_session, "7055938", "LIBERATOR", "CASH_BALANCE", line_available=50_000.0)

    res = await _run(service, "/buy PTT 100 12.50", db=db_session)

    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert res["draft_id"].startswith("DRAFT-")
    card = service.replies[0]
    assert card["type"] == "flex"
    text = _card_text(card)
    # order details + side-coloured badge + expiry note
    assert "PTT" in text and "BUY" in text and "12.50" in text and "1,250.00" in text
    assert "หมดอายุใน 3 นาที" in text
    # both postback buttons carry the opaque draft_id
    assert f"action=trade_draft_confirm&draft_id={res['draft_id']}" in text
    assert f"action=trade_draft_cancel&draft_id={res['draft_id']}" in text
    # the draft is live in the store
    assert res["draft_id"] in handlers._DRAFTS


@pytest.mark.asyncio
async def test_buy_badge_is_green_short_badge_is_red(service, db_session):
    from app.services.line_cli import cards

    buy = cards.trade_confirmation_card(
        draft_id="DRAFT-1", cmd="buy", symbol="PTT", volume=100, price=12.50,
        broker="lib", account="cash", account_no="7055938", total_thb=1250.0, ttl_seconds=180)
    short = cards.trade_confirmation_card(
        draft_id="DRAFT-2", cmd="short", symbol="TISCO", volume=100, price=124.50,
        broker="kss", account="margin", account_no="3024959", total_thb=12450.0, ttl_seconds=180)

    assert cards.UP in _card_text(buy)          # green for BUY
    assert cards.DOWN in _card_text(short)      # red for SHORT


# --------------------------------------------------------------------------- #
# Pre-trade guardrails (rejections)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_buy_rejects_odd_lot(service, db_session):
    await _seed_account(db_session)
    res = await _run(service, "/buy PTT 150 12.50", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_BAD_LOT"
    assert "board lot" in service.last_text()
    assert not handlers._DRAFTS


@pytest.mark.asyncio
async def test_buy_rejects_bad_tick_size(service, db_session):
    await _seed_account(db_session)
    res = await _run(service, "/buy PTT 100 12.55", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_BAD_TICK"


@pytest.mark.asyncio
async def test_buy_rejects_insufficient_line(service, db_session):
    await _seed_account(db_session, line_available=5_000.0)
    res = await _run(service, "/buy PTT 100 100.00", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_INSUFFICIENT_LINE"
    assert "วงเงินไม่พอ" in service.last_text()


@pytest.mark.asyncio
async def test_buy_rejects_missing_line_available(service, db_session):
    # no BrokerAccount row at all -> line_available unreadable -> fail-closed
    res = await _run(service, "/buy PTT 100 12.50", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_NO_LINE_AVAILABLE"


@pytest.mark.asyncio
async def test_sell_requires_a_position(service, db_session):
    res = await _run(service, "/sell PTT 100 13.00", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_NO_POSITION"


@pytest.mark.asyncio
async def test_sell_rejects_volume_above_holding(service, db_session):
    await _seed_position(db_session, "PTT", volume=100)
    res = await _run(service, "/sell PTT 300 13.00", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_INSUFFICIENT_POSITION"


@pytest.mark.asyncio
async def test_sell_drafts_when_position_holds_enough(service, db_session):
    await _seed_position(db_session, "PTT", volume=500)
    res = await _run(service, "/sell PTT 300 13.00", db=db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"


@pytest.mark.asyncio
async def test_short_requires_sbl_borrow(service, db_session):
    await _seed_account(db_session, "3024959", "KRUNGSRI", "CREDIT_BALANCE", line_available=634_864.16)
    res = await _run(service, "/short TISCO 100 124.50", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_NO_SBL"


@pytest.mark.asyncio
async def test_short_drafts_with_sbl_and_line(service, db_session):
    await _seed_account(db_session, "3024959", "KRUNGSRI", "CREDIT_BALANCE", line_available=634_864.16)
    await _seed_sbl(db_session, "TISCO", remaining_qty=1000)
    res = await _run(service, "/short TISCO 100 124.50", db=db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert res["draft_id"] in handlers._DRAFTS


@pytest.mark.asyncio
async def test_lib_margin_override_is_rejected(service, db_session):
    res = await _run(service, "/buy lib:margin PTT 100 12.50", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED" and res["code"] == "E_BAD_ACCOUNT"


@pytest.mark.asyncio
async def test_kill_switch_blocks_order_draft(service, db_session, monkeypatch):
    from app.services.kill_switch_service import kill_switch_service
    monkeypatch.setattr(kill_switch_service, "is_active", lambda: True)
    res = await _run(service, "/buy PTT 100 12.50", db=db_session)
    assert res["status"] == "CLI_KILL_SWITCH"


# --------------------------------------------------------------------------- #
# Confirm / cancel postbacks
# --------------------------------------------------------------------------- #
async def _draft(service, db_session, text="/buy PTT 100 12.50"):
    await _seed_account(db_session)
    res = await _run(service, text, db=db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    return res


@pytest.mark.asyncio
async def test_confirm_returns_draft_id_and_order(service, db_session):
    drafted = await _draft(service, db_session)
    draft_id = drafted["draft_id"]

    res = await handlers.handle_postback(
        f"action=trade_draft_confirm&draft_id={draft_id}",
        db=db_session, raw_event=_event(), service=service,
    )

    assert res["status"] == "TRADE_DRAFT_CONFIRMED"
    assert res["draft_id"] == draft_id
    assert res["order"]["symbol"] == "PTT"
    assert res["order"]["cmd"] == "buy"
    assert res["order"]["volume"] == 100
    assert res["order"]["broker"] == "lib" and res["order"]["account"] == "cash"
    # the draft is consumed (idempotency: a replay can't confirm twice)
    assert draft_id not in handlers._DRAFTS
    # receipt card was pushed
    assert "ยืนยันคำสั่งแล้ว" in _text_of(service.replies[-1])


@pytest.mark.asyncio
async def test_cancel_drops_the_draft(service, db_session):
    drafted = await _draft(service, db_session)
    draft_id = drafted["draft_id"]

    res = await handlers.handle_postback(
        f"action=trade_draft_cancel&draft_id={draft_id}",
        db=db_session, raw_event=_event(), service=service,
    )

    assert res["status"] == "TRADE_DRAFT_CANCELLED"
    assert res["draft_id"] == draft_id and res["found"] is True
    assert draft_id not in handlers._DRAFTS
    assert "ยกเลิกคำสั่งแล้ว" in _text_of(service.replies[-1])


@pytest.mark.asyncio
async def test_confirm_after_cancel_or_unknown_draft_is_expired(service, db_session):
    # an unknown / already-consumed draft_id must never confirm
    res = await handlers.handle_postback(
        "action=trade_draft_confirm&draft_id=DRAFT-DEADBEEF",
        db=db_session, raw_event=_event(), service=service,
    )
    assert res["status"] == "TRADE_DRAFT_EXPIRED"
    assert "หมดอายุ" in service.last_text()


@pytest.mark.asyncio
async def test_draft_expires_after_ttl(service, db_session, monkeypatch):
    import time as _time
    drafted = await _draft(service, db_session)
    draft_id = drafted["draft_id"]

    # age the draft beyond the TTL and prove it can no longer be taken
    handlers._DRAFTS[draft_id]["created_at"] = _time.time() - (handlers.DRAFT_TTL_SECONDS + 1)
    assert handlers._take_draft(draft_id) is None
    assert draft_id not in handlers._DRAFTS


@pytest.mark.asyncio
async def test_purge_drafts_removes_only_expired(service, db_session, monkeypatch):
    import time as _time
    await _draft(service, db_session, "/buy PTT 100 12.50")
    await _draft(service, db_session, "/buy AOT 100 20.00")
    ids = list(handlers._DRAFTS.keys())
    handlers._DRAFTS[ids[0]]["created_at"] = _time.time() - 999
    removed = handlers._purge_drafts()
    assert removed == 1
    assert ids[0] not in handlers._DRAFTS and ids[1] in handlers._DRAFTS


def test_purge_drafts_honours_settings_card_ttl(monkeypatch):
    """2.2b — draft TTL must come from settings.CARD_TTL_SECONDS (call-time), not hardcoded 180."""
    from app.core.config import settings
    import time as _time

    monkeypatch.setattr(settings, "CARD_TTL_SECONDS", 5)
    assert handlers.DRAFT_TTL_SECONDS == 5

    handlers._DRAFTS.clear()
    now = _time.time()
    # 6-second-old draft: expired under TTL=5 (would still be alive under hardcoded 180)
    handlers._DRAFTS["DRF-exp"] = {"draft_id": "DRF-exp", "created_at": now - 6}
    # 3-second-old draft: active under TTL=5
    handlers._DRAFTS["DRF-act"] = {"draft_id": "DRF-act", "created_at": now - 3}

    removed = handlers._purge_drafts()
    assert removed == 1
    assert "DRF-exp" not in handlers._DRAFTS
    assert "DRF-act" in handlers._DRAFTS


@pytest.mark.asyncio
async def test_handle_postback_ignores_foreign_actions(service, db_session):
    res = await handlers.handle_postback(
        "action=batch_approve&batch_id=X", db=db_session, raw_event=_event(), service=service,
    )
    assert res is None                      # let line_service fall through


# --------------------------------------------------------------------------- #
# Webhook E2E — line_service routes the postback to the draft handler
# --------------------------------------------------------------------------- #
HEADERS = {"X-Line-Signature": "mock_signature"}


def _postback_payload(data, *, user_id="U_OP"):
    return {"events": [{
        "type": "postback", "timestamp": 1718000000000,
        "source": {"type": "user", "userId": user_id},
        "replyToken": "tok-postback",
        "postback": {"data": data},
    }]}


@pytest.mark.asyncio
async def test_webhook_routes_trade_draft_confirm(client, db_session, monkeypatch):
    from app.services.line_service import line_service

    # Draft one order through the real handler so a draft_id exists in memory.
    svc = FakeService()
    await _seed_account(db_session)
    drafted = await _run(svc, "/buy PTT 100 12.50", db=db_session)
    draft_id = drafted["draft_id"]

    monkeypatch.setattr(line_service, "_send_reply", AsyncMock())

    resp = await client.post(
        "/api/v1/webhook/line",
        json=_postback_payload(f"action=trade_draft_confirm&draft_id={draft_id}"),
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert results and results[0]["status"] == "TRADE_DRAFT_CONFIRMED"
    assert results[0]["draft_id"] == draft_id


# --------------------------------------------------------------------------- #
# 2.1 — SHORT confirm must carry last_trade_price (G6) and fail closed
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_short_confirm_passes_last_trade_price(service, db_session, monkeypatch):
    from app.services.broker_cdp import order_executor as oe

    await _seed_account(db_session, "3024959", "KRUNGSRI", "CREDIT_BALANCE",
                        line_available=634_864.16)
    await _seed_sbl(db_session, "TISCO", remaining_qty=1000)
    drafted = await _run(service, "/short TISCO 100 124.50", db=db_session)
    assert drafted["status"] == "CLI_TRADE_DRAFTED"

    async def _quote(broker, symbol):
        return {"last": 125.0, "bid_1": 124.9, "offer_1": 125.1, "source": "streaming_dom"}

    monkeypatch.setattr(handlers, "_broker_quote", _quote)

    seen = {}

    async def _fake_exec(order, **kwargs):
        seen["kwargs"] = kwargs
        return {"success": True, "status": "DRY_RUN"}

    monkeypatch.setattr(oe, "execute_confirmed_order", _fake_exec)

    res = await handlers.handle_postback(
        f"action=trade_draft_confirm&draft_id={drafted['draft_id']}",
        db=db_session, raw_event=_event(), service=service,
    )
    assert res["status"] == "TRADE_DRAFT_CONFIRMED"
    assert seen["kwargs"]["last_trade_price"] == 125.0


@pytest.mark.asyncio
async def test_short_confirm_without_quote_fails_closed(service, db_session, monkeypatch):
    from app.services.broker_cdp import order_executor as oe

    await _seed_account(db_session, "3024959", "KRUNGSRI", "CREDIT_BALANCE",
                        line_available=634_864.16)
    await _seed_sbl(db_session, "TISCO", remaining_qty=1000)
    drafted = await _run(service, "/short TISCO 100 124.50", db=db_session)

    async def _no_quote(broker, symbol):
        return {"last": None, "bid_1": None, "offer_1": None, "source": "unavailable"}

    monkeypatch.setattr(handlers, "_broker_quote", _no_quote)

    called = {"n": 0}

    async def _fake_exec(order, **kwargs):
        called["n"] += 1
        return {"success": True, "status": "DRY_RUN"}

    monkeypatch.setattr(oe, "execute_confirmed_order", _fake_exec)

    res = await handlers.handle_postback(
        f"action=trade_draft_confirm&draft_id={drafted['draft_id']}",
        db=db_session, raw_event=_event(), service=service,
    )
    assert res["execution"]["status"] == "REJECTED"
    assert res["execution"]["error_code"] == "E_NO_QUOTE"
    assert called["n"] == 0          # never reached the executor


# --------------------------------------------------------------------------- #
# 2.6 — value-based sizing edge cases
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_value_order_resolves_board_lot_from_quote(service, db_session, monkeypatch):
    await _seed_account(db_session, line_available=100_000.0)

    async def _quote(broker, symbol):
        return {"last": 12.50, "offer_1": 12.50, "bid_1": 12.40, "source": "streaming_dom"}

    monkeypatch.setattr(handlers, "_broker_quote", _quote)

    res = await _run(service, "/buy PTT 50k", db=db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert res["card"]["type"] == "flex"
    assert "4,000" in _card_text(res["card"])       # 50,000 / 12.50 = 4,000 shares


@pytest.mark.asyncio
async def test_value_order_floors_not_ceils(service, db_session):
    # explicit price → no quote needed; 50,000 / 34.50 = 1,449.27 → 1,400 shares
    await _seed_account(db_session, line_available=100_000.0)
    res = await _run(service, "/buy PTT 50000b 34.50", db=db_session)
    assert res["status"] == "CLI_TRADE_DRAFTED"
    assert "1,400" in _card_text(res["card"])


@pytest.mark.asyncio
async def test_value_order_insufficient_budget(service, db_session):
    await _seed_account(db_session, line_available=100_000.0)
    res = await _run(service, "/buy PTT 500b 34.50", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED"
    assert res["code"] == "E_INSUFFICIENT_BUDGET"


@pytest.mark.asyncio
async def test_value_order_without_quote_is_rejected(service, db_session, monkeypatch):
    await _seed_account(db_session, line_available=100_000.0)

    async def _no_quote(broker, symbol):
        return {"last": None, "bid_1": None, "offer_1": None, "source": "unavailable"}

    monkeypatch.setattr(handlers, "_broker_quote", _no_quote)
    res = await _run(service, "/buy PTT 50k", db=db_session)
    assert res["status"] == "CLI_TRADE_REJECTED"
    assert res["code"] == "E_NO_QUOTE"
