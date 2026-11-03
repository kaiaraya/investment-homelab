# -*- coding: utf-8 -*-
"""Unit tests for broker CDP daemon launcher.

Strictly zero real browser, zero real subprocess, zero network requests.
Verifies contract C1-C7, fail-closed semantics, already_up, spawned, timeout, and restart.
"""
import asyncio
import os
from pathlib import Path
import signal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.broker_cdp.daemon_launcher import (
    REPO_ROOT,
    _DaemonFileLock,
    daemon_state,
    ensure_daemon,
    get_broker_port,
    get_daemon_pid,
    get_log_tail,
    is_port_open,
    normalize_broker_slug,
    restart_daemon,
)


@pytest.fixture(autouse=True)
def prepare_test_db():
    """Unit tests require no database interaction; override conftest autouse db fixture."""
    yield


# ────────────────────────────────────────────────────────────────────────────
# 1. Slug & Port Normalization Tests (C1 & G9)
# ────────────────────────────────────────────────────────────────────────────

def test_normalize_broker_slug_mappings():
    assert normalize_broker_slug("lib") == "liberator"
    assert normalize_broker_slug("liberator") == "liberator"
    assert normalize_broker_slug("LIBERATOR ") == "liberator"
    assert normalize_broker_slug("kss") == "kss"
    assert normalize_broker_slug("krungsri") == "kss"
    assert normalize_broker_slug(" KSS ") == "kss"


def test_normalize_broker_slug_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_broker_slug("unknown_broker")


def test_get_broker_port():
    assert get_broker_port("kss") == 9333
    assert get_broker_port("krungsri") == 9333
    assert get_broker_port("liberator") == 9334
    assert get_broker_port("lib") == 9334


# ────────────────────────────────────────────────────────────────────────────
# 2. Helpers (is_port_open, get_log_tail, pidfile)
# ────────────────────────────────────────────────────────────────────────────

def test_is_port_open_mock():
    with patch("socket.create_connection") as mock_conn:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        assert is_port_open(9333) is True

    with patch("socket.create_connection", side_effect=ConnectionRefusedError):
        assert is_port_open(9333) is False

    assert is_port_open(0) is False


def test_get_log_tail(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    log_dir = tmp_path / "data" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "daemon-kss.log"
    log_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\n", encoding="utf-8")

    tail = get_log_tail("kss", max_lines=3)
    assert tail == "line4\nline5\nline6\n"


def test_get_log_tail_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    assert get_log_tail("kss") == ""


def test_get_daemon_pid_from_pidfile(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    pid_file = data_dir / "daemon-kss.pid"
    pid_file.write_text("99999\n", encoding="utf-8")

    real_open = open
    def side_effect(path, *args, **kwargs):
        if "/proc/99999/cmdline" in str(path):
            m = MagicMock()
            m.__enter__.return_value.read.return_value = b"python scripts/broker_cdp/session_daemon.py kss 300"
            return m
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=side_effect):
        assert get_daemon_pid("kss") == 99999


# ────────────────────────────────────────────────────────────────────────────
# 3. daemon_state Tests (Fail-Closed, OTP vs LOGIN, Port states)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daemon_state_port_closed():
    with patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=False):
        res = await daemon_state("kss")
        assert res["state"] == "DAEMON_DOWN"
        assert res["port"] == 9333
        assert res["page_url"] is None
        assert res["pid"] is None


@pytest.mark.asyncio
async def test_daemon_state_authenticated():
    probe_return = {
        "broker": "kss",
        "purpose": "streaming",
        "state": "AUTHENTICATED",
        "url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp",
        "pid": 1234,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=True),
        patch("app.services.broker_cdp.daemon_launcher.cdp_session_status", new=AsyncMock(return_value=probe_return)),
        patch("app.services.broker_cdp.daemon_launcher.get_daemon_pid", return_value=5678),
    ):
        res = await daemon_state("kss")
        assert res["state"] == "AUTHENTICATED"
        assert res["port"] == 9333
        assert res["page_url"] == "https://wme2.settrade.com/realtime/streaming7/StreamingPage.jsp"
        assert res["pid"] == 5678


@pytest.mark.asyncio
async def test_daemon_state_otp_page_detection():
    probe_return = {
        "broker": "kss",
        "purpose": "streaming",
        "state": "LOGIN_PAGE",
        "url": "https://wen075.settrade.com/twofa/confirm",
        "pid": 1234,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=True),
        patch("app.services.broker_cdp.daemon_launcher.cdp_session_status", new=AsyncMock(return_value=probe_return)),
        patch("app.services.broker_cdp.daemon_launcher.get_daemon_pid", return_value=None),
    ):
        res = await daemon_state("kss")
        assert res["state"] == "OTP_PAGE"
        assert res["port"] == 9333
        assert res["pid"] == 1234


@pytest.mark.asyncio
async def test_daemon_state_login_page_detection():
    probe_return = {
        "broker": "liberator",
        "purpose": "portfolio",
        "state": "LOGIN_PAGE",
        "url": "https://webtrade.liberator.co.th/login",
        "pid": 4321,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=True),
        patch("app.services.broker_cdp.daemon_launcher.cdp_session_status", new=AsyncMock(return_value=probe_return)),
        patch("app.services.broker_cdp.daemon_launcher.get_daemon_pid", return_value=None),
    ):
        res = await daemon_state("lib")
        assert res["state"] == "LOGIN_PAGE"
        assert res["port"] == 9334


@pytest.mark.asyncio
async def test_daemon_state_probe_down_fail_closed():
    probe_return = {
        "broker": "kss",
        "purpose": "streaming",
        "state": "DAEMON_DOWN",
        "url": None,
        "pid": None,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=True),
        patch("app.services.broker_cdp.daemon_launcher.cdp_session_status", new=AsyncMock(return_value=probe_return)),
    ):
        res = await daemon_state("kss")
        assert res["state"] == "DAEMON_DOWN"


@pytest.mark.asyncio
async def test_daemon_state_unknown_broker():
    res = await daemon_state("invalid_broker")
    assert res["state"] == "UNKNOWN"
    assert res["port"] == 0


# ────────────────────────────────────────────────────────────────────────────
# 4. ensure_daemon Tests (already_up, fail_closed, spawned, timeout, crashed)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_daemon_already_up(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    state_mock = {
        "state": "AUTHENTICATED",
        "port": 9333,
        "page_url": "https://wme2.settrade.com/realtime/streaming7/StreamingPage",
        "pid": 8888,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new=AsyncMock(return_value=state_mock)),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        res = await ensure_daemon("kss")
        assert res["status"] == "already_up"
        assert res["state"] == "AUTHENTICATED"
        assert res["port"] == 9333
        assert res["pid"] == 8888
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_daemon_port_open_not_authenticated_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    state_mock = {
        "state": "LOGIN_PAGE",
        "port": 9334,
        "page_url": "https://webtrade.liberator.co.th/login",
        "pid": 7777,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new=AsyncMock(return_value=state_mock)),
        patch("asyncio.create_subprocess_exec") as mock_exec,
    ):
        res = await ensure_daemon("liberator")
        assert res["status"] == "LOGIN_PAGE"
        assert res["state"] == "LOGIN_PAGE"
        assert res["port"] == 9334
        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_daemon_port_open_probe_down_no_spawn(tmp_path, monkeypatch):
    """C7: TCP port open but CDP probe reports DAEMON_DOWN must never spawn a 2nd daemon."""
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    state_mock = {
        "state": "DAEMON_DOWN",
        "port": 9333,
        "page_url": None,
        "pid": None,
    }
    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", new=AsyncMock(return_value=state_mock)),
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=True),
        patch("asyncio.create_subprocess_exec", new=AsyncMock()) as mock_exec,
    ):
        res = await ensure_daemon("kss", wait_s=10)

    mock_exec.assert_not_called()
    assert res["status"] == "DAEMON_DOWN"
    assert res["state"] == "DAEMON_DOWN"
    assert res["port"] == 9333
    assert not (tmp_path / "data" / "daemon-kss.pid").exists()


@pytest.mark.asyncio
async def test_ensure_daemon_spawn_success(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)

    states = [
        {"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None},
        {"state": "AUTHENTICATED", "port": 9333, "page_url": "https://wme2.settrade.com/realtime", "pid": 5555},
    ]
    state_mock = AsyncMock(side_effect=states)

    fake_proc = MagicMock()
    fake_proc.pid = 5555
    fake_proc.returncode = None

    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", state_mock),
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=False),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)) as mock_exec,
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        res = await ensure_daemon("kss", wait_s=10)
        assert res["status"] == "spawned"
        assert res["state"] == "AUTHENTICATED"
        assert res["port"] == 9333
        assert res["pid"] == 5555

        mock_exec.assert_called_once()
        call_args, call_kwargs = mock_exec.call_args
        assert call_args[1] == "scripts/broker_cdp/session_daemon.py"
        assert call_args[2] == "kss"
        assert call_args[3] == "300"
        assert call_kwargs["start_new_session"] is True
        assert call_kwargs["cwd"] == str(tmp_path)
        assert call_kwargs["env"]["DISPLAY"] == ":0"

        pid_file = tmp_path / "data" / "daemon-kss.pid"
        assert pid_file.read_text().strip() == "5555"


@pytest.mark.asyncio
async def test_ensure_daemon_spawn_early_otp_exit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)

    states = [
        {"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None},
        {"state": "OTP_PAGE", "port": 9333, "page_url": "https://wen075.settrade.com/twofa", "pid": 1212},
    ]
    state_mock = AsyncMock(side_effect=states)

    fake_proc = MagicMock()
    fake_proc.pid = 1212
    fake_proc.returncode = None

    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", state_mock),
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=False),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        res = await ensure_daemon("kss", wait_s=10)
        assert res["status"] == "OTP_PAGE"
        assert res["state"] == "OTP_PAGE"
        assert res["port"] == 9333
        assert res["pid"] == 1212


@pytest.mark.asyncio
async def test_ensure_daemon_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)

    state_mock = AsyncMock(return_value={"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None})

    fake_proc = MagicMock()
    fake_proc.pid = 9999
    fake_proc.returncode = None

    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", state_mock),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)),
    ):
        res = await ensure_daemon("kss", wait_s=0.02)
        assert res["status"] == "timeout"
        assert res["state"] == "DAEMON_DOWN"
        assert res["pid"] == 9999


@pytest.mark.asyncio
async def test_ensure_daemon_crashed(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)

    state_mock = AsyncMock(return_value={"state": "DAEMON_DOWN", "port": 9333, "page_url": None, "pid": None})
    fake_proc = MagicMock()
    fake_proc.pid = 9999
    fake_proc.returncode = 1

    with (
        patch("app.services.broker_cdp.daemon_launcher.daemon_state", state_mock),
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=fake_proc)),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        res = await ensure_daemon("kss", wait_s=10)
        assert res["status"] == "crashed"
        assert res["state"] == "DAEMON_DOWN"


# ────────────────────────────────────────────────────────────────────────────
# 5. restart_daemon Tests (Kill order C6, Signal handling, Re-spawn)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_restart_daemon_kill_order(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    pid_file = data_dir / "daemon-kss.pid"
    pid_file.write_text("1001\n", encoding="utf-8")

    kill_signals = []

    def mock_kill(pid, sig):
        kill_signals.append((pid, sig))
        if sig == 0:
            raise OSError("No such process")

    def mock_killpg(pgid, sig):
        kill_signals.append((pgid, sig))

    with (
        patch("app.services.broker_cdp.daemon_launcher.get_daemon_pid", return_value=1001),
        patch("app.services.broker_cdp.daemon_launcher.get_cdp_daemon_pid", return_value=2002),
        patch("os.getpgid", return_value=1001),
        patch("os.kill", side_effect=mock_kill),
        patch("os.killpg", side_effect=mock_killpg),
        patch("app.services.broker_cdp.daemon_launcher.is_port_open", return_value=False),
        patch("app.services.broker_cdp.daemon_launcher.ensure_daemon", new=AsyncMock(return_value={"status": "spawned", "state": "AUTHENTICATED"})) as mock_ensure,
    ):
        res = await restart_daemon("kss")
        assert res["status"] == "spawned"

        assert len(kill_signals) >= 1
        assert kill_signals[0] == (1001, signal.SIGTERM)
        assert not pid_file.exists()
        mock_ensure.assert_called_once_with("kss", wait_s=90)


# ────────────────────────────────────────────────────────────────────────────
# 6. File Locking Concurrency Test
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daemon_file_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.broker_cdp.daemon_launcher.REPO_ROOT", tmp_path)
    async with _DaemonFileLock("kss", timeout=1.0):
        lock_file = tmp_path / "data" / "locks" / "daemon-kss.lock"
        assert lock_file.exists()
        # Verify reentrant acquisition succeeds without deadlock or timeout
        async with _DaemonFileLock("kss", timeout=0.1):
            assert lock_file.exists()
