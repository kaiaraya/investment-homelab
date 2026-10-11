"""Regression tests for the 4-stage startup hardening of ``scripts/start_homelab.py``.

Covers:
  * Stage renumbering — Liberator (was Stage 2B) -> Stage 3, Launch -> Stage 4.
  * Stage 2 Krungsri login-failure LINE escalation helper
    (``push_krungsri_login_alert``) — honest-escalation / Anti-Mock guardrails
    (Invariant 1: never fabricate a successful login; always escalate truthfully).
"""
import asyncio
from unittest.mock import AsyncMock

import scripts.start_homelab as sh


def test_stage1_to_stage4_function_names_exist():
    """After the 4-stage renumbering every stage function must be importable."""
    assert hasattr(sh, "stage1_check_kdeconnect")
    assert hasattr(sh, "stage2_verify_krungsri_session")
    assert hasattr(sh, "stage3_verify_liberator_session")
    assert hasattr(sh, "stage4_launch_server_and_console")


def test_old_stage_function_names_removed():
    """The stale 2B/3-stage names must be gone so no contradictory call site survives."""
    assert not hasattr(sh, "stage2b_verify_liberator_session")
    assert not hasattr(sh, "stage3_launch_server_and_console")


def test_push_krungsri_login_alert_dispatches_critical_line(monkeypatch):
    """A Krungsri login failure must escalate to LINE as CRITICAL with actionable steps."""
    spy = AsyncMock()
    monkeypatch.setattr(sh.line_service, "send_system_notification", spy)

    asyncio.run(sh.push_krungsri_login_alert("login rejected", "invalid credentials"))

    spy.assert_awaited_once()
    _, kwargs = spy.call_args
    assert kwargs["severity"] == "CRITICAL"
    assert "LOGIN FAILED" in kwargs["title"]
    assert "login rejected" in kwargs["message"]
    assert kwargs.get("action_required")


def test_push_krungsri_login_alert_never_raises(monkeypatch):
    """An escalation-transport failure must be swallowed (must not mask the login error)."""
    async def _boom(*args, **kwargs):
        raise RuntimeError("LINE API down")

    monkeypatch.setattr(sh.line_service, "send_system_notification", _boom)

    # Must return normally, not propagate the RuntimeError.
    asyncio.run(sh.push_krungsri_login_alert("login exception", "TimeoutError"))
