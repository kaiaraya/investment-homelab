"""
LINE Group OTP relay — unit tests (2026-10-08)

Covers:
  * push_message() target resolution (group → admin → broadcast)
  * push_otp_request() message content + group targeting
"""

import pytest

from app.core.config import settings
from app.services.line_service import line_service


class _FakeResp:
    status_code = 200
    text = "ok"


class _FakeClient:
    """Captures the payload instead of hitting api.line.me."""

    last: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeClient.last = {"url": url, "headers": headers, "json": json}
        return _FakeResp()


@pytest.fixture
def live_line(monkeypatch):
    """Force live (non-simulation) LINE mode with a stubbed transport."""
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", False)
    monkeypatch.setattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "live_token_abc")
    monkeypatch.setattr("app.services.line_service.httpx.AsyncClient", _FakeClient)
    _FakeClient.last = {}
    return _FakeClient


@pytest.mark.asyncio
async def test_push_message_targets_group(live_line, monkeypatch):
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_group_abc")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)

    ok = await line_service.push_message("hello a14s homelab")

    assert ok is True
    assert live_line.last["url"].endswith("/v2/bot/message/push")
    assert live_line.last["json"]["to"] == "C_group_abc"


@pytest.mark.asyncio
async def test_push_message_falls_back_to_broadcast(live_line, monkeypatch):
    monkeypatch.setattr(settings, "LINE_GROUP_ID", None)
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)

    ok = await line_service.push_message("nobody configured")

    assert ok is True
    assert live_line.last["url"].endswith("/v2/bot/message/broadcast")
    assert "to" not in live_line.last["json"]


@pytest.mark.asyncio
async def test_push_otp_request_targets_group_with_ref(live_line, monkeypatch):
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_group_abc")
    monkeypatch.setattr(settings, "LINE_ADMIN_USER_ID", None)

    ok = await line_service.push_otp_request(
        ref="BIPE", broker="LIBERATOR", timeout_seconds=180
    )

    assert ok is True
    assert live_line.last["json"]["to"] == "C_group_abc"
    text = live_line.last["json"]["messages"][0]["text"]
    assert "2FA OTP REQUIRED" in text
    assert "BIPE" in text
    assert "Liberator WebTrade" in text
    assert "180" in text


@pytest.mark.asyncio
async def test_push_otp_request_simulation_returns_true(monkeypatch):
    monkeypatch.setattr(settings, "LINE_SIMULATION_MODE", True)
    monkeypatch.setattr(settings, "LINE_GROUP_ID", "C_group_abc")

    assert await line_service.push_otp_request(ref=None, broker="KRUNGSRI") is True
