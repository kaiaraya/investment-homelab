"""Unit tests for scripts.start_homelab.resolve_startup_plan.

Covers the mobile-offline skip-both decision table — the heart of the
"mobile-offline -> degrade + continue (no sys.exit)" change in main().

Rationale (Invariant 7.3 / root_cause_and_escalation.md):
  KDE Connect is the ONLY channel the system uses to read the 2FA SMS OTP.
  If the bridge is OFFLINE, a fresh broker login is impossible, so startup must
  SKIP BOTH broker logins (Krungsri + Liberator) and mark them DEGRADED rather
  than hard-abort with ``sys.exit(1)``. This keeps the Cockpit reachable for
  manual remediation. ``--skip-*`` flags are INTENTIONAL skips (optimistic, not
  degraded) and must remain distinguishable from the offline-degrade path.
"""
import scripts.start_homelab as sh


def test_kde_offline_skips_both_and_degrades_both():
    """Mobile bridge OFFLINE -> skip BOTH logins and degrade BOTH (no sys.exit)."""
    plan = sh.resolve_startup_plan(False, False, False)
    assert plan["kde_ready"] is False
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is False
    assert plan["degrade_krungsri"] is True
    assert plan["degrade_liberator"] is True


def test_kde_offline_overrides_skip_flags():
    """Offline always wins: even without --skip-* flags, both stages are skipped."""
    plan = sh.resolve_startup_plan(False, True, True)
    assert plan["kde_ready"] is False
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is False
    assert plan["degrade_krungsri"] is True
    assert plan["degrade_liberator"] is True


def test_kde_online_runs_both_without_degrade():
    """Bridge online, no flags -> run BOTH stages, no degradation."""
    plan = sh.resolve_startup_plan(True, False, False)
    assert plan["kde_ready"] is True
    assert plan["run_krungsri"] is True
    assert plan["run_liberator"] is True
    assert plan["degrade_krungsri"] is False
    assert plan["degrade_liberator"] is False


def test_skip_flags_are_optimistic_not_degraded():
    """Explicit --skip-login --skip-liberator -> kde still ready, nothing degraded."""
    plan = sh.resolve_startup_plan(True, True, True)
    assert plan["kde_ready"] is True
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is False
    assert plan["degrade_krungsri"] is False
    assert plan["degrade_liberator"] is False


def test_skip_kde_treated_as_ready_and_runs_per_flags():
    """--skip-kde (kde_ok=None) -> optimistic kde_ready, stages honour their own flags."""
    plan = sh.resolve_startup_plan(None, True, False)
    assert plan["kde_ready"] is True
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is True
    assert plan["degrade_krungsri"] is False
    assert plan["degrade_liberator"] is False


def test_skip_login_only_still_runs_liberator():
    """Skipping only the Krungsri login still runs the (independent) Liberator check."""
    plan = sh.resolve_startup_plan(True, True, False)
    assert plan["kde_ready"] is True
    assert plan["run_krungsri"] is False
    assert plan["run_liberator"] is True
    assert plan["degrade_krungsri"] is False
    assert plan["degrade_liberator"] is False
