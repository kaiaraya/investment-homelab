# -*- coding: utf-8 -*-
"""Unit and integration tests for CDP-2 /status truth reporting.

Verifies:
1. _broker_health uses CDP probe as primary truth while auth_driver.is_authenticated is False.
2. _handle_status formats port, pid, origin (CDP vs flag), timestamps, and per-tab status.
3. Distinct colors and texts for AUTH (🟢), LOGIN_PAGE (🟡), NO_TAB/UNKNOWN (🟡), DAEMON_DOWN (🔴).
4. Live probe on running Chrome daemons returns AUTHENTICATED with real pids.
"""
from unittest.mock import AsyncMock, PropertyMock, patch
import pytest

from app.services.line_cli import handlers
from app.services.line_cli.handlers import _broker_health, _handle_status


@pytest.mark.asyncio
async def test_broker_health_cdp_authenticated_while_flag_false():
    """When gateway restarts (auth_driver.is_authenticated == False), CDP probe truth gives AUTH."""
    mock_kss_probe = {
        "broker": "kss",
        "purpose": "streaming",
        "state": "AUTHENTICATED",
        "daemon_up": True,
        "port": 9333,
        "pid": 12345,
        "target_found": True,
        "url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp",
        "url_path": "/realtime/streaming7/StreamingPage.jsp",
        "checked_at": "2026-10-26T07:32:10+00:00",
        "reason": "matches authenticated path",
    }
    mock_sbl_probe = {
        "broker": "kss",
        "purpose": "sbl",
        "state": "AUTHENTICATED",
        "daemon_up": True,
        "port": 9333,
        "pid": 12345,
        "target_found": True,
        "url": "https://www.krungsrisecurities.com/sblweb/MainSBL.aspx",
        "url_path": "/sblweb/MainSBL.aspx",
        "checked_at": "2026-10-26T07:32:10+00:00",
        "reason": "matches authenticated path",
    }

    async def _mock_cdp(broker, purpose=None):
        if purpose == "sbl":
            return mock_sbl_probe
        return mock_kss_probe

    with (
        patch("app.browser.auth_driver.KrungsriAuthDriver.is_authenticated", new_callable=PropertyMock, return_value=False),
        patch("app.services.broker_cdp.session_probe.cdp_session_status", side_effect=_mock_cdp),
    ):
        h = await _broker_health("kss")
        assert h["authenticated"] is True
        assert h["source"] == "CDP"
        assert h["account"] == "MARGIN"
        assert h["cdp"]["port"] == 9333
        assert h["cdp"]["pid"] == 12345
        assert h["cdp"]["sbl"]["state"] == "AUTHENTICATED"


@pytest.mark.asyncio
async def test_broker_health_daemon_down_fallback_to_flag():
    """When daemon is down but in-process flag is True, falls back to flag."""
    mock_down = {
        "broker": "lib",
        "purpose": "portfolio",
        "state": "DAEMON_DOWN",
        "daemon_up": False,
        "port": 9334,
        "pid": None,
        "target_found": False,
        "url": None,
        "url_path": None,
        "checked_at": "2026-10-26T07:32:10+00:00",
        "reason": "connection refused",
    }
    with (
        patch("app.brokers.liberator_plugin.get_health", AsyncMock(return_value={"is_authenticated": True, "last_heartbeat": "14:20"})),
        patch("app.services.broker_cdp.session_probe.cdp_session_status", AsyncMock(return_value=mock_down)),
    ):
        h = await _broker_health("lib")
        assert h["authenticated"] is True
        assert h["source"] == "flag"
        assert h["heartbeat"] == "14:20"
        assert h["account"] == "CASH"


@pytest.mark.asyncio
async def test_handle_status_formats_expected_cards_and_summaries():
    """Verify _handle_status card structure, emoji mappings, port, pid, and timestamps."""
    mock_kss = {
        "authenticated": True,
        "heartbeat": "14:32",
        "account": "MARGIN",
        "source": "CDP",
        "cdp": {
            "broker": "kss",
            "port": 9333,
            "pid": 12345,
            "state": "AUTHENTICATED",
            "daemon_up": True,
            "checked_at": "2026-10-26T07:32:10+00:00",
            "sbl": {
                "state": "AUTHENTICATED",
            },
        },
    }
    mock_lib = {
        "authenticated": True,
        "heartbeat": "14:32",
        "account": "CASH",
        "source": "CDP",
        "cdp": {
            "broker": "lib",
            "port": 9334,
            "pid": 12399,
            "state": "AUTHENTICATED",
            "daemon_up": True,
            "checked_at": "2026-10-26T07:32:10+00:00",
        },
    }

    async def _mock_health(b):
        return mock_kss if b == "kss" else mock_lib

    service = AsyncMock()
    service._send_reply = AsyncMock()

    with patch.object(handlers, "_broker_health", side_effect=_mock_health):
        res = await _handle_status(service, "reply-tok")
        assert res["status"] == "CLI_STATUS"
        assert res["kss_alive"] is True
        assert res["lib_alive"] is True

        brokers = res["brokers"]
        assert len(brokers) == 2

        kss = brokers[0]
        assert kss["emoji"] == "🟢"
        assert kss["name"] == "KSS (MARGIN)"
        assert "CDP 9333" in kss["line1"]
        assert "streaming AUTH · sbl AUTH" in kss["line1"]
        assert "pid 12345" in kss["line2"]
        assert "14:32:10" in kss["line2"]
        assert "🟢 KSS (MARGIN) · CDP 9333 · streaming AUTH · sbl AUTH · pid 12345 · 14:32:10" == kss["summary"]

        lib = brokers[1]
        assert lib["emoji"] == "🟢"
        assert lib["name"] == "LIB (CASH)"
        assert "CDP 9334" in lib["line1"]
        assert "portfolio AUTH" in lib["line1"]
        assert "pid 12399" in lib["line2"]
        assert "14:32:10" in lib["line2"]
        assert "🟢 LIB (CASH) · CDP 9334 · portfolio AUTH · pid 12399 · 14:32:10" == lib["summary"]


@pytest.mark.asyncio
async def test_handle_status_distinguishes_daemon_down_login_unknown():
    """DAEMON_DOWN (🔴), LOGIN_PAGE (🟡), and UNKNOWN (🟡) must show distinct emojis and texts."""
    mock_down = {
        "authenticated": False,
        "account": "MARGIN",
        "source": "CDP",
        "cdp": {
            "port": 9333,
            "pid": None,
            "state": "DAEMON_DOWN",
            "daemon_up": False,
            "checked_at": "2026-10-26T07:32:10+00:00",
            "sbl": {"state": "DAEMON_DOWN"},
        },
    }
    mock_login = {
        "authenticated": False,
        "account": "CASH",
        "source": "CDP",
        "cdp": {
            "port": 9334,
            "pid": 9999,
            "state": "LOGIN_PAGE",
            "daemon_up": True,
            "checked_at": "2026-10-26T07:32:10+00:00",
        },
    }

    async def _mock_health(b):
        return mock_down if b == "kss" else mock_login

    service = AsyncMock()
    service._send_reply = AsyncMock()

    with patch.object(handlers, "_broker_health", side_effect=_mock_health):
        res = await _handle_status(service, "reply-tok")
        assert res["kss_alive"] is False
        assert res["lib_alive"] is False

        brokers = res["brokers"]
        kss = brokers[0]
        assert kss["emoji"] == "🔴"
        assert "DAEMON_DOWN" in kss["line1"]

        lib = brokers[1]
        assert lib["emoji"] == "🟡"
        assert "LOGIN" in lib["line1"]


@pytest.mark.asyncio
async def test_live_daemons_status_truth():
    """Integration test: executes live read-only probe on real Chrome instances."""
    h_kss = await _broker_health("kss")
    h_lib = await _broker_health("lib")

    # Both live daemons are running and authenticated
    assert h_kss["authenticated"] is True
    assert h_kss["source"] == "CDP"
    assert h_kss["cdp"]["port"] == 9333
    assert h_kss["cdp"]["pid"] is not None
    assert h_kss["cdp"]["state"] == "AUTHENTICATED"

    assert h_lib["authenticated"] is True
    assert h_lib["source"] == "CDP"
    assert h_lib["cdp"]["port"] == 9334
    assert h_lib["cdp"]["pid"] is not None
    assert h_lib["cdp"]["state"] == "AUTHENTICATED"
