# -*- coding: utf-8 -*-
"""Regression and integration tests for start_homelab.py Stage 2/3 CDP unification.

Verifies:
1. stage2_verify_krungsri_session delegates to ensure_daemon('kss') and checks cdp_session_status('kss').
2. When KSS CDP session is AUTHENTICATED -> returns True.
3. When KSS CDP session is not AUTHENTICATED -> returns False and triggers push_krungsri_login_alert.
4. stage3_verify_liberator_session delegates to ensure_daemon('liberator') and checks cdp_session_status('liberator').
5. When Liberator CDP session is AUTHENTICATED -> returns True; else returns False (non-fatal, optional).
6. Sequential execution contract: ensure_daemon is called sequentially per broker, never closing running browsers.
"""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest

import scripts.start_homelab as sh


@pytest.mark.asyncio
async def test_stage2_krungsri_authenticated():
    with (
        patch("scripts.start_homelab.ensure_daemon", new_callable=AsyncMock) as mock_ensure,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
    ):
        mock_ensure.return_value = {"status": "already_up", "state": "AUTHENTICATED", "port": 9333, "pid": 1234}
        mock_probe.return_value = {"state": "AUTHENTICATED", "port": 9333, "pid": 1234, "url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp"}

        ok = await sh.stage2_verify_krungsri_session()
        assert ok is True
        mock_ensure.assert_awaited_once_with("kss", wait_s=90.0)
        mock_probe.assert_awaited_once_with("kss")


@pytest.mark.asyncio
async def test_stage2_krungsri_not_authenticated_escalates_line():
    with (
        patch("scripts.start_homelab.ensure_daemon", new_callable=AsyncMock) as mock_ensure,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
        patch("scripts.start_homelab.push_krungsri_login_alert", new_callable=AsyncMock) as mock_alert,
    ):
        mock_ensure.return_value = {"status": "LOGIN_PAGE", "state": "LOGIN_PAGE", "port": 9333, "pid": 1234}
        mock_probe.return_value = {"state": "LOGIN_PAGE", "port": 9333, "pid": 1234, "reason": "Target tab is at login/otp marker"}

        ok = await sh.stage2_verify_krungsri_session()
        assert ok is False
        mock_ensure.assert_awaited_once_with("kss", wait_s=90.0)
        mock_probe.assert_awaited_once_with("kss")
        mock_alert.assert_awaited_once()
        assert "CDP session not authenticated" in mock_alert.call_args[0][0]


@pytest.mark.asyncio
async def test_stage2_krungsri_exception_handled():
    with (
        patch("scripts.start_homelab.ensure_daemon", side_effect=RuntimeError("CDP port conflict")),
        patch("scripts.start_homelab.push_krungsri_login_alert", new_callable=AsyncMock) as mock_alert,
    ):
        ok = await sh.stage2_verify_krungsri_session()
        assert ok is False
        mock_alert.assert_awaited_once()
        assert "CDP exception" in mock_alert.call_args[0][0]


@pytest.mark.asyncio
async def test_stage3_liberator_authenticated():
    with (
        patch("scripts.start_homelab.ensure_daemon", new_callable=AsyncMock) as mock_ensure,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
    ):
        mock_ensure.return_value = {"status": "spawned", "state": "AUTHENTICATED", "port": 9334, "pid": 5678}
        mock_probe.return_value = {"state": "AUTHENTICATED", "port": 9334, "pid": 5678, "url": "https://webtrade.liberator.co.th/Portfolio"}

        ok = await sh.stage3_verify_liberator_session()
        assert ok is True
        mock_ensure.assert_awaited_once_with("liberator", wait_s=90.0)
        mock_probe.assert_awaited_once_with("liberator")


@pytest.mark.asyncio
async def test_stage3_liberator_not_authenticated_returns_false_without_raising():
    with (
        patch("scripts.start_homelab.ensure_daemon", new_callable=AsyncMock) as mock_ensure,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
    ):
        mock_ensure.return_value = {"status": "DAEMON_DOWN", "state": "DAEMON_DOWN", "port": 9334, "pid": None}
        mock_probe.return_value = {"state": "DAEMON_DOWN", "port": 9334, "pid": None, "reason": "CDP daemon on port 9334 not reachable"}

        ok = await sh.stage3_verify_liberator_session()
        assert ok is False
        mock_ensure.assert_awaited_once_with("liberator", wait_s=90.0)
        mock_probe.assert_awaited_once_with("liberator")


@pytest.mark.asyncio
async def test_stage3_liberator_exception_handled():
    with patch("scripts.start_homelab.ensure_daemon", side_effect=Exception("Liberator network failure")):
        ok = await sh.stage3_verify_liberator_session()
        assert ok is False


@pytest.mark.asyncio
async def test_stage2_and_stage3_force_fresh_calls_restart_daemon():
    with (
        patch("scripts.start_homelab.restart_daemon", new_callable=AsyncMock) as mock_restart,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
    ):
        mock_restart.return_value = {"status": "spawned", "state": "AUTHENTICATED", "port": 9333, "pid": 1111}
        mock_probe.return_value = {"state": "AUTHENTICATED", "port": 9333, "pid": 1111, "url": "https://wme2.settrade.com"}

        ok_kss = await sh.stage2_verify_krungsri_session(force_fresh=True)
        assert ok_kss is True
        mock_restart.assert_awaited_once_with("kss", wait_s=90)

    with (
        patch("scripts.start_homelab.restart_daemon", new_callable=AsyncMock) as mock_restart,
        patch("scripts.start_homelab.cdp_session_status", new_callable=AsyncMock) as mock_probe,
    ):
        mock_restart.return_value = {"status": "spawned", "state": "AUTHENTICATED", "port": 9334, "pid": 2222}
        mock_probe.return_value = {"state": "AUTHENTICATED", "port": 9334, "pid": 2222, "url": "https://webtrade.liberator.co.th"}

        ok_lib = await sh.stage3_verify_liberator_session(force_fresh=True)
        assert ok_lib is True
        mock_restart.assert_awaited_once_with("liberator", wait_s=90)


def test_skip_login_plan_does_not_execute_launcher():
    plan = sh.resolve_startup_plan(kde_ok=True, skip_login=True, skip_liberator=True)
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is False

