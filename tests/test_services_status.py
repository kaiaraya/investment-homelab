"""
Unit tests for scripts.services_status in-gateway daemon reporting.
===================================================================
Covers the 2026-10-10 rename ``ENABLE_PHASE3_SCHEDULER`` -> ``ENABLE_INTRADAY_SCHEDULER``
so the services view, the gateway boot log, and the /console admin toggle registry
(``app.api.v1.endpoints.admin``) all agree on the same flag name (Zero-Contradiction).
"""

import scripts.services_status as ss


def test_daemon_flags_use_renamed_intraday_flag():
    from app.core.config import settings

    row = ss.collect_in_gateway_daemons()

    assert row["key"] == "daemons"
    flags = row["flags"]

    # Renamed key present; the retired name must be gone
    assert "intraday_scheduler" in flags
    assert "phase3_scheduler" not in flags
    assert set(flags) == {"intraday_scheduler", "action_exit_dispatcher", "master_orchestrator"}

    # Values must mirror the live settings (single source of truth)
    assert flags["intraday_scheduler"] is bool(getattr(settings, "ENABLE_INTRADAY_SCHEDULER", False))
    assert flags["action_exit_dispatcher"] is bool(getattr(settings, "ENABLE_ACTION_EXIT_DISPATCHER", False))
    assert flags["master_orchestrator"] is bool(getattr(settings, "ENABLE_AGENTIC_ORCHESTRATOR", False))

    assert row["status"] in ("ON", "SLIM")
