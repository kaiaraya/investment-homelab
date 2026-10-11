"""
Unit tests for app.brokers.krungsri.session_health (KSS-RCA-011 / LIB-RCA-007).

The shared browser-free inspector must NEVER report a missing/stale saved session as
"ready": ``needs_fresh_login`` must be True when the storage-state file is absent or
older than the trading-day limit (Anti-Mock Guardrail).
"""

import json
import os
import time

import app.brokers.krungsri.session_health as sh


def _write_state(path, cookie_count=2):
    state = {
        "cookies": [{"name": f"c{i}", "value": "x", "expires": -1} for i in range(cookie_count)],
        "origins": [],
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _age_file(path, hours):
    """Backdates a file's mtime by `hours`."""
    target = time.time() - hours * 3600
    os.utime(str(path), (target, target))
    return path


# --------------------------------------------------------------------------- #
# MISSING
# --------------------------------------------------------------------------- #
def test_missing_file_requires_fresh_login(tmp_path):
    info = sh.session_file_info(str(tmp_path / "session_state.json"))
    assert info["exists"] is False
    assert info["needs_fresh_login"] is True
    assert info["reason"] == sh.REASON_MISSING
    assert info["mtime"] is None
    assert info["mtime_iso"] is None
    assert info["age_seconds"] is None
    assert info["age_hours"] is None
    assert info["cookie_count"] == 0


# --------------------------------------------------------------------------- #
# RECENT (reuse worth attempting — no fresh login needed yet)
# --------------------------------------------------------------------------- #
def test_recent_file_does_not_require_fresh_login(tmp_path):
    p = _write_state(tmp_path / "session_state.json", cookie_count=3)
    info = sh.session_file_info(str(p))
    assert info["exists"] is True
    assert info["needs_fresh_login"] is False
    assert info["reason"] == sh.REASON_RECENT
    assert info["cookie_count"] == 3
    assert info["age_hours"] is not None and info["age_hours"] < 1
    assert isinstance(info["mtime_iso"], str) and info["mtime_iso"]


# --------------------------------------------------------------------------- #
# STALE (older than a trading day -> EXPIRED for reporting)
# --------------------------------------------------------------------------- #
def test_stale_file_requires_fresh_login(tmp_path):
    p = _age_file(_write_state(tmp_path / "session_state.json"), hours=20)
    info = sh.session_file_info(str(p))
    assert info["exists"] is True
    assert info["needs_fresh_login"] is True
    assert info["reason"] == sh.REASON_STALE
    assert info["age_hours"] > 12


def test_custom_max_age_threshold(tmp_path):
    p = _age_file(_write_state(tmp_path / "session_state.json"), hours=2)
    assert sh.session_file_info(str(p), max_age_hours=1)["reason"] == sh.REASON_STALE
    assert sh.session_file_info(str(p), max_age_hours=48)["reason"] == sh.REASON_RECENT


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #
def test_corrupt_json_presence_is_not_trusted_for_cookies(tmp_path):
    p = tmp_path / "session_state.json"
    p.write_text("{not valid json", encoding="utf-8")
    info = sh.session_file_info(str(p))
    assert info["exists"] is True
    assert info["cookie_count"] == 0
    # A freshly-written corrupt file is "RECENT" -> reuse attempt, but 0 cookies reported.
    assert info["reason"] == sh.REASON_RECENT


def test_session_needs_fresh_login_predicate(tmp_path):
    assert sh.session_needs_fresh_login(str(tmp_path / "nope.json")) is True
    p = _write_state(tmp_path / "session_state.json")
    assert sh.session_needs_fresh_login(str(p)) is False
