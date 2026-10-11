"""
LINE-RCA-009 — the authoritative OTP channel must be the one that actually captures.
====================================================================================

Root cause this suite locks down (2026-10-08):
`auth_driver._wait_for_otp_multi_channel()` Check-3 polled KDE Connect notifications
every 0.5s **ungated**, so while LINE was supposed to be authoritative the OTP was
captured via the dormant KDE fallback — no `LINE_OTP_RECEIVED` row was ever written and
LINE delivery could not be proven (re-login 17:05 showed `LOGIN_SUCCESS` with neither a
LINE nor a KDE row because the direct poll never logs one).

These tests assert the *policy* (pure helpers) and the *behaviour* (which capture path
may win) so the regression cannot silently come back.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from app.browser.auth_driver import _safe_otp_source, auth_driver
from app.core.events import event_bus
from app.db.models import SessionLog
from app.schemas.auth import AuthStatus, LoginResult, OTPPayload, OTPSource
from app.services.otp_relay_readiness import (
    CHANNEL_KDE_CONNECT,
    CHANNEL_LINE_DIRECT,
    CHANNEL_LINE_GROUP,
    CHANNEL_NONE,
    channel_accepts_source,
    channel_allows_kde,
    channel_db_event_types,
    event_type_to_source,
)


def _drain_otp_queue() -> None:
    """The queue is a process-wide singleton — never let a stale item drive a test."""
    while not event_bus.otp_queue.empty():
        event_bus.otp_queue.get_nowait()
    event_bus._latest_otp = None
    event_bus._latest_otp_payload = None


# ------------------------------------------------------------------ pure policy

def test_channel_allows_kde_only_for_the_kde_channel():
    assert channel_allows_kde(CHANNEL_KDE_CONNECT) is True
    assert channel_allows_kde(CHANNEL_LINE_GROUP) is False
    assert channel_allows_kde(CHANNEL_LINE_DIRECT) is False
    assert channel_allows_kde(CHANNEL_NONE) is False


def test_channel_db_event_types_are_channel_scoped_and_fail_closed():
    assert channel_db_event_types(CHANNEL_LINE_GROUP) == ("LINE_OTP_RECEIVED",)
    assert channel_db_event_types(CHANNEL_LINE_DIRECT) == ("LINE_OTP_RECEIVED",)
    assert channel_db_event_types(CHANNEL_KDE_CONNECT) == ("KDECONNECT_OTP_RECEIVED",)
    # unknown / none channel => no acceptable row at all (fail-closed)
    assert channel_db_event_types(CHANNEL_NONE) == ()
    assert channel_db_event_types("garbage-channel") == ()


def test_channel_accepts_source_rejects_cross_channel_capture():
    # A KDE capture may never satisfy a LINE channel (this IS the bug class)
    assert channel_accepts_source(CHANNEL_LINE_DIRECT, "kdeconnect_direct") is False
    assert channel_accepts_source(CHANNEL_LINE_GROUP, "kdeconnect_sms") is False
    # ...and a LINE capture may not satisfy a KDE-only channel
    assert channel_accepts_source(CHANNEL_KDE_CONNECT, "line_chat") is False
    # matching pairs are accepted
    assert channel_accepts_source(CHANNEL_LINE_DIRECT, "line_chat") is True
    assert channel_accepts_source(CHANNEL_KDE_CONNECT, "kdeconnect_sms") is True
    # operator-typed / in-process paths are channel-agnostic
    assert channel_accepts_source(CHANNEL_LINE_DIRECT, "browser_dom_manual") is True
    assert channel_accepts_source(CHANNEL_NONE, "event_bus") is True


def test_event_type_to_source_is_an_honest_mapping():
    assert event_type_to_source("LINE_OTP_RECEIVED") == "line_chat"
    assert event_type_to_source("KDECONNECT_OTP_RECEIVED") == "kdeconnect_sms"


# ------------------------------------------------------- LoginResult: otp_source

def test_login_result_carries_otp_source_and_stays_dict_compatible():
    res = LoginResult(
        success=True,
        status=AuthStatus.AUTHENTICATED,
        otp_source=OTPSource.LINE_CHAT,
    )
    assert res.otp_source == OTPSource.LINE_CHAT
    assert res["otp_source"] == "line_chat"   # HybridBaseModel dict access
    # No OTP was needed => no attribution is invented
    assert LoginResult(success=True, status=AuthStatus.AUTHENTICATED).otp_source is None


def test_safe_otp_source_never_invents_a_channel():
    assert _safe_otp_source(None) is None
    assert _safe_otp_source("") is None
    assert _safe_otp_source("line_chat") == OTPSource.LINE_CHAT
    assert _safe_otp_source("browser_dom_manual") == OTPSource.BROWSER_DOM
    assert _safe_otp_source("totally-unknown-tag") is None


# ------------------------------------------------- capture-path gating (behaviour)

@pytest.mark.asyncio
async def test_line_channel_never_polls_kde_connect(monkeypatch):
    """
    THE REGRESSION: with an authoritative LINE channel the dormant KDE poll must not run.

    Before the fix this poll ran every 0.5s regardless of channel and won the race, so the
    OTP was captured via KDE with no `LINE_OTP_RECEIVED` row — LINE delivery unprovable.
    """
    from app.services.kdeconnect_service import kdeconnect_service

    _drain_otp_queue()
    poll = AsyncMock(return_value=None)
    monkeypatch.setattr(kdeconnect_service, "poll_active_notifications", poll)

    with pytest.raises(TimeoutError):
        await auth_driver._wait_for_otp_multi_channel(
            otp_timeout=1,
            wait_start_time=datetime.now(timezone.utc),
            otp_input_sel=None,
            channel=CHANNEL_LINE_DIRECT,
        )

    poll.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_channel_fails_closed_without_touching_kde(monkeypatch):
    """channel='none' must neither read the DB nor poll KDE (fail-closed default)."""
    from app.services.kdeconnect_service import kdeconnect_service

    _drain_otp_queue()
    poll = AsyncMock(return_value=None)
    monkeypatch.setattr(kdeconnect_service, "poll_active_notifications", poll)

    with pytest.raises(TimeoutError):
        await auth_driver._wait_for_otp_multi_channel(
            otp_timeout=1,
            wait_start_time=datetime.now(timezone.utc),
            otp_input_sel=None,
            channel=CHANNEL_NONE,
        )

    poll.assert_not_awaited()


@pytest.mark.asyncio
async def test_kde_channel_still_polls_kde_connect(monkeypatch):
    """When the operator explicitly re-enables the fallback the KDE path must still work."""
    from app.services.kdeconnect_service import kdeconnect_service

    _drain_otp_queue()

    class _FakePayload:
        otp = "123456"
        masked_otp = "12****"
        ref = "SMEG"

    poll = AsyncMock(return_value=_FakePayload())
    monkeypatch.setattr(kdeconnect_service, "poll_active_notifications", poll)

    otp, source = await auth_driver._wait_for_otp_multi_channel(
        otp_timeout=3,
        wait_start_time=datetime.now(timezone.utc),
        otp_input_sel=None,
        channel=CHANNEL_KDE_CONNECT,
    )

    assert otp == "123456"
    assert source == "kdeconnect_direct"
    poll.assert_awaited()


@pytest.mark.asyncio
async def test_line_channel_reads_line_row_and_reports_line_chat(db_session):
    """A `LINE_OTP_RECEIVED` row satisfies the LINE channel and is attributed honestly."""
    _drain_otp_queue()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(SessionLog(
        event_type="LINE_OTP_RECEIVED",
        details="Received OTP 6-digits from LINE: 654321 (Ref: SMEG)",
        created_at=now,
    ))
    await db_session.commit()

    otp, source = await auth_driver._wait_for_otp_multi_channel(
        otp_timeout=3,
        wait_start_time=now - timedelta(minutes=1),
        otp_input_sel=None,
        channel=CHANNEL_LINE_DIRECT,
    )

    assert otp == "654321"
    assert source == "line_chat"
    assert _safe_otp_source(source) == OTPSource.LINE_CHAT


@pytest.mark.asyncio
async def test_line_channel_ignores_kdeconnect_row_in_db(db_session):
    """A legacy KDE row must NOT satisfy an authoritative LINE channel."""
    _drain_otp_queue()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(SessionLog(
        event_type="KDECONNECT_OTP_RECEIVED",
        details="Received SMS OTP: 111111 (Ref: SMEG)",
        created_at=now,
    ))
    await db_session.commit()

    with pytest.raises(TimeoutError):
        await auth_driver._wait_for_otp_multi_channel(
            otp_timeout=1,
            wait_start_time=now - timedelta(minutes=1),
            otp_input_sel=None,
            channel=CHANNEL_LINE_DIRECT,
        )


@pytest.mark.asyncio
async def test_line_channel_ignores_queued_kde_payload():
    """An in-process KDE-sourced payload must not satisfy an authoritative LINE channel."""
    _drain_otp_queue()
    await event_bus.publish_otp(OTPPayload(otp="222222", ref="SMEG", source=OTPSource.KDE_CONNECT))
    assert event_bus.otp_queue.qsize() == 1

    with pytest.raises(TimeoutError):
        await auth_driver._wait_for_otp_multi_channel(
            otp_timeout=1,
            wait_start_time=datetime.now(timezone.utc),
            otp_input_sel=None,
            channel=CHANNEL_LINE_DIRECT,
        )

    # The cross-channel payload was consumed and discarded, not silently accepted
    assert event_bus.otp_queue.empty()
    _drain_otp_queue()


@pytest.mark.asyncio
async def test_line_channel_accepts_queued_line_payload():
    """The legitimate LINE webhook path (EventBus, OTPSource.LINE_CHAT) still wins."""
    _drain_otp_queue()
    await event_bus.publish_otp(OTPPayload(otp="333333", ref="SMEG", source=OTPSource.LINE_CHAT))

    otp, source = await auth_driver._wait_for_otp_multi_channel(
        otp_timeout=3,
        wait_start_time=datetime.now(timezone.utc),
        otp_input_sel=None,
        channel=CHANNEL_LINE_DIRECT,
    )

    assert otp == "333333"
    assert source == "line_chat"
    _drain_otp_queue()
