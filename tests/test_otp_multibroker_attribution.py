"""
LINE-RCA-010 — multi-broker OTP attribution + primary-DB pinning
================================================================

Root causes this suite locks down (2026-10-08, live evidence):

1. **Wrong database (fatal).** The LINE webhook persisted `LINE_OTP_RECEIVED` through
   the *platform-aware* `get_db()` session. `get_session_factory(None)` reads
   `settings.TRADING_PLATFORM`, so with `TRADING_PLATFORM=CLICK2WIN` the row went into
   `investment_homelab_click2win.db` while **every** driver polls `AsyncSessionLocal`
   → the row was invisible → `TIMEOUT (180s)` even though the operator typed the code
   (orphan row `id=26 … 922412 (Ref: N/A)`).
2. **Hard-coded attribution.** The ACK always said "Krungsri Securities" and resolved
   `ref` only from `auth_driver.current_ref`, so a Liberator OTP was labelled
   Krungsri with `Ref: N/A`.

Policy under test: the relay channel is broker-agnostic and **pinned to the primary
DB**; broker + ref come from the newest `OTP_REQUESTED` marker
(**latest-request-wins**, operator decision 2026-10-08).
"""

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.browser.auth_driver import OTP_SESSION_LOG_PATTERN, auth_driver
from app.core.events import event_bus
from app.db.models import SessionLog
from app.schemas.auth import OTPPayload
from app.services import otp_relay_registry as registry
from app.services.line_service import line_service
from app.services.otp_relay_readiness import CHANNEL_LINE_DIRECT


def _drain_otp_queue() -> None:
    """The queue/replay slots are process-wide singletons — never let them leak."""
    while not event_bus.otp_queue.empty():
        event_bus.otp_queue.get_nowait()
    event_bus._latest_otp = None
    event_bus._latest_otp_payload = None


def _utcnow_naive() -> datetime:
    """`session_logs.created_at` is stored as naive UTC — stay consistent."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ pure policy

def test_broker_label_maps_known_tags_case_insensitively():
    assert registry.broker_label("KRUNGSRI") == "Krungsri TradeMan"
    assert registry.broker_label("liberator") == "Liberator WebTrade"
    assert registry.broker_label("CLICK2WIN") == "Settrade Click2Win"
    # An unknown tag falls through unchanged — we never invent a label.
    assert registry.broker_label("WEIRD") == "WEIRD"
    assert registry.broker_label(None) is None
    assert registry.broker_label("") is None


def test_request_marker_round_trips_broker_and_ref():
    d = registry.format_request_details("LIBERATOR", "ANBA", 180)
    assert registry.parse_request_broker(d) == "LIBERATOR"
    assert registry.parse_request_ref(d) == "ANBA"
    # A ref-less request must not read back as a bogus ref.
    assert registry.parse_request_ref(registry.format_request_details("KRUNGSRI", None)) is None


def test_otp_row_keeps_the_driver_pattern_and_gains_a_broker_tag():
    d = registry.format_otp_details("922412", "ANBA", "LIBERATOR")
    assert registry.parse_otp_broker(d) == "LIBERATOR"
    # Zero-Contradiction: the channel-gated DB wait still parses the row.
    assert re.search(OTP_SESSION_LOG_PATTERN, d).group(1) == "922412"


def test_legacy_untagged_otp_row_stays_acceptable():
    """Untagged (legacy / KDE) rows must never be rejected — lenient, not fail-closed."""
    legacy = "Received OTP 6-digits from LINE: 654321 (Ref: SMEG)"
    assert registry.parse_otp_broker(legacy) is None
    assert re.search(OTP_SESSION_LOG_PATTERN, legacy).group(1) == "654321"


# ------------------------------------------------------------------- DB pinning

@pytest.mark.asyncio
async def test_registry_binds_to_the_driver_session_factory():
    """
    The relay must bind to `app.db.session.AsyncSessionLocal` — the *same* factory
    every driver polls — never the platform-aware `get_db()` factory (the fatal bug).
    """
    import app.db.session as db_module

    async with registry._primary_session() as s:
        bound_url = s.get_bind().url
    assert bound_url == db_module.AsyncSessionLocal.kw["bind"].url


@pytest.mark.asyncio
async def test_record_and_resolve_pending_request_round_trip():
    assert await registry.record_request("LIBERATOR", ref="ANBA", ttl_seconds=180)

    pending = await registry.resolve_pending_request()
    assert pending is not None
    assert pending.broker == "LIBERATOR"
    assert pending.ref == "ANBA"
    assert pending.label == "Liberator WebTrade"


@pytest.mark.asyncio
async def test_resolve_pending_request_is_latest_request_wins(db_session):
    now = _utcnow_naive()
    db_session.add(SessionLog(
        event_type="OTP_REQUESTED",
        details=registry.format_request_details("KRUNGSRI", "SMEG"),
        created_at=now - timedelta(seconds=30),
    ))
    db_session.add(SessionLog(
        event_type="OTP_REQUESTED",
        details=registry.format_request_details("LIBERATOR", "ANBA"),
        created_at=now,
    ))
    await db_session.commit()

    pending = await registry.resolve_pending_request()
    assert pending is not None
    assert pending.broker == "LIBERATOR"  # the newest request owns the OTP
    assert pending.ref == "ANBA"


@pytest.mark.asyncio
async def test_resolve_pending_request_ignores_a_stale_marker(db_session):
    db_session.add(SessionLog(
        event_type="OTP_REQUESTED",
        details=registry.format_request_details("LIBERATOR", "ANBA"),
        created_at=_utcnow_naive() - timedelta(seconds=registry.DEFAULT_PENDING_TTL_SECONDS + 60),
    ))
    await db_session.commit()

    assert await registry.resolve_pending_request() is None


@pytest.mark.asyncio
async def test_resolve_pending_request_is_none_without_a_marker():
    assert await registry.resolve_pending_request() is None


# --------------------------------------------- webhook attribution (end-to-end)

async def _post_otp_via_webhook(monkeypatch, text: str, db):
    """Drive the real webhook text handler and capture the LINE reply text."""
    reply = AsyncMock()
    monkeypatch.setattr(line_service, "_send_reply", reply)
    _drain_otp_queue()
    result = await line_service._handle_text_message(
        db, text, {"type": "message", "replyToken": "test-reply-token"}
    )
    return result, reply


@pytest.mark.asyncio
async def test_liberator_otp_is_labelled_liberator_and_persisted_for_drivers(monkeypatch, db_session):
    """
    Liberator asks → operator types the code → the ACK must name Liberator (not
    Krungsri) and the row must land where the drivers read.
    """
    await registry.record_request("LIBERATOR", ref="ANBA", ttl_seconds=180)

    result, reply = await _post_otp_via_webhook(monkeypatch, "922412", db_session)

    assert result["status"] == "OTP_RELAYED"
    assert result["broker"] == "LIBERATOR"
    assert result["ref"] == "ANBA"

    reply_text = reply.await_args.args[1]
    assert "Liberator WebTrade" in reply_text
    assert "Krungsri" not in reply_text   # the hard-coded label is gone
    assert "ANBA" in reply_text           # ...and the ref is no longer "N/A"

    async with registry._primary_session() as probe:
        row = (await probe.execute(
            select(SessionLog).where(SessionLog.event_type == "LINE_OTP_RECEIVED")
        )).scalar_one()
    assert "922412" in row.details
    assert registry.parse_otp_broker(row.details) == "LIBERATOR"


@pytest.mark.asyncio
async def test_webhook_otp_row_is_consumed_by_the_channel_gated_driver_wait(monkeypatch, db_session):
    """
    The money assertion for LINE-RCA-010: webhook write → driver read.

    Before the fix this timed out (the row sat in the CLICK2WIN sandbox DB). The
    in-process queue is drained first so only the cross-process DB hand-off can win.
    The request is Krungsri's, so Phase C's broker filter still lets it through
    (the cross-broker refusal is covered separately).
    """
    await registry.record_request("KRUNGSRI", ref="SMEG", ttl_seconds=180)
    await _post_otp_via_webhook(monkeypatch, "922412", db_session)
    _drain_otp_queue()

    otp, source = await auth_driver._wait_for_otp_multi_channel(
        otp_timeout=3,
        wait_start_time=_utcnow_naive() - timedelta(minutes=1),
        otp_input_sel=None,
        channel=CHANNEL_LINE_DIRECT,
    )
    assert otp == "922412"
    assert source == "line_chat"


@pytest.mark.asyncio
async def test_published_payload_carries_the_broker_tag(monkeypatch, db_session):
    await registry.record_request("LIBERATOR", ref="ANBA")

    await _post_otp_via_webhook(monkeypatch, "922412", db_session)

    payload = event_bus._latest_otp_payload
    assert isinstance(payload, OTPPayload)
    assert payload.broker == "LIBERATOR"
    assert payload.source.value == "line_chat"
    _drain_otp_queue()


@pytest.mark.asyncio
async def test_otp_without_a_marker_falls_back_to_the_awaited_krungsri_ref(monkeypatch, db_session):
    """Legacy path: no marker, but the Krungsri driver demonstrably awaits `SMEG`."""
    auth_driver.current_ref = "SMEG"

    result, reply = await _post_otp_via_webhook(monkeypatch, "123456", db_session)

    assert result["broker"] == "KRUNGSRI"
    assert result["ref"] == "SMEG"
    assert "Krungsri TradeMan" in reply.await_args.args[1]


@pytest.mark.asyncio
async def test_push_otp_request_records_a_marker_before_pushing(monkeypatch):
    push = AsyncMock(return_value=True)
    monkeypatch.setattr(line_service, "push_message", push)

    ok = await line_service.push_otp_request(ref="ANBA", broker="LIBERATOR", timeout_seconds=180)
    assert ok is True

    pending = await registry.resolve_pending_request()
    assert pending is not None
    assert pending.broker == "LIBERATOR"
    assert pending.ref == "ANBA"

    pushed_text = push.await_args.args[0]
    assert "Liberator WebTrade" in pushed_text
    assert "ANBA" in pushed_text


# ------------------------------------------ broker isolation (Phase C filters)

def test_broker_matches_is_lenient_only_for_untagged_rows():
    assert registry.broker_matches("KRUNGSRI", None) is True      # legacy / KDE SMS
    assert registry.broker_matches("KRUNGSRI", "KRUNGSRI") is True
    assert registry.broker_matches("KRUNGSRI", "TRADEMAN") is True
    assert registry.broker_matches("LIBERATOR", "LIBERATOR") is True
    # Cross-broker consumption is refused in both directions.
    assert registry.broker_matches("KRUNGSRI", "LIBERATOR") is False
    assert registry.broker_matches("LIBERATOR", "KRUNGSRI") is False


@pytest.mark.asyncio
async def test_krungsri_driver_ignores_a_liberator_tagged_row(db_session):
    db_session.add(SessionLog(
        event_type="LINE_OTP_RECEIVED",
        details=registry.format_otp_details("922412", "ANBA", "LIBERATOR"),
        created_at=_utcnow_naive(),
    ))
    await db_session.commit()
    _drain_otp_queue()

    with pytest.raises(TimeoutError):
        await auth_driver._wait_for_otp_multi_channel(
            otp_timeout=1,
            wait_start_time=_utcnow_naive() - timedelta(minutes=1),
            otp_input_sel=None,
            channel=CHANNEL_LINE_DIRECT,
        )


@pytest.mark.asyncio
async def test_krungsri_driver_accepts_its_own_tagged_row(db_session):
    db_session.add(SessionLog(
        event_type="LINE_OTP_RECEIVED",
        details=registry.format_otp_details("445566", "SMEG", "KRUNGSRI"),
        created_at=_utcnow_naive(),
    ))
    await db_session.commit()
    _drain_otp_queue()

    otp, source = await auth_driver._wait_for_otp_multi_channel(
        otp_timeout=3,
        wait_start_time=_utcnow_naive() - timedelta(minutes=1),
        otp_input_sel=None,
        channel=CHANNEL_LINE_DIRECT,
    )
    assert otp == "445566"
    assert source == "line_chat"


def test_both_drivers_wire_the_shared_broker_filter():
    """
    Zero-Contradiction guard: both drivers must consume the *shared* filter, so the
    broker-isolation rule cannot silently drift apart between them.
    """
    from pathlib import Path
    import re as _re

    root = Path(__file__).resolve().parents[1]
    auth_src = (root / "app" / "browser" / "auth_driver.py").read_text(encoding="utf-8")
    liberator_src = (root / "app" / "brokers" / "liberator" / "driver.py").read_text(encoding="utf-8")

    assert 'driver_broker = "KRUNGSRI"' in auth_src
    assert 'driver_broker = "LIBERATOR"' in liberator_src
    for src in (auth_src, liberator_src):
        # The DB (cross-process) path AND the in-process queue path are both gated.
        assert "broker_matches(driver_broker" in src
        assert "parse_otp_broker(" in src
        assert _re.search(r"if not broker_matches\(driver_broker, _?row_broker\)", src)
