"""
Tests for Liberator WebTrade saved-session JWT expiry handling.

Covers LIB-RCA-006: a remembered-but-expired (~24h) JWT must NOT be treated as a
valid session (Anti-Mock Guardrail / Invariant 1).
"""

import base64
import json
import time

import pytest

from app.brokers.liberator.driver import LiberatorDriver


def _make_jwt(exp: int) -> str:
    """Builds a syntactically valid JWT whose payload carries the given `exp`."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


def _write_state(path, *, api_exp=None, ws_exp=None, cookies=None):
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
        if ws_exp is not None:
            cookies.append({
                "name": "ws-token",
                "value": _make_jwt(ws_exp),
                "domain": "webtrade.liberator.co.th",
                "path": "/",
            })
    state = {
        "timestamp": "2026-10-03T06:12:42.679289+00:00",
        "platform": "LIBERATOR",
        "cookies": cookies,
        "current_url": "https://webtrade.liberator.co.th/Market",
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _driver_with_session(tmp_path, **kwargs) -> LiberatorDriver:
    path = tmp_path / "liberator_session.json"
    _write_state(path, **kwargs)
    drv = LiberatorDriver()
    drv.session_path = str(path)
    return drv


def test_session_token_expiry_reads_jwt_exp(tmp_path):
    exp = int(time.time()) + 3600
    drv = _driver_with_session(tmp_path, api_exp=exp)
    assert drv._session_token_expiry() == exp


def test_session_token_expiry_reads_ws_token_when_no_api_token(tmp_path):
    exp = int(time.time()) + 7200
    drv = _driver_with_session(tmp_path, ws_exp=exp)
    assert drv._session_token_expiry() == exp


def test_session_token_expiry_none_when_only_anti_bot_cookies(tmp_path):
    """Real captured files can contain only Incapsula cookies (no JWT)."""
    drv = _driver_with_session(
        tmp_path,
        cookies=[
            {"name": "visid_incap_2965054", "value": "abcd...", "expires": 1822493161},
            {"name": "incap_ses_373_2965054", "value": "abcd", "expires": -1},
        ],
    )
    assert drv._session_token_expiry() is None
    # No determinable expiry -> must NOT block the live DOM check.
    assert drv._saved_session_expired() is False


def test_saved_session_expired_true_for_past_exp(tmp_path):
    drv = _driver_with_session(tmp_path, api_exp=int(time.time()) - 120)
    assert drv._saved_session_expired() is True


def test_saved_session_not_expired_for_future_exp(tmp_path):
    drv = _driver_with_session(tmp_path, api_exp=int(time.time()) + 3600)
    assert drv._saved_session_expired() is False


def test_saved_session_expired_true_within_safety_margin(tmp_path):
    # Expires in 10s but the safety margin is 60s -> treated as unusable.
    drv = _driver_with_session(tmp_path, api_exp=int(time.time()) + 10)
    assert drv._saved_session_expired(safety_margin_seconds=60) is True


def test_session_token_expiry_none_for_missing_file(tmp_path):
    drv = LiberatorDriver()
    drv.session_path = str(tmp_path / "does_not_exist.json")
    assert drv._session_token_expiry() is None


@pytest.mark.asyncio
async def test_verify_saved_session_rejects_expired_without_browser(tmp_path, monkeypatch):
    """LIB-RCA-006 regression: expired JWT fails fast WITHOUT launching a browser."""
    drv = _driver_with_session(tmp_path, api_exp=int(time.time()) - 60)

    async def _boom(*args, **kwargs):
        raise AssertionError("launch_browser must NOT be called for an expired session")

    monkeypatch.setattr(drv, "launch_browser", _boom)

    assert await drv.verify_saved_session() is False
    assert drv.status == "DISCONNECTED"
