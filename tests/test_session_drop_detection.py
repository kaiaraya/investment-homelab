"""
Tests for proactive session-drop detection (Phase A — KSS-RCA-011 / LIB-RCA-007).

Covers:
  * A2: MCP ``session_get_health`` exposes file-backed session state
        (session_file_exists / session_file_mtime / session_file_age_hours /
         needs_fresh_login / session_file_reason) so agents can tell
        "no saved session at all" from "saved session present but driver detached".
"""

import json
import os
import time
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import app.browser.session_sentinel as sentinel_mod
from app.browser.session_sentinel import (
    is_premarket_window,
    seconds_until_premarket_window,
    session_sentinel,
)
from app.core.config import settings
from app.db.models import SessionLog
from app.mcp.pillars.pillar1_session import session_get_health
from app.services.kdeconnect_service import kdeconnect_service
from app.services.line_service import line_service


# ==============================================================================
# A2 — MCP session_get_health exposes the on-disk session file state
# ==============================================================================
@pytest.mark.asyncio
async def test_session_get_health_reports_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(tmp_path / "session_state.json"))
    health = await session_get_health()
    kss = health["krungsri_trademan"]
    assert kss["session_file_exists"] is False
    assert kss["session_file_mtime"] is None
    assert kss["session_file_age_hours"] is None
    assert kss["needs_fresh_login"] is True
    assert kss["session_file_reason"] == "MISSING"


@pytest.mark.asyncio
async def test_session_get_health_reports_present_file(monkeypatch, tmp_path):
    p = tmp_path / "session_state.json"
    p.write_text(json.dumps({"cookies": [{"name": "a", "value": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(p))
    health = await session_get_health()
    kss = health["krungsri_trademan"]
    assert kss["session_file_exists"] is True
    assert kss["session_file_mtime"]
    assert kss["session_file_age_hours"] is not None
    assert kss["needs_fresh_login"] is False
    assert kss["session_file_reason"] == "RECENT"


# ==============================================================================
# A3 — SessionSentinel detects a session-file DROP with NO live tab
# ==============================================================================
def _seed_sentinel_state(monkeypatch, path, *, exists, needs_login):
    """Points the sentinel at `path` and seeds its last-observed baseline."""
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(path))
    session_sentinel._last_session_file_exists = exists
    session_sentinel._last_session_file_needs_login = needs_login


@pytest.mark.asyncio
async def test_transition_first_observation_is_baseline_only(monkeypatch, tmp_path, db_session):
    """The very first observation must record state without spamming an alert."""
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(tmp_path / "session_state.json"))
    session_sentinel._last_session_file_exists = None
    session_sentinel._last_session_file_needs_login = None
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_session_file_transition()
        mock_push.assert_not_awaited()
    assert session_sentinel._last_session_file_exists is False


@pytest.mark.asyncio
async def test_transition_present_to_missing_fires_dual_alert(monkeypatch, tmp_path, db_session):
    """present -> missing must log + alert on BOTH LINE and KDE Connect."""
    _seed_sentinel_state(monkeypatch, tmp_path / "session_state.json", exists=True, needs_login=False)
    # File is deliberately NOT created -> a drop has occurred.
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_session_file_transition()
        mock_push.assert_awaited_once()
        assert "หายไปจากเครื่อง" in mock_push.call_args[0][0]

    assert kdeconnect_service.send_critical_alert.await_count >= 1
    stmt = select(SessionLog).where(SessionLog.event_type == "SESSION_FILE_LOST")
    log = (await db_session.execute(stmt)).scalars().first()
    assert log is not None


@pytest.mark.asyncio
async def test_transition_recent_to_expired_fires_alert(monkeypatch, tmp_path, db_session):
    """recent -> stale (>12h) must be surfaced as an expiry, not silent."""
    p = tmp_path / "session_state.json"
    p.write_text(json.dumps({"cookies": [{"name": "a", "value": "x"}]}), encoding="utf-8")
    _seed_sentinel_state(monkeypatch, p, exists=True, needs_login=False)
    old = time.time() - 20 * 3600
    os.utime(str(p), (old, old))

    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_session_file_transition()
        mock_push.assert_awaited_once()
        assert "หมดอายุ" in mock_push.call_args[0][0]

    stmt = select(SessionLog).where(SessionLog.event_type == "SESSION_FILE_EXPIRED")
    assert (await db_session.execute(stmt)).scalars().first() is not None


@pytest.mark.asyncio
async def test_transition_does_not_repeat_alert(monkeypatch, tmp_path, db_session):
    """A steady missing state must not re-alert on every monitor tick."""
    _seed_sentinel_state(monkeypatch, tmp_path / "session_state.json", exists=True, needs_login=False)
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_session_file_transition()  # fires
        await session_sentinel._check_session_file_transition()  # steady state
        assert mock_push.await_count == 1


# ==============================================================================
# A4 — Pre-market warning (KSS-RCA-009: 09:45–09:55 Bangkok, weekdays only)
# ==============================================================================
def test_premarket_window_weekday_inside():
    assert is_premarket_window(datetime(2026, 9, 28, 9, 45, 0)) is True   # Monday
    assert is_premarket_window(datetime(2026, 9, 28, 9, 48, 0)) is True
    assert is_premarket_window(datetime(2026, 9, 28, 9, 55, 59)) is True


def test_premarket_window_weekday_outside():
    assert is_premarket_window(datetime(2026, 9, 28, 9, 44, 59)) is False
    assert is_premarket_window(datetime(2026, 9, 28, 9, 56, 0)) is False
    assert is_premarket_window(datetime(2026, 9, 28, 10, 5, 0)) is False


def test_premarket_window_weekend_never():
    assert is_premarket_window(datetime(2026, 9, 26, 9, 48, 0)) is False  # Saturday
    assert is_premarket_window(datetime(2026, 9, 27, 9, 48, 0)) is False  # Sunday


def test_seconds_until_premarket_window():
    # Inside the window -> 0
    assert seconds_until_premarket_window(datetime(2026, 9, 28, 9, 48, 0)) == 0.0
    # Monday 09:00 -> 45 minutes
    assert seconds_until_premarket_window(datetime(2026, 9, 28, 9, 0, 0)) == 45 * 60


def test_seconds_until_premarket_window_rolls_weekend_to_monday():
    friday_after = datetime(2026, 10, 2, 16, 0, 0)  # Friday, after the window
    assert friday_after.weekday() == 4
    monday_window = datetime(2026, 10, 5, 9, 45, 0)
    assert seconds_until_premarket_window(friday_after) == (
        monday_window - friday_after
    ).total_seconds()


def test_next_wait_seconds_caps_to_premarket_window(monkeypatch):
    """The monitor must not sleep PAST the 09:45 window (KSS-RCA-009)."""
    session_sentinel.interval_seconds = 1800
    monkeypatch.setattr(sentinel_mod, "bkk_now", lambda: datetime(2026, 9, 28, 9, 40, 0))
    assert session_sentinel._next_wait_seconds() == 300.0  # exactly to 09:45
    monkeypatch.setattr(sentinel_mod, "bkk_now", lambda: datetime(2026, 9, 28, 8, 0, 0))
    assert session_sentinel._next_wait_seconds() == 1800.0  # far away -> normal interval


@pytest.mark.asyncio
async def test_premarket_warning_fires_once_per_day(monkeypatch, tmp_path, db_session):
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(sentinel_mod, "bkk_now", lambda: datetime(2026, 9, 28, 9, 48, 0))
    session_sentinel._last_premarket_warn_date = None
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_premarket_warning()  # fires
        await session_sentinel._check_premarket_warning()  # same BKK day -> deduped
        assert mock_push.await_count == 1
        assert "ตลาดเปิด" in mock_push.call_args[0][0]

    stmt = select(SessionLog).where(SessionLog.event_type == "PREMARKET_SESSION_WARNING")
    assert (await db_session.execute(stmt)).scalars().first() is not None


@pytest.mark.asyncio
async def test_premarket_warning_silent_outside_window(monkeypatch, tmp_path, db_session):
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(sentinel_mod, "bkk_now", lambda: datetime(2026, 9, 28, 11, 0, 0))
    session_sentinel._last_premarket_warn_date = None
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_premarket_warning()
        mock_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_premarket_warning_silent_when_session_recent(monkeypatch, tmp_path, db_session):
    p = tmp_path / "session_state.json"
    p.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    monkeypatch.setattr(settings, "SESSION_STATE_PATH", str(p))
    monkeypatch.setattr(sentinel_mod, "bkk_now", lambda: datetime(2026, 9, 28, 9, 48, 0))
    session_sentinel._last_premarket_warn_date = None
    with patch.object(line_service, "push_message", new_callable=AsyncMock) as mock_push:
        await session_sentinel._check_premarket_warning()
        mock_push.assert_not_awaited()
