"""Invariant 8 regression: KrungsriAuthDriver.verify_saved_session must be NON-destructive.

Proven once live (2026-10-07): a transient navigation timeout in verify_saved_session()
deleted a freshly-obtained Zero-OTP session (data/session_state.json), forcing a wasteful
SMS-OTP re-login and risking account lock. These tests lock in the non-destructive contract:
- transient timeout/exception  -> leave the session file 100% intact.
- genuine validation miss      -> quarantine (rename to *.stale.bak.json), never hard-delete.
"""
import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.browser.auth_driver import auth_driver
from app.core.config import settings


def _seed_session_file(path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cookies": [{"name": "ws-token", "value": "abc"}], "origins": []}, f)


@pytest.fixture
def isolated_auth_driver(monkeypatch, tmp_path):
    """Point the driver at a tmp session file and always restore global driver state."""
    sess = tmp_path / "session_state.json"
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(sess))
    saved_page = auth_driver.page
    saved_status = auth_driver.status
    saved_context = auth_driver.context
    yield sess
    auth_driver.page = saved_page
    auth_driver.status = saved_status
    auth_driver.context = saved_context


@pytest.mark.asyncio
async def test_transient_timeout_does_not_delete_session_file(isolated_auth_driver):
    """A navigation/DOM timeout must leave the saved Zero-OTP session file fully intact."""
    sess = isolated_auth_driver
    _seed_session_file(sess)

    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.url = "about:blank"
    page.goto = AsyncMock(side_effect=TimeoutError("Page.goto: Timeout 12000ms exceeded"))
    auth_driver.page = page
    auth_driver.context = None

    result = await auth_driver.verify_saved_session()

    assert result is False
    assert os.path.exists(sess), "Invariant 8: a transient timeout MUST NOT delete the session file"
    assert not os.path.exists(f"{sess}.stale.bak.json")


@pytest.mark.asyncio
async def test_validation_miss_quarantines_session_non_destructively(isolated_auth_driver):
    """A genuine validation miss must quarantine (rename), never hard-delete."""
    sess = isolated_auth_driver
    _seed_session_file(sess)

    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.url = "about:blank"
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=Exception("#dropDownAccountPort not found"))
    auth_driver.page = page
    auth_driver.context = None

    result = await auth_driver.verify_saved_session()

    assert result is False
    assert not os.path.exists(sess), "Original path should be quarantined away"
    assert os.path.exists(f"{sess}.stale.bak.json"), "Stale token must be preserved as *.stale.bak.json"


@pytest.mark.asyncio
async def test_missing_session_file_returns_false_without_side_effects(isolated_auth_driver):
    """No file -> plain False, no exceptions, nothing created."""
    sess = isolated_auth_driver

    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    page.url = "about:blank"
    page.goto = AsyncMock()
    auth_driver.page = page
    auth_driver.context = None

    result = await auth_driver.verify_saved_session()

    assert result is False
    assert not os.path.exists(sess)
    page.goto.assert_not_called()
