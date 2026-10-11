"""
Unit tests for scripts.daily_readiness — the unified daily readiness runner.

Covers the safety gates the skill promises (broker_pdca_rca / root_cause_and_escalation):

  * Invariant 9 — auto re-login must be CANCELLED (status=BRIDGE_DOWN) and must NEVER
    call a broker ``login()`` (i.e. never fire SMS OTP) when the mobile bridge is down.
  * Anti-Mock — the GO/NO-GO verdict must reflect the real offline verdict in
    report-only mode (a deliberate ``--no-login`` skip is NOT a failure).
  * Single source of truth — Krungsri/Liberator readiness reuses each broker's own
    session-health module (Broker Knowledge Isolation).
  * Exit code mapping: GO -> 0, NO-GO -> 1.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import scripts.daily_readiness as dr
from app.browser.auth_driver import auth_driver as krungsri_auth_driver
from app.brokers.liberator.driver import liberator_driver
from app.brokers.krungsri import session_health as kss_session_health
from app.brokers.liberator import session_health as lib_session_health
from app.core.config import settings
from app.services.kdeconnect_service import kdeconnect_service


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pin_bridge(monkeypatch, reachable=True, refreshed=None):
    """
    Pins the LINE-group OTP relay probes so tests never touch the network, `.env`
    or the cloudflared tunnel.

    Invariant 9 (LINE variant, 2026-10-08): the gate is
    `otp_relay_readiness.check()` — the SAME single source of truth the real drivers
    (auth_driver / liberator_driver) call. It replaces the old KDE/D-Bus probe.

    `refreshed` is kept for backward compatibility with the previous API: passing
    `[False, False]` still means "not reachable" (its last element decides).
    """
    from app.services.line_service import line_service
    from app.services.otp_relay_readiness import OtpRelayReadiness, otp_relay_readiness

    if refreshed is not None:
        reachable = bool(refreshed[-1]) if isinstance(refreshed, (list, tuple)) else bool(refreshed)

    if reachable:
        result = OtpRelayReadiness(
            ready=True,
            channel="line_group",
            reason="LINE group relay ready (test)",
            details={"gateway_up": True, "line_group_id_configured": True},
        )
    else:
        result = OtpRelayReadiness(
            ready=False,
            channel="none",
            reason="Backend gateway is DOWN on :8000 (test)",
            details={"gateway_up": False, "line_group_id_configured": True},
        )

    monkeypatch.setattr(otp_relay_readiness, "check", AsyncMock(return_value=result))
    # Never hit api.line.me from a unit test
    monkeypatch.setattr(line_service, "push_message", AsyncMock(return_value=True))
    monkeypatch.setattr(line_service, "send_system_notification", AsyncMock(return_value=False))


def _pin_krungsri_verdict(monkeypatch, *, exists=True, needs_fresh_login=False,
                          reason="RECENT", cookie_count=3, age_hours=1.0):
    monkeypatch.setattr(
        kss_session_health,
        "session_file_info",
        lambda path: {
            "exists": exists,
            "cookie_count": cookie_count,
            "age_hours": age_hours,
            "mtime_iso": "2026-10-08T09:00:00",
            "needs_fresh_login": needs_fresh_login,
            "reason": reason,
        },
    )


def _pin_liberator_verdict(monkeypatch, *, exists=True, expired=False, remaining=3600):
    monkeypatch.setattr(
        lib_session_health,
        "session_health",
        lambda path: {
            "exists": exists,
            "expired": expired,
            "exp": None,
            "remaining_seconds": remaining,
        },
    )


# --------------------------------------------------------------------------- #
# Invariant 9 — OTP Bridge Readiness Gate
# --------------------------------------------------------------------------- #
def test_krungsri_login_cancelled_when_bridge_down(monkeypatch, capsys):
    """bridge down -> BRIDGE_DOWN, and auth_driver.login() must NOT be invoked."""
    login_spy = AsyncMock()
    monkeypatch.setattr(krungsri_auth_driver, "login", login_spy)

    args = dr.parse_args([])
    out = asyncio.run(dr.ensure_krungsri(args, bridge_ok=False))

    assert out["status"] == "BRIDGE_DOWN"
    assert out["authenticated"] is None
    login_spy.assert_not_awaited()
    assert "ไม่ยิง SMS OTP" in capsys.readouterr().out


def test_liberator_login_cancelled_when_bridge_down(monkeypatch):
    login_spy = AsyncMock()
    monkeypatch.setattr(liberator_driver, "login", login_spy)

    args = dr.parse_args([])
    out = asyncio.run(dr.ensure_liberator(args, bridge_ok=False))

    assert out["status"] == "BRIDGE_DOWN"
    login_spy.assert_not_awaited()


def test_no_login_flag_skips_relogin_even_when_bridge_live(monkeypatch):
    login_spy = AsyncMock()
    monkeypatch.setattr(krungsri_auth_driver, "login", login_spy)
    _pin_krungsri_verdict(monkeypatch)

    args = dr.parse_args(["--no-login"])
    out = asyncio.run(dr.ensure_krungsri(args, bridge_ok=True))

    assert out["status"] == "SKIPPED"
    login_spy.assert_not_awaited()


# --------------------------------------------------------------------------- #
# OTP relay step (Invariant 9 — LINE variant, replaces the KDE/D-Bus probe)
# --------------------------------------------------------------------------- #
def test_relay_ready_reports_line_channel(monkeypatch):
    _pin_bridge(monkeypatch, reachable=True)
    args = dr.parse_args([])

    out = asyncio.run(dr.ensure_mobile_bridge(args))

    assert out["reachable"] is True
    assert out["channel"] == "line_group"


def test_relay_down_escalates_to_hitl_without_pinging(monkeypatch):
    """When the relay is not ready we escalate (LINE system notification) — never fake readiness."""
    _pin_bridge(monkeypatch, reachable=False)
    from app.services.line_service import line_service

    help_spy = AsyncMock(return_value=True)
    push_spy = AsyncMock(return_value=True)
    monkeypatch.setattr(line_service, "send_system_notification", help_spy)
    monkeypatch.setattr(line_service, "push_message", push_spy)

    args = dr.parse_args([])
    out = asyncio.run(dr.ensure_mobile_bridge(args))

    assert out["reachable"] is False
    assert out["pinged"] is False
    help_spy.assert_awaited_once()
    push_spy.assert_not_awaited()


def test_relay_ready_sends_line_group_confirmation(monkeypatch):
    """Ready relay -> push the human-confirm message into the LINE group (stepwise-approval §5)."""
    _pin_bridge(monkeypatch, reachable=True)
    from app.services.line_service import line_service

    push_spy = AsyncMock(return_value=True)
    monkeypatch.setattr(line_service, "push_message", push_spy)

    args = dr.parse_args([])
    out = asyncio.run(dr.ensure_mobile_bridge(args))

    assert out["reachable"] is True and out["pinged"] is True
    push_spy.assert_awaited_once()


# --------------------------------------------------------------------------- #
# GO / NO-GO verdict logic (Anti-Mock: no false NO-GO from a deliberate skip)
# --------------------------------------------------------------------------- #
def test_krungsri_ready_matrix():
    assert dr._krungsri_ready({"status": "AUTHENTICATED"}) is True
    assert dr._krungsri_ready({"status": "FAILED"}) is False
    assert dr._krungsri_ready({"status": "ERROR"}) is False
    assert dr._krungsri_ready({"status": "BRIDGE_DOWN"}) is False
    # report-only: the offline verdict decides
    assert dr._krungsri_ready({"status": "SKIPPED", "needs_fresh_login": False}) is True
    assert dr._krungsri_ready({"status": "SKIPPED", "needs_fresh_login": True}) is False


def test_liberator_ready_matrix():
    assert dr._liberator_ready({"status": "AUTHENTICATED"}) is True
    assert dr._liberator_ready({"status": "SKIPPED", "exists": True, "expired": False}) is True
    assert dr._liberator_ready({"status": "SKIPPED", "exists": True, "expired": True}) is False
    assert dr._liberator_ready({"status": "SKIPPED", "exists": False, "expired": False}) is False
    assert dr._liberator_ready({"status": "BRIDGE_DOWN"}) is False


def test_run_report_only_is_go_when_both_sessions_healthy(monkeypatch):
    """--no-login + healthy offline verdicts -> GO (no browser, no OTP)."""
    _pin_bridge(monkeypatch, reachable=True)
    _pin_krungsri_verdict(monkeypatch, needs_fresh_login=False, reason="RECENT")
    _pin_liberator_verdict(monkeypatch, exists=True, expired=False)
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": True})

    summary = asyncio.run(dr.run(dr.parse_args(["--no-login", "--no-ping"])))

    assert summary["verdict"] == "GO"
    assert summary["reasons"] == []


def test_run_report_only_no_go_when_krungsri_session_missing(monkeypatch):
    _pin_bridge(monkeypatch, reachable=True)
    _pin_krungsri_verdict(monkeypatch, exists=False, needs_fresh_login=True, reason="MISSING")
    _pin_liberator_verdict(monkeypatch, exists=True, expired=False)
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": True})

    summary = asyncio.run(dr.run(dr.parse_args(["--no-login", "--no-ping"])))

    assert summary["verdict"] == "NO-GO"
    assert any("Krungsri" in r for r in summary["reasons"])


def test_run_no_go_when_bridge_down(monkeypatch, capsys):
    _pin_bridge(monkeypatch, refreshed=[False, False])
    _pin_krungsri_verdict(monkeypatch, needs_fresh_login=False, reason="RECENT")
    _pin_liberator_verdict(monkeypatch, exists=True, expired=False)
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": True})

    summary = asyncio.run(dr.run(dr.parse_args(["--no-login", "--no-ping"])))

    assert summary["verdict"] == "NO-GO"
    assert any("bridge" in r.lower() for r in summary["reasons"])
    assert "SMS OTP" in capsys.readouterr().out


def test_run_skips_liberator_when_flagged(monkeypatch):
    """--skip-liberator: Liberator must not block the verdict."""
    _pin_bridge(monkeypatch, reachable=True)
    _pin_krungsri_verdict(monkeypatch, needs_fresh_login=False, reason="RECENT")
    _pin_liberator_verdict(monkeypatch, exists=False, expired=True)
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": True})

    summary = asyncio.run(dr.run(dr.parse_args(["--no-login", "--no-ping", "--skip-liberator"])))

    assert summary["verdict"] == "GO"
    assert summary["liberator"]["status"] == "SKIPPED"


# --------------------------------------------------------------------------- #
# Exit-code mapping + Click2Win / backend probes
# --------------------------------------------------------------------------- #
def test_main_returns_1_on_no_go(monkeypatch):
    _pin_bridge(monkeypatch, refreshed=[False, False])
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": False})

    assert dr.main(["--no-login", "--no-ping"]) == 1


def test_main_returns_0_on_go(monkeypatch):
    _pin_bridge(monkeypatch, reachable=True)
    _pin_krungsri_verdict(monkeypatch, needs_fresh_login=False, reason="RECENT")
    _pin_liberator_verdict(monkeypatch, exists=True, expired=False)
    monkeypatch.setattr(dr, "check_backend", lambda: {"up": True})

    assert dr.main(["--no-login", "--no-ping"]) == 0


def test_click2win_never_claims_a_green_check(tmp_path, monkeypatch, capsys):
    """Click2Win is a sandbox with no JWT -> presence only, never a false ✅."""
    p = tmp_path / "click2win_session.json"
    p.write_text(json.dumps({"cookies": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "CLICK2WIN_SESSION_PATH", str(p))

    out = dr.inspect_click2win(dr.parse_args([]))
    printed = capsys.readouterr().out

    assert out["exists"] is True and out["cookies"] == 2
    assert "✅" not in printed


def test_check_backend_uses_tcp_probe(monkeypatch):
    monkeypatch.setattr(dr, "_port_open", lambda host, port, timeout=0.6: True)
    assert dr.check_backend() == {"up": True}
    monkeypatch.setattr(dr, "_port_open", lambda host, port, timeout=0.6: False)
    assert dr.check_backend() == {"up": False}
