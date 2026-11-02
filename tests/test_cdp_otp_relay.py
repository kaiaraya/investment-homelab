# -*- coding: utf-8 -*-
"""Tests for scripts/broker_cdp/otp_relay.py — LINE OTP relay (แบบเดิม) in the CDP path."""
import asyncio

import pytest

from scripts.broker_cdp.otp_relay import (
    OTP_SESSION_LOG_PATTERN,
    OtpMatch,
    check_line_otp_once,
)


class _FakeRow:
    def __init__(self, details, row_id):
        self.details = details
        self.id = row_id


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, captured=None):
        self._rows = rows
        self._captured = captured if captured is not None else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self._captured["stmt"] = stmt
        return _FakeResult(self._rows)


@pytest.fixture
def fake_session_factory(monkeypatch):
    """Patch AsyncSessionLocal; returns (make, captured) with the last SELECT."""
    captured: dict = {}

    def make(rows):
        def factory():
            return _FakeSession(rows, captured)

        monkeypatch.setattr(
            "scripts.broker_cdp.otp_relay.AsyncSessionLocal", factory
        )
        return captured

    return make


def test_otp_regex_matches_line_row():
    m = OTP_SESSION_LOG_PATTERN.search(
        "Received OTP 6-digits from LINE: 922412 (Ref: N/A) (Broker: KRUNGSRI)"
    )
    assert m and m.group(1) == "922412"


def test_check_line_otp_once_returns_match_for_matching_broker(fake_session_factory):
    fake_session_factory(
        [_FakeRow("Received OTP 6-digits from LINE: 111222 (Ref: N/A) (Broker: KRUNGSRI)", 77)]
    )
    match = asyncio.run(check_line_otp_once("KRUNGSRI"))
    assert match == OtpMatch(otp="111222", row_id=77)


def test_check_line_otp_once_ignores_other_broker(fake_session_factory):
    fake_session_factory(
        [_FakeRow("Received OTP 6-digits from LINE: 333444 (Ref: N/A) (Broker: LIBERATOR)", 78)]
    )
    assert asyncio.run(check_line_otp_once("KRUNGSRI")) is None


def test_check_line_otp_once_returns_none_when_empty(fake_session_factory):
    fake_session_factory([])
    assert asyncio.run(check_line_otp_once("KRUNGSRI")) is None


def test_poll_is_watermarked_to_avoid_stale_otp(fake_session_factory):
    """Stale rows (a code from an earlier login/test) must be filtered in SQL,
    otherwise the loop re-types an old code into a fresh OTP form."""
    captured = fake_session_factory([])
    asyncio.run(check_line_otp_once("KRUNGSRI", since_id=4242))
    sql = str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))
    assert "session_logs.id > 4242" in sql, sql
    assert "LINE_OTP_RECEIVED" in sql
