"""Unit tests for scripts.dev_resume_session — Zero-OTP resume helper (KSS-RCA-015 companion).

Covers the pure decision boundary (Anti-Mock: real assertions, no guessing):
  * decide_action() maps session_file_info() → 'resume' vs 'fresh_login'.
  * format_report() surfaces the action + reason (human-readable, stable strings).
"""

import scripts.dev_resume_session as drs


def test_decide_action_missing():
    info = {"exists": False, "needs_fresh_login": True}
    assert drs.decide_action(info) == "fresh_login"


def test_decide_action_stale():
    info = {"exists": True, "needs_fresh_login": True}
    assert drs.decide_action(info) == "fresh_login"


def test_decide_action_recent():
    info = {"exists": True, "needs_fresh_login": False}
    assert drs.decide_action(info) == "resume"


def test_format_report_contains_action_and_reason():
    out = drs.format_report(
        {
            "exists": True,
            "mtime_iso": "2026-10-10T16:39:00",
            "age_hours": 1.0,
            "cookie_count": 60,
            "reason": "RECENT",
            "needs_fresh_login": False,
        },
        "resume",
    )
    assert "resume" in out
    assert "RECENT" in out
    assert "60" in out
