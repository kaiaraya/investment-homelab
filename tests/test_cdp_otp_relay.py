# -*- coding: utf-8 -*-
"""Tests for scripts/broker_cdp/otp_relay.py — LINE OTP relay (แบบเดิม) in the CDP path."""
import asyncio

import pytest

from scripts.broker_cdp import otp_relay
from scripts.broker_cdp.otp_relay import (
    OTP_SESSION_LOG_PATTERN,
    OtpMatch,
    check_line_otp_once,
)

VALID_UID = "U" + "a" * 32


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


def test_repair_line_uid_restores_malformed_value_from_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(f'LINE_ADMIN_USER_ID="{VALID_UID}"\n', encoding="utf-8")
    monkeypatch.setattr(otp_relay, "_REPO_ROOT", str(tmp_path))

    from app.core.config import settings

    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_OP", raising=False)
    otp_relay._repair_line_uid()
    assert settings.LINE_ADMIN_USER_ID == VALID_UID


def test_repair_line_uid_leaves_valid_value_alone(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('LINE_ADMIN_USER_ID="Udeadbeef"\n', encoding="utf-8")
    monkeypatch.setattr(otp_relay, "_REPO_ROOT", str(tmp_path))

    from app.core.config import settings

    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", VALID_UID, raising=False)
    otp_relay._repair_line_uid()
    assert settings.LINE_ADMIN_USER_ID == VALID_UID


# ────────────────────────────────────────────────────────────────────────────
# _fill_otp_input & submit button drift guard tests (t_0e05fe62)
# ────────────────────────────────────────────────────────────────────────────

class FakeElement:
    def __init__(self, visible: bool = True):
        self.visible = visible
        self.filled = None
        self.clicked = False

    async def is_visible(self) -> bool:
        return self.visible

    async def fill(self, val: str) -> None:
        self.filled = val

    async def click(self) -> None:
        self.clicked = True


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    def __init__(self, elements=None):
        self.elements = elements or {}
        self.keyboard = FakeKeyboard()

    async def query_selector(self, sel: str):
        return self.elements.get(sel)


@pytest.mark.asyncio
async def test_fill_otp_input_clicks_btn_confirm():
    from scripts.broker_cdp.brokers import _fill_otp_input

    otp_input = FakeElement()
    btn_confirm = FakeElement()
    page = FakePage({
        "#otp": otp_input,
        "input#btnConfirm": btn_confirm,
    })

    res = await _fill_otp_input(page, "#otp", "123456")
    assert res is True
    assert otp_input.filled == "123456"
    assert btn_confirm.clicked is True
    assert page.keyboard.pressed == []


@pytest.mark.asyncio
async def test_fill_otp_input_fallback_enter_when_no_button():
    from scripts.broker_cdp.brokers import _fill_otp_input

    otp_input = FakeElement()
    page = FakePage({"#otp": otp_input})

    res = await _fill_otp_input(page, "#otp", "654321")
    assert res is True
    assert otp_input.filled == "654321"
    assert page.keyboard.pressed == ["Enter"]


@pytest.mark.asyncio
async def test_fill_otp_input_returns_false_if_input_missing():
    from scripts.broker_cdp.brokers import _fill_otp_input

    page = FakePage({})
    res = await _fill_otp_input(page, "#missing", "123456")
    assert res is False
    assert page.keyboard.pressed == []


def test_otp_submit_selectors_drift_guard():
    from scripts.broker_cdp.brokers import OTP_SUBMIT_SELECTORS as BROKER_SELECTORS
    from app.browser.auth_driver import OTP_SUBMIT_SELECTORS as AUTH_SELECTORS

    assert BROKER_SELECTORS == AUTH_SELECTORS
    assert "input#btnConfirm" in BROKER_SELECTORS
    assert "input#btnSubmit" in BROKER_SELECTORS
    assert "button:has-text('ยืนยัน')" in BROKER_SELECTORS
