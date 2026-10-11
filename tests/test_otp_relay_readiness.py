"""
OTP relay readiness gate + session-log OTP extraction tests (2026-10-08)

Covers Invariant 9 (LINE variant):
  * gate reports NOT ready when the LINE group is unconfigured / mocked / gateway down
  * gate reports ready when LINE group + gateway are live (channel = line_group)
  * LINE-RCA-007: gate reports NOT ready when the configured target is *undeliverable*
    (bot left the group → group/summary 404), and falls back to the 1:1 chat when that
    target is reachable — never a false-GO
  * OTP_SESSION_LOG_PATTERN matches the real `session_logs.details` rows (LINE-RCA-002)
"""

import re

import pytest

from app.browser.auth_driver import OTP_SESSION_LOG_PATTERN
from app.core.config import settings
from app.services.otp_relay_readiness import (
    CHANNEL_LINE_DIRECT,
    CHANNEL_LINE_GROUP,
    CHANNEL_NONE,
    _probe_target,
    otp_relay_readiness,
)


def _stub_probe(monkeypatch, unreachable=None):
    """
    Pin the LINE-RCA-007 deliverability probe (`_probe_target`).

    Any target id in `unreachable` answers like a bot that is no longer in the group:
    HTTP 404 "Not found" — every other target is reported reachable.
    """
    bad = set(unreachable or ())

    async def _probe(target_id, token, timeout=6.0):
        if target_id in bad:
            return False, 'HTTP 404: {"message":"Not found"}'
        return True, "reachable (stubbed)"

    monkeypatch.setattr("app.services.otp_relay_readiness._probe_target", _probe)
    return _probe


@pytest.fixture
def line_ready_env(monkeypatch):
    """LINE group relay fully configured; gateway probe + target probe stubbed to UP."""
    monkeypatch.setattr(settings, "LINE_OTP_RELAY_ENABLED", True)
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "live_token_abc")
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_group_abc")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: True)
    _stub_probe(monkeypatch)


@pytest.mark.asyncio
async def test_gate_ready_with_line_group_and_gateway(line_ready_env):
    result = await otp_relay_readiness.check()
    assert result.ready is True
    assert result.channel == CHANNEL_LINE_GROUP
    assert result.details["line_group_id_configured"] is True
    assert result.details["line_group_reachable"] is True
    assert result.details["gateway_up"] is True
    assert await otp_relay_readiness.is_ready() is True


@pytest.mark.asyncio
async def test_gate_blocked_when_group_target_undeliverable(monkeypatch):
    """
    LINE-RCA-007 (live proof 2026-10-08): `.env` held a well-formed groupId whose bot had
    already left the group → `group/summary` = 404 and push = "Failed to send messages".
    The gate must NOT report ready in that state (no false-GO → no wasted SMS OTP).
    """
    monkeypatch.setattr(settings, "LINE_OTP_RELAY_ENABLED", True)
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "live_token_abc")
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "Ccd_stale_group")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: True)
    _stub_probe(monkeypatch, unreachable={"Ccd_stale_group"})

    result = await otp_relay_readiness.check()

    assert result.ready is False
    assert result.channel == CHANNEL_NONE
    assert "not deliverable" in result.reason
    assert "404" in result.reason
    assert result.details["line_group_reachable"] is False


@pytest.mark.asyncio
async def test_gate_stays_closed_when_group_undeliverable_even_with_direct_id(monkeypatch):
    """
    Fail-closed (LINE-RCA-007): a *configured but undeliverable* group keeps the gate shut
    even when a 1:1 id exists — `line_service.push_message` still targets LINE_GROUP_ID
    first, so opening the gate here would be a false-GO (OTP pushed to nowhere).
    """
    monkeypatch.setattr(settings, "LINE_OTP_RELAY_ENABLED", True)
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "live_token_abc")
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "Ccd_stale_group")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_admin_direct")
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: True)
    _stub_probe(monkeypatch, unreachable={"Ccd_stale_group"})

    result = await otp_relay_readiness.check()

    assert result.ready is False
    assert result.channel == CHANNEL_NONE
    assert result.details["line_group_reachable"] is False
    assert result.details["line_direct_reachable"] is None  # never probed: group wins
    assert "LINE_GROUP_ID" in result.reason  # actionable fix is spelled out


@pytest.mark.asyncio
async def test_probe_target_selects_endpoint_by_id_prefix(monkeypatch):
    """`_probe_target` must query the endpoint that matches the id kind (C / R / U)."""
    seen = {}

    class _Resp:
        status_code = 200
        text = "{}"

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            seen["url"] = url
            seen["auth"] = (headers or {}).get("Authorization")
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    for target, expected in (
        ("C123", "https://api.line.me/v2/bot/group/C123/summary"),
        ("R123", "https://api.line.me/v2/bot/room/R123/summary"),
        ("U123", "https://api.line.me/v2/bot/profile/U123"),
    ):
        ok, detail = await _probe_target(target, "tok")
        assert (ok, detail) == (True, "reachable")
        assert seen["url"] == expected
        assert seen["auth"] == "Bearer tok"

    assert await _probe_target("", "tok") == (False, "target not set")


@pytest.mark.asyncio
async def test_gate_not_ready_without_any_push_target(line_ready_env, monkeypatch):
    """
    LINE-RCA-006: neither a group nor a 1:1 target is set -> the relay cannot push OTP
    anywhere, so the gate must stay closed (Invariant 9: no SMS OTP in that state).
    """
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert result.channel == CHANNEL_NONE
    assert "LINE_GROUP_ID" in result.reason
    assert "LINE_ADMIN_USER_ID" in result.reason
    assert result.details["line_target_kind"] is None


@pytest.mark.asyncio
async def test_gate_ready_with_direct_user_id_when_group_missing(line_ready_env, monkeypatch):
    """
    LINE-RCA-006 (Path B): without a LINE group (bot not invitable — LINE-RCA-005) the
    1:1 bot chat is a valid OTP target. `LINE_ADMIN_USER_ID` must open the gate as
    channel `line_direct`.
    """
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_operator_1to1")
    result = await otp_relay_readiness.check()
    assert result.ready is True
    assert result.channel == CHANNEL_LINE_DIRECT
    assert result.details["line_direct_id_configured"] is True
    assert result.details["line_target_kind"] == "direct"
    assert result.details["gateway_up"] is True


@pytest.mark.asyncio
async def test_gate_prefers_group_over_direct(line_ready_env, monkeypatch):
    """Zero-Contradiction: when both targets exist the group always wins."""
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_group_abc")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_operator_1to1")
    result = await otp_relay_readiness.check()
    assert result.ready is True
    assert result.channel == CHANNEL_LINE_GROUP
    assert result.details["line_target_kind"] == "group"


@pytest.mark.asyncio
async def test_gate_direct_target_still_needs_gateway(line_ready_env, monkeypatch):
    """Invariant 9 holds for the 1:1 channel too: no gateway -> cannot receive OTP."""
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", "U_operator_1to1")
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: False)
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert "gateway is DOWN" in result.reason


@pytest.mark.asyncio
async def test_gate_not_ready_when_gateway_down(line_ready_env, monkeypatch):
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: False)
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert "gateway is DOWN" in result.reason


@pytest.mark.asyncio
async def test_gate_not_ready_in_simulation_mode(line_ready_env, monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", True)
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert "SIMULATION_MODE" in result.reason


@pytest.mark.asyncio
async def test_gate_not_ready_when_relay_disabled(line_ready_env, monkeypatch):
    monkeypatch.setattr(settings, "LINE_OTP_RELAY_ENABLED", False)
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert "disabled" in result.reason


@pytest.mark.asyncio
async def test_gate_not_ready_with_mock_token(line_ready_env, monkeypatch):
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "mock_line_channel_token")
    result = await otp_relay_readiness.check()
    assert result.ready is False
    assert "mock" in result.reason


@pytest.mark.asyncio
async def test_gate_can_skip_gateway_probe(line_ready_env, monkeypatch):
    """require_gateway=False must pass even when nothing listens on :8000."""
    monkeypatch.setattr("app.services.otp_relay_readiness._port_open", lambda *a, **k: False)
    result = await otp_relay_readiness.check(require_gateway=False)
    assert result.ready is True
    assert result.channel == CHANNEL_LINE_GROUP


def test_otp_pattern_matches_line_session_log_row():
    """LINE-RCA-002: the row the LINE relay actually writes must be parseable."""
    details = "Received OTP 6-digits from LINE: 849201 (Ref: BIPE)"
    match = re.search(OTP_SESSION_LOG_PATTERN, details)
    assert match is not None
    assert match.group(1) == "849201"


def test_otp_pattern_matches_kde_session_log_row():
    details = "Received SMS OTP: 123456"
    match = re.search(OTP_SESSION_LOG_PATTERN, details)
    assert match is not None
    assert match.group(1) == "123456"


def test_otp_pattern_ignores_non_otp_details():
    assert re.search(OTP_SESSION_LOG_PATTERN, "Awaiting 2FA SMS OTP. Ref: BIPE") is None
