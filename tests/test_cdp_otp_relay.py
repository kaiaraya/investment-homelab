# -*- coding: utf-8 -*-
"""Tests for scripts/broker_cdp/otp_relay.py — LINE OTP relay (แบบเดิม) in the CDP path."""
import asyncio

import pytest

from scripts.broker_cdp.otp_relay import OTP_SESSION_LOG_PATTERN, check_line_otp_once


class _FakeRow:
    def __init__(self, details):
        self.details = details


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        return _FakeResult(self._rows)


@pytest.fixture
def fake_session_factory(monkeypatch):
    def make(rows):
        def factory():
            return _FakeSession(rows)

        monkeypatch.setattr(
            "scripts.broker_cdp.otp_relay.AsyncSessionLocal", factory
        )

    return make


def test_otp_regex_matches_line_row():
    m = OTP_SESSION_LOG_PATTERN.search(
        "Received OTP 6-digits from LINE: 922412 (Ref: N/A) (Broker: KRUNGSRI)"
    )
    assert m and m.group(1) == "922412"


def test_check_line_otp_once_returns_otp_for_matching_broker(fake_session_factory):
    fake_session_factory(
        [_FakeRow("Received OTP 6-digits from LINE: 111222 (Ref: N/A) (Broker: KRUNGSRI)")]
    )
    otp = asyncio.run(check_line_otp_once("KRUNGSRI"))
    assert otp == "111222"


def test_check_line_otp_once_ignores_other_broker(fake_session_factory):
    fake_session_factory(
        [_FakeRow("Received OTP 6-digits from LINE: 333444 (Ref: N/A) (Broker: LIBERATOR)")]
    )
    otp = asyncio.run(check_line_otp_once("KRUNGSRI"))
    assert otp is None


def test_check_line_otp_once_returns_none_when_empty(fake_session_factory):
    fake_session_factory([])
    assert asyncio.run(check_line_otp_once("KRUNGSRI")) is None
