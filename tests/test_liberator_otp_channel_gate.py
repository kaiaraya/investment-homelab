"""
LINE-RCA-009 (Gate B) — Liberator must obey the authoritative OTP channel.
=========================================================================

Before this change `LiberatorDriver.login()` had two problems:

  1. **No relay-readiness gate.** A fresh login fired a real broker SMS OTP even
     when nothing could capture it (relay not ready) -> unreadable OTP, 180s stall,
     account-lock risk (Invariant 9 — LINE variant).
  2. **No channel gating / no honest attribution.** Its 180s wait loop polled KDE
     Connect *ungated* and never reported which path actually supplied the OTP, so
     while LINE was supposed to be authoritative the dormant KDE fallback could
     silently win the race (the exact bug class LINE-RCA-009 fixed in auth_driver).

These tests drive the real `login()` against a stubbed page, so the policy is proven
behaviourally instead of by inspecting source text (Anti-Mock / real evidence).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.brokers.liberator.driver import LiberatorDriver, _safe_otp_source
from app.core.events import event_bus
from app.db.models import SessionLog
from app.schemas.auth import AuthStatus, OTPSource
from app.services.otp_relay_readiness import (
    CHANNEL_LINE_DIRECT,
    OtpRelayReadiness,
    otp_relay_readiness,
)


# ------------------------------------------------------------------ test doubles

# The confirm button selector used by `login()` after the OTP is captured (exact string).
_CONFIRM_SELECTOR = "button:has-text('ยืนยัน'), button[type='submit']"


def _drain_otp_queue() -> None:
    """The queue is a process-wide singleton — never let a stale item drive a test."""
    while not event_bus.otp_queue.empty():
        event_bus.otp_queue.get_nowait()


class _FakeEl:
    """Minimal Playwright element stand-in (visible + interactive)."""

    def __init__(self) -> None:
        self.fill = AsyncMock()
        self.click = AsyncMock()
        self.evaluate = AsyncMock(return_value=None)

    async def is_visible(self) -> bool:
        return True

    async def input_value(self) -> str:
        return ""


class _FakePage:
    """Minimal Playwright page stand-in for the Liberator login flow."""

    def __init__(self) -> None:
        self.dashboard = False
        self.goto = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.inner_text = AsyncMock(return_value="รหัส OTP (ref. code: SMEG)")
        self.evaluate = AsyncMock(return_value=None)
        self.keyboard = AsyncMock()

    @property
    def url(self) -> str:
        if self.dashboard:
            return "https://webtrade.liberator.co.th/Market"
        return "https://webtrade.liberator.co.th/login/otp"

    def is_closed(self) -> bool:
        return False

    async def query_selector(self, selector):
        if selector == _CONFIRM_SELECTOR:
            el = _FakeEl()

            async def _click(*_a, **_k):
                # Submitting the OTP lands on the dashboard -> lets login() finish.
                self.dashboard = True

            el.click = AsyncMock(side_effect=_click)
            return el
        return _FakeEl()


class _FakeContext:
    async def cookies(self):
        return []


def _ready_line_direct() -> OtpRelayReadiness:
    return OtpRelayReadiness(
        ready=True,
        channel=CHANNEL_LINE_DIRECT,
        reason="LINE 1:1 chat ready (userId U93d…)",
    )


def _fresh_driver(tmp_path) -> LiberatorDriver:
    """A driver whose session file does not exist -> the fresh-login path is taken."""
    drv = LiberatorDriver()
    drv.session_path = str(tmp_path / "missing_liberator_session.json")
    return drv


# ----------------------------------------------------- attribution helper (line 1)

def test_safe_otp_source_never_invents_a_channel():
    """Unmapped / absent capture tags must report 'unknown', never a guess."""
    assert _safe_otp_source(None) is None
    assert _safe_otp_source("") is None
    assert _safe_otp_source("line_chat") == OTPSource.LINE_CHAT
    assert _safe_otp_source("kdeconnect_sms") == OTPSource.KDE_CONNECT
    assert _safe_otp_source("browser_dom_manual") == OTPSource.BROWSER_DOM
    assert _safe_otp_source("totally-unknown-tag") is None


# ------------------------------------- relay gate BEFORE the SMS (line 2)

@pytest.mark.asyncio
async def test_liberator_login_aborts_before_sms_when_relay_not_ready(monkeypatch, tmp_path):
    """Relay not ready => BRIDGE_DOWN, browser never launched, no SMS OTP triggered."""
    check = AsyncMock(return_value=OtpRelayReadiness(
        ready=False,
        channel="none",
        reason="LINE push target missing",
    ))
    monkeypatch.setattr(otp_relay_readiness, "check", check)

    drv = _fresh_driver(tmp_path)
    launch = AsyncMock()
    drv.launch_browser = launch

    res = await drv.login(username="7055938", password="not-a-real-password")

    assert res.success is False
    assert res.status == AuthStatus.BRIDGE_DOWN
    assert res.error_code == "BRIDGE_DOWN"
    assert "SMS OTP was NOT triggered" in (res.message or "")
    assert drv.status == "BRIDGE_DOWN"
    # no browser -> no credentials submitted -> the broker never issues an SMS
    launch.assert_not_awaited()
    # LINE is authoritative: the dormant KDE fallback must NOT be allowed to satisfy the gate
    assert check.await_args.kwargs.get("allow_kde_fallback") is False


# -------------------------------- LINE channel capture + honest attribution (line 3)

@pytest.mark.asyncio
async def test_liberator_line_channel_captures_line_row_and_never_polls_kde(
    monkeypatch, db_session, tmp_path
):
    """A `LINE_OTP_RECEIVED` row satisfies the LINE channel; KDE is never polled."""
    from app.services.kdeconnect_service import kdeconnect_service
    from app.services.line_service import line_service

    _drain_otp_queue()
    monkeypatch.setattr(otp_relay_readiness, "check", AsyncMock(return_value=_ready_line_direct()))

    async def _fake_push(ref=None, broker="KRUNGSRI", timeout_seconds=None, notes=None):
        """The real sequence: the push asks the operator, whose LINE reply is logged
        afterwards by the webhook — so the row must be created AFTER the wait began."""
        db_session.add(SessionLog(
            event_type="LINE_OTP_RECEIVED",
            details="Received OTP 6-digits from LINE: 654321 (Ref: SMEG)",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=2),
        ))
        await db_session.commit()
        return True

    monkeypatch.setattr(line_service, "push_otp_request", AsyncMock(side_effect=_fake_push))

    kde_poll = AsyncMock(return_value=None)
    monkeypatch.setattr(kdeconnect_service, "poll_active_notifications", kde_poll)

    drv = _fresh_driver(tmp_path)
    drv.launch_browser = AsyncMock()
    drv.page = _FakePage()
    drv.context = _FakeContext()

    res = await drv.login(username="7055938", password="not-a-real-password")

    assert res.success is True, res.message
    assert res.status == AuthStatus.AUTHENTICATED
    assert res.otp_ref == "SMEG"
    # Honest attribution: the code really came through the LINE relay
    assert res.otp_source == OTPSource.LINE_CHAT
    assert res["otp_source"] == "line_chat"
    # The dormant fallback stayed dormant (this IS the LINE-RCA-009 regression)
    kde_poll.assert_not_awaited()
