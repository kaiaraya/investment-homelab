"""
Unit tests for scripts.preflight_check broker-session health reporting.

Covers LIB-RCA-007: preflight must NOT claim "✅ session exists" from
``os.path.exists()`` alone. It must reuse each driver's REAL session-expiry guard
(Broker Knowledge Isolation):

  - Liberator (live)       -> JWT ``exp`` via app.brokers.liberator.session_health
  - Click2Win (SIMULATION) -> presence + age + cookie count only (never a false ✅)
  - Krungsri (live)        -> presence + size + age

The stale-vs-active disagreement that triggered LIB-RCA-007 is asserted at the
module level (``session_health``) and at the render level (``check_liberator_session``).
"""

import base64
import json
import os
import time

import app.brokers.liberator.session_health as sh
import scripts.preflight_check as pf


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _make_jwt(exp: int) -> str:
    """Builds a syntactically valid JWT whose payload carries the given `exp`."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


def _write_liberator_state(path, *, api_exp=None, cookies=None):
    """Creates a Liberator storage-state file at `path` and returns the path."""
    if cookies is None:
        cookies = []
        if api_exp is not None:
            cookies.append({
                "name": "api-token",
                "value": _make_jwt(api_exp),
                "domain": "webtrade.liberator.co.th",
                "path": "/",
            })
    state = {
        "timestamp": "2026-10-05T12:01:28+00:00",
        "platform": "LIBERATOR",
        "cookies": cookies,
        "current_url": "https://webtrade.liberator.co.th/Market",
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# session_health module (shared single source of truth)
# --------------------------------------------------------------------------- #
def test_read_session_token_expiry_reads_jwt_exp(tmp_path):
    exp = int(time.time()) + 3600
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=exp)
    assert sh.read_session_token_expiry(str(p)) == exp


def test_read_session_token_expiry_falls_back_to_cookie_expires(tmp_path):
    # api-token present but NOT a JWT -> fall back to its positive `expires`.
    future = int(time.time()) + 7200
    p = _write_liberator_state(
        tmp_path / "lib.json",
        cookies=[{"name": "api-token", "value": "not-a-jwt", "expires": future}],
    )
    assert sh.read_session_token_expiry(str(p)) == future


def test_read_session_token_expiry_none_when_only_anti_bot_cookies(tmp_path):
    p = _write_liberator_state(
        tmp_path / "lib.json",
        cookies=[
            {"name": "visid_incap_2965054", "value": "abcd...", "expires": 1822493161},
            {"name": "incap_ses_373_2965054", "value": "abcd", "expires": -1},
        ],
    )
    assert sh.read_session_token_expiry(str(p)) is None


def test_read_session_token_expiry_none_for_missing_file(tmp_path):
    assert sh.read_session_token_expiry(str(tmp_path / "nope.json")) is None


def test_read_session_token_expiry_none_for_corrupt_file(tmp_path):
    p = tmp_path / "lib.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    assert sh.read_session_token_expiry(str(p)) is None


def test_session_expired_true_for_past_exp(tmp_path):
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=int(time.time()) - 300)
    assert sh.session_expired(str(p)) is True


def test_session_expired_true_within_safety_margin(tmp_path):
    # Expires in 10s but the margin is 60s -> treated as unusable.
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=int(time.time()) + 10)
    assert sh.session_expired(str(p), safety_margin_seconds=60) is True


def test_session_expired_false_for_future_exp(tmp_path):
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=int(time.time()) + 3600)
    assert sh.session_expired(str(p)) is False


def test_session_expired_false_when_undeterminable(tmp_path):
    # No determinable expiry must NOT block the live DOM path (LIB-RCA-006).
    p = _write_liberator_state(tmp_path / "lib.json")  # no cookies
    assert sh.session_expired(str(p)) is False


def test_session_health_three_states(tmp_path):
    missing = sh.session_health(str(tmp_path / "nope.json"))
    assert missing == {
        "exists": False, "exp": None, "expired": False, "remaining_seconds": None,
    }

    expired = sh.session_health(
        str(_write_liberator_state(tmp_path / "stale.json", api_exp=int(time.time()) - 60))
    )
    assert expired["exists"] is True
    assert expired["expired"] is True
    assert expired["remaining_seconds"] < 0

    active = sh.session_health(
        str(_write_liberator_state(tmp_path / "fresh.json", api_exp=int(time.time()) + 3600))
    )
    assert active["exists"] is True
    assert active["expired"] is False
    assert active["remaining_seconds"] > 0


# --------------------------------------------------------------------------- #
# Click2Win (SIMULATION) status helper
# --------------------------------------------------------------------------- #
def test_click2win_session_status_no_file(tmp_path):
    status = pf.click2win_session_status(str(tmp_path / "c2w.json"))
    assert status == {"exists": False, "age_seconds": None, "cookie_count": 0}


def test_click2win_session_status_with_file(tmp_path):
    p = tmp_path / "c2w.json"
    p.write_text(json.dumps({"cookies": [{"name": "a"}, {"name": "b"}]}), encoding="utf-8")
    status = pf.click2win_session_status(str(p))
    assert status["exists"] is True
    assert status["cookie_count"] == 2
    assert status["age_seconds"] is not None and status["age_seconds"] >= 0


# --------------------------------------------------------------------------- #
# Render tests (capsys) — the actual false-positive fix (LIB-RCA-007)
# --------------------------------------------------------------------------- #
def _pin_liberator(monkeypatch, path):
    monkeypatch.setattr(pf, "_path", lambda key, default: str(path))


def test_check_liberator_session_renders_expired(tmp_path, monkeypatch, capsys):
    """A present-but-expired saved session must NOT render the green check line."""
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=int(time.time()) - 300)
    _pin_liberator(monkeypatch, p)
    pf.check_liberator_session()
    out = capsys.readouterr().out
    assert "EXPIRED" in out
    assert "✅" not in out


def test_check_liberator_session_renders_active(tmp_path, monkeypatch, capsys):
    p = _write_liberator_state(tmp_path / "lib.json", api_exp=int(time.time()) + 3600)
    _pin_liberator(monkeypatch, p)
    pf.check_liberator_session()
    out = capsys.readouterr().out
    assert "Session active" in out
    assert "✅" in out


def test_check_liberator_session_renders_no_session(tmp_path, monkeypatch, capsys):
    _pin_liberator(monkeypatch, tmp_path / "missing.json")
    pf.check_liberator_session()
    out = capsys.readouterr().out
    assert "No saved session" in out


def test_check_liberator_session_renders_undeterminable(tmp_path, monkeypatch, capsys):
    p = _write_liberator_state(
        tmp_path / "lib.json",
        cookies=[{"name": "incap_ses_1", "value": "x", "expires": -1}],
    )
    _pin_liberator(monkeypatch, p)
    pf.check_liberator_session()
    out = capsys.readouterr().out
    assert "no JWT expiry found" in out
    assert "✅" not in out


def test_check_click2win_session_renders_simulation_step(tmp_path, monkeypatch, capsys):
    """Click2Win has its OWN step and never claims a false check (simulation broker)."""
    monkeypatch.setattr(pf, "_path", lambda key, default: str(tmp_path / "missing.json"))
    pf.check_click2win_session()
    out = capsys.readouterr().out
    assert "SIMULATION" in out
    assert "No saved session" in out
    assert "✅" not in out


def test_check_click2win_session_renders_present_file(tmp_path, monkeypatch, capsys):
    p = tmp_path / "c2w.json"
    p.write_text(json.dumps({"cookies": [{"name": "a"}]}), encoding="utf-8")
    monkeypatch.setattr(pf, "_path", lambda key, default: str(p))
    pf.check_click2win_session()
    out = capsys.readouterr().out
    assert "Saved file present" in out
    assert "1 cookies" in out
    assert "✅" not in out


# --------------------------------------------------------------------------- #
# Krungsri status helper + render — the LIB-RCA-007 / KSS-RCA-011 regression
# --------------------------------------------------------------------------- #
def _pin_krungsri(monkeypatch, path):
    monkeypatch.setattr(pf, "_path", lambda key, default: str(path))


def test_krungsri_session_status_missing(tmp_path):
    status = pf.krungsri_session_status(str(tmp_path / "missing.json"))
    assert status["exists"] is False
    assert status["needs_fresh_login"] is True
    assert status["reason"] == "MISSING"


def test_check_krungsri_session_renders_no_session(tmp_path, monkeypatch, capsys):
    _pin_krungsri(monkeypatch, tmp_path / "missing.json")
    pf.check_krungsri_session()
    out = capsys.readouterr().out
    assert "No saved session" in out
    assert "✅" not in out


def test_check_krungsri_session_renders_expired(tmp_path, monkeypatch, capsys):
    """A present-but-stale saved session must NOT render the green check line."""
    p = tmp_path / "session_state.json"
    p.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    old = time.time() - 20 * 3600
    os.utime(str(p), (old, old))
    _pin_krungsri(monkeypatch, p)
    pf.check_krungsri_session()
    out = capsys.readouterr().out
    assert "EXPIRED" in out
    assert "✅" not in out


def test_check_krungsri_session_renders_recent_present(tmp_path, monkeypatch, capsys):
    """A recent file is reported truthfully — reuse is attempted, but never a false ✅."""
    p = tmp_path / "session_state.json"
    p.write_text(json.dumps({"cookies": [{"name": "a"}]}), encoding="utf-8")
    _pin_krungsri(monkeypatch, p)
    pf.check_krungsri_session()
    out = capsys.readouterr().out
    assert "Saved cookies present" in out
    assert "✅" not in out
