# -*- coding: utf-8 -*-
"""Unit tests for CDP session probe (read-only) and path contract.

Covers all 5 states: AUTHENTICATED, LOGIN_PAGE, NO_TARGET_TAB, DAEMON_DOWN, UNKNOWN
and asserts that probe execution is strictly read-only (zero goto/navigate calls).
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.broker_cdp.session_probe import cdp_session_status
from scripts.broker_cdp.brokers import AUTH_PATHS, LOGIN_MARKERS, is_authenticated_path


# ────────────────────────────────────────────────────────────────────────────
# 1. Path Contract & Helper Tests
# ────────────────────────────────────────────────────────────────────────────

def test_is_authenticated_path_kss_streaming():
    url = "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp"
    assert is_authenticated_path("kss", "streaming", url) is True


def test_is_authenticated_path_kss_sbl():
    url = "https://www.krungsrisecurities.com/sblweb/MainSBL.aspx"
    assert is_authenticated_path("kss", "sbl", url) is True


def test_is_authenticated_path_kss_member():
    url = "https://www.krungsrisecurities.com/th/member/CreditBalance_Announcement.aspx"
    assert is_authenticated_path("kss", "member", url) is True


def test_is_authenticated_path_liberator():
    for sub in ["Market", "Portfolio", "Trade"]:
        url = f"https://webtrade.liberator.co.th/{sub}"
        assert is_authenticated_path("lib", "portfolio", url) is True
        assert is_authenticated_path("liberator", "portfolio", url) is True


def test_is_authenticated_path_rejects_login_markers():
    # Rejection happens before path matching
    trap_urls = [
        "https://webtrade.liberator.co.th/login",
        "https://webtrade.liberator.co.th/otp",
        "https://wen075.settrade.com/twofa",
        "https://www.krungsrisecurities.com/Login.aspx",
        "https://www.krungsrisecurities.com/th/member/login.aspx",
        "https://www.krungsrisecurities.com/th/member/login",
        "https://auth.settrade.com/auth/login",
        "https://webtrade.liberator.co.th/signin",
    ]
    for url in trap_urls:
        assert is_authenticated_path("lib", "portfolio", url) is False
        assert is_authenticated_path("kss", "streaming", url) is False
        assert is_authenticated_path("kss", "member", url) is False


def test_is_authenticated_path_rejects_bare_root_and_empty():
    assert is_authenticated_path("kss", "streaming", "") is False
    assert is_authenticated_path("kss", "streaming", "https://wme2.settrade.com") is False
    assert is_authenticated_path("kss", "streaming", "https://wme2.settrade.com/") is False
    assert is_authenticated_path("lib", "portfolio", "https://webtrade.liberator.co.th/") is False


def test_is_authenticated_path_rejects_substring_host_traps():
    # "trade" in "webtrade.liberator.co.th" must not fool path checking
    assert is_authenticated_path("lib", "portfolio", "https://webtrade.liberator.co.th/unknown") is False


# ────────────────────────────────────────────────────────────────────────────
# 2. Probe 5 States Tests
# ────────────────────────────────────────────────────────────────────────────

def _create_mock_page(url: str):
    page = MagicMock()
    page.url = url
    page.title = AsyncMock(return_value="Page Title")
    page.goto = MagicMock()
    page.evaluate = AsyncMock(return_value={})
    return page


@pytest.mark.asyncio
async def test_probe_state_daemon_down():
    # When is_cdp_available returns False, returns DAEMON_DOWN without raising
    with patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=False):
        status = await cdp_session_status("kss")
        assert status["state"] == "DAEMON_DOWN"
        assert status["daemon_up"] is False
        assert status["target_found"] is False
        assert status["broker"] == "kss"
        assert status["purpose"] == "streaming"
        assert status["port"] == 9333


@pytest.mark.asyncio
async def test_probe_state_daemon_down_connection_error():
    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", side_effect=ConnectionError("Refused")),
    ):
        status = await cdp_session_status("lib")
        assert status["state"] == "DAEMON_DOWN"
        assert status["daemon_up"] is False
        assert status["target_found"] is False
        assert status["port"] == 9334


@pytest.mark.asyncio
async def test_probe_state_no_target_tab():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()

    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
        patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=None),
    ):
        status = await cdp_session_status("kss")
        assert status["state"] == "NO_TARGET_TAB"
        assert status["daemon_up"] is True
        assert status["target_found"] is False
        assert pw_mock.stop.call_count == 1


@pytest.mark.asyncio
async def test_probe_state_no_target_tab_empty_blank():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()
    page_mock = _create_mock_page("about:blank")

    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
        patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=page_mock),
    ):
        status = await cdp_session_status("lib")
        assert status["state"] == "NO_TARGET_TAB"
        assert status["daemon_up"] is True
        assert status["target_found"] is False
        page_mock.goto.assert_not_called()


@pytest.mark.asyncio
async def test_probe_state_login_page():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()
    page_mock = _create_mock_page("https://webtrade.liberator.co.th/login")

    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
        patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=page_mock),
    ):
        status = await cdp_session_status("lib", "portfolio")
        assert status["state"] == "LOGIN_PAGE"
        assert status["daemon_up"] is True
        assert status["target_found"] is True
        assert status["url"] == "https://webtrade.liberator.co.th/login"
        assert status["url_path"] == "/login"
        page_mock.goto.assert_not_called()


@pytest.mark.asyncio
async def test_probe_state_authenticated():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()
    page_mock = _create_mock_page("https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp")

    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
        patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=page_mock),
    ):
        status = await cdp_session_status("kss", "streaming")
        assert status["state"] == "AUTHENTICATED"
        assert status["daemon_up"] is True
        assert status["target_found"] is True
        assert status["url_path"] == "/realtime/streaming7/StreamingPage.jsp"
        page_mock.goto.assert_not_called()


@pytest.mark.asyncio
async def test_probe_state_unknown():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()
    page_mock = _create_mock_page("https://www.krungsrisecurities.com/maintenance.html")

    with (
        patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
        patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
        patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=page_mock),
    ):
        status = await cdp_session_status("kss", "streaming")
        assert status["state"] == "UNKNOWN"
        assert status["daemon_up"] is True
        assert status["target_found"] is True
        page_mock.goto.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# 3. Read-Only Enforcement (Assert NO goto / navigation called across all runs)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_only_strictly_no_goto():
    pw_mock = MagicMock()
    pw_mock.stop = AsyncMock()
    ctx_mock = MagicMock()

    test_cases = [
        ("kss", "streaming", "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp"),
        ("kss", "sbl", "https://www.krungsrisecurities.com/sblweb/MainSBL.aspx"),
        ("lib", "portfolio", "https://webtrade.liberator.co.th/Market"),
        ("lib", "portfolio", "https://webtrade.liberator.co.th/login"),
        ("kss", "streaming", "https://some-unrelated-site.com/foo"),
    ]

    for broker, purpose, url in test_cases:
        page_mock = _create_mock_page(url)
        with (
            patch("app.services.broker_cdp.session_probe.is_cdp_available", return_value=True),
            patch("app.services.broker_cdp.session_probe.connect_cdp", return_value=(pw_mock, None, ctx_mock)),
            patch("app.services.broker_cdp.session_probe.resolve_target_tab", return_value=page_mock),
        ):
            await cdp_session_status(broker, purpose)
            page_mock.goto.assert_not_called()
            assert not hasattr(page_mock, "navigate") or page_mock.navigate.call_count == 0
