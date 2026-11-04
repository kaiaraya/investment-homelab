# -*- coding: utf-8 -*-
"""Unit tests for LINE CLI /login Phase 2 integration with session daemon.

Verifies:
- /login wakes up session_daemon (ensure_daemon) instead of auth_driver.login
- force triggers restart_daemon
- /login zero-OTP attach when already authenticated and no daemon spawn
- concurrent lock protection between /login kss and /login all
"""
import asyncio
from unittest.mock import AsyncMock
import pytest

from app.services.line_cli import handlers
from tests.test_line_cli_flow import FakeService, ATTACHED_KSS, _patch_relay, _run, _text_of


@pytest.fixture
def service():
    return FakeService()


@pytest.fixture(autouse=True)
def _broker_edges(monkeypatch):
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=True))
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_detach_session_cdp", AsyncMock(return_value=False))
    monkeypatch.setattr(handlers, "_in_nego_window", lambda now=None: True)
    handlers._LOCKS.clear()
    handlers._STARTED.clear()


@pytest.mark.asyncio
async def test_login_wakes_daemon_when_not_attached(service, db_session, monkeypatch):
    """When attach returns None, ensure_daemon is called instead of legacy auth_driver."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    _patch_relay(monkeypatch, ready=True)

    from app.services.broker_cdp import daemon_launcher
    mock_ensure = AsyncMock(return_value={
        "status": "ready",
        "broker": "kss",
        "port": 9333,
        "pid": 999,
        "page_url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp",
        "state": "AUTHENTICATED",
    })
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    # Legacy auth_driver must NOT be called
    from app.browser.auth_driver import auth_driver
    mock_auth = AsyncMock()
    monkeypatch.setattr(auth_driver, "login", mock_auth)

    res = await _run(service, "/login kss", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    mock_ensure.assert_awaited_once_with("kss")
    mock_auth.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_force_restarts_daemon(service, db_session, monkeypatch):
    """Force flag triggers restart_daemon."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    _patch_relay(monkeypatch, ready=True)

    from app.services.broker_cdp import daemon_launcher
    mock_restart = AsyncMock(return_value={
        "status": "ready",
        "broker": "kss",
        "port": 9333,
        "pid": 1001,
        "page_url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp",
        "state": "AUTHENTICATED",
    })
    monkeypatch.setattr(daemon_launcher, "restart_daemon", mock_restart)

    res = await _run(service, "/login kss force", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    mock_restart.assert_awaited_once_with("kss")


@pytest.mark.asyncio
async def test_login_zero_otp_when_already_authenticated(service, db_session, monkeypatch):
    """When attach succeeds, no daemon launch or OTP needed."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=dict(ATTACHED_KSS)))
    from app.services.broker_cdp import daemon_launcher
    mock_ensure = AsyncMock()
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    res = await _run(service, "/login kss", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    assert res["results"][0]["status"] == "attached"
    mock_ensure.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_kss_and_login_all_mutual_lock(service, db_session):
    """Gate lock prevents concurrent /login kss and /login all."""
    gate_lock = handlers._lock_for("login", "gate")
    assert not gate_lock.locked()

    async with gate_lock:
        res = await _run(service, "/login kss", db=db_session)
        assert res.get("status") == "CLI_BUSY"
        assert "กำลังทำงานอยู่" in service.last_text()


@pytest.mark.asyncio
async def test_login_awaiting_otp_when_login_page_does_not_fail(service, db_session, monkeypatch):
    """When launcher returns LOGIN_PAGE or OTP_PAGE, handler reports awaiting OTP, NOT failed/❌."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    _patch_relay(monkeypatch, ready=True)

    from app.services.broker_cdp import daemon_launcher
    mock_ensure = AsyncMock(return_value={
        "status": "LOGIN_PAGE",
        "broker": "kss",
        "port": 9333,
        "pid": 999,
        "page_url": "https://auth.settrade.com/auth/login",
        "state": "LOGIN_PAGE",
        "log_tail": "Waiting for OTP confirmation...",
    })
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    res = await _run(service, "/login kss", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    assert res["results"][0]["status"] == "awaiting_otp"
    assert res["results"][0]["state"] == "LOGIN_PAGE"
    pushes = [_text_of(m) for m, _ in service.pushes]
    assert not any("❌" in p for p in pushes)
    assert any("กำลังรอ OTP" in p for p in pushes)


@pytest.mark.asyncio
async def test_login_lib_calls_ensure_daemon_lib(service, db_session, monkeypatch):
    """Handler path for /login lib routes to ensure_daemon with 'lib'."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    _patch_relay(monkeypatch, ready=True)

    from app.services.broker_cdp import daemon_launcher
    mock_ensure = AsyncMock(return_value={
        "status": "spawned",
        "broker": "liberator",
        "port": 9334,
        "pid": 1002,
        "page_url": "https://webtrade.liberator.co.th/portfolio",
        "state": "AUTHENTICATED",
    })
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    res = await _run(service, "/login lib", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    mock_ensure.assert_awaited_once_with("lib")
    assert res["results"][0]["status"] == "ok"


@pytest.mark.asyncio
async def test_login_daemon_down_fails_with_log_tail(service, db_session, monkeypatch):
    """When daemon is down / crashes, handler reports failure with 5-line log tail."""
    monkeypatch.setattr(handlers, "_attach_session_cdp", AsyncMock(return_value=None))
    monkeypatch.setattr(handlers, "_broker_session_alive", AsyncMock(return_value=False))
    _patch_relay(monkeypatch, ready=True)

    from app.services.broker_cdp import daemon_launcher
    mock_ensure = AsyncMock(return_value={
        "status": "crashed",
        "broker": "kss",
        "port": 9333,
        "pid": 999,
        "page_url": None,
        "state": "DAEMON_DOWN",
        "log_tail": "line1\nline2\nline3\nline4\nline5",
    })
    monkeypatch.setattr(daemon_launcher, "ensure_daemon", mock_ensure)

    res = await _run(service, "/login kss", db=db_session)

    assert res.get("status") == "CLI_LOGIN"
    assert res["results"][0]["status"] == "failed"
    assert res["results"][0]["state"] == "DAEMON_DOWN"
    pushes = [_text_of(m) for m, _ in service.pushes]
    assert any("❌" in p and "log tail" in p and "line5" in p for p in pushes)
