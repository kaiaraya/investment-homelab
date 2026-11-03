# -*- coding: utf-8 -*-
"""CDP broker session daemon launcher (unified startup / attach / restart).

Single control surface to ensure CDP broker daemons (:9333/:9334) are running
without duplicate logins, credential prompts, or SSO session decay.
"""
import asyncio
import fcntl
import logging
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from app.services.broker_cdp.session_probe import cdp_session_status, get_cdp_daemon_pid
from scripts.broker_cdp.client import BROKER_CDP_PORTS

logger = logging.getLogger("broker_cdp_daemon_launcher")

REPO_ROOT = Path(__file__).resolve().parents[3]

BROKER_PORTS = {
    "kss": 9333,
    "krungsri": 9333,
    "liberator": 9334,
    "lib": 9334,
}

VALID_STATES = {
    "AUTHENTICATED",
    "LOGIN_PAGE",
    "OTP_PAGE",
    "NO_TARGET_TAB",
    "DAEMON_DOWN",
    "UNKNOWN",
}


def normalize_broker_slug(broker: str) -> str:
    """Map external/legacy broker slugs to canonical daemon names ('kss' | 'liberator')."""
    b = (broker or "").strip().lower()
    if b in ("lib", "liberator"):
        return "liberator"
    if b in ("kss", "krungsri"):
        return "kss"
    raise ValueError(f"Unknown broker slug '{broker}'. Expected 'kss' or 'liberator'")


def get_broker_port(broker: str) -> int:
    """Resolve CDP debugging port for broker."""
    b = (broker or "").strip().lower()
    if b in BROKER_PORTS:
        return BROKER_PORTS[b]
    return BROKER_CDP_PORTS.get(b, 0)


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Check whether a local TCP port is actively accepting connections."""
    if not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError, socket.timeout):
        return False


def get_daemon_pid(broker: str) -> Optional[int]:
    """Find PID of the python session_daemon process for broker."""
    norm = normalize_broker_slug(broker)
    pid_file = REPO_ROOT / "data" / f"daemon-{norm}.pid"
    if pid_file.exists():
        try:
            with open(pid_path_str := str(pid_file), "r", encoding="utf-8") as f:
                candidate = int(f.read().strip())
            with open(f"/proc/{candidate}/cmdline", "rb") as fh:
                cmdline = fh.read().decode(errors="replace")
            if "session_daemon.py" in cmdline and norm in cmdline:
                return candidate
        except (OSError, ValueError):
            pass

    # Fallback scan /proc
    try:
        proc_dir = "/proc"
        if os.path.exists(proc_dir):
            for entry in os.listdir(proc_dir):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                try:
                    with open(f"/proc/{pid}/cmdline", "rb") as fh:
                        raw = fh.read().decode(errors="replace")
                    if "session_daemon.py" in raw and norm in raw:
                        return pid
                except (OSError, IOError):
                    continue
    except Exception:
        pass
    return None


def get_pid_holding_port(port: int) -> Optional[int]:
    """Find any process PID listening on the given port (ss / lsof fallback)."""
    if not port:
        return None
    try:
        out = subprocess.check_output(
            ["ss", "-ltnp", f"sport = :{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        match = re.search(r"pid=(\d+)", out)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["lsof", "-t", f"-i:{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        pids = [int(p) for p in out.strip().split() if p.isdigit()]
        if pids:
            return pids[0]
    except Exception:
        pass
    return None


def get_log_tail(broker: str, max_lines: int = 5) -> str:
    """Read the last N lines from the broker daemon log file."""
    try:
        norm = normalize_broker_slug(broker)
        log_file = REPO_ROOT / "data" / "logs" / f"daemon-{norm}.log"
        if not log_file.exists():
            return ""
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-max_lines:])
    except Exception:
        return ""


class _DaemonFileLock:
    """Cross-process mutex via fcntl.flock on data/locks/daemon-<broker>.lock."""

    def __init__(self, broker: str, timeout: float = 15.0):
        self.broker = broker
        self.timeout = timeout
        self.file_obj = None

    def _acquire(self):
        norm = normalize_broker_slug(self.broker)
        lock_dir = REPO_ROOT / "data" / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / f"daemon-{norm}.lock"
        self.file_obj = open(lock_path, "a+")
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (BlockingIOError, OSError):
                if time.monotonic() - start > self.timeout:
                    raise TimeoutError(f"Could not acquire daemon lock for {norm} within {self.timeout}s")
                time.sleep(0.1)

    def _release(self):
        if self.file_obj:
            try:
                fcntl.flock(self.file_obj.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self.file_obj.close()
            except OSError:
                pass
            self.file_obj = None

    async def __aenter__(self):
        await asyncio.to_thread(self._acquire)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await asyncio.to_thread(self._release)


async def daemon_state(broker: str) -> Dict[str, Any]:
    """Inspect live daemon state for broker without modifying state or launching processes.

    Returns:
        {"state": str, "port": int, "page_url": Optional[str], "pid": Optional[int]}
    """
    try:
        norm = normalize_broker_slug(broker)
    except ValueError:
        return {
            "state": "UNKNOWN",
            "port": 0,
            "page_url": None,
            "pid": None,
        }

    port = get_broker_port(norm)
    tcp_open = await asyncio.to_thread(is_port_open, port)
    if not tcp_open:
        return {
            "state": "DAEMON_DOWN",
            "port": port,
            "page_url": None,
            "pid": None,
        }

    try:
        probe_info = await cdp_session_status(norm)
    except Exception as e:
        logger.warning(f"cdp_session_status failed for {norm}: {e}")
        probe_info = {"state": "UNKNOWN", "url": None, "pid": None}

    raw_state = probe_info.get("state", "UNKNOWN")
    page_url = probe_info.get("url")
    daemon_pid = get_daemon_pid(norm)
    chrome_pid = probe_info.get("pid") or get_cdp_daemon_pid(port)
    pid = daemon_pid or chrome_pid

    # Distinguish OTP_PAGE from generic LOGIN_PAGE
    if raw_state == "LOGIN_PAGE":
        url_lower = (page_url or "").lower()
        if any(marker in url_lower for marker in ("/otp", "/twofa")):
            state = "OTP_PAGE"
        else:
            state = "LOGIN_PAGE"
    else:
        state = raw_state

    if state not in VALID_STATES:
        state = "UNKNOWN"

    return {
        "state": state,
        "port": port,
        "page_url": page_url,
        "pid": pid,
    }


async def ensure_daemon(broker: str, wait_s: float = 90.0) -> Dict[str, Any]:
    """Ensure the CDP daemon is ready without launching duplicate browsers.

    1. If port is already open and AUTHENTICATED -> status='already_up'.
    2. If port is open but not AUTHENTICATED -> fail-closed (return current state, do not spawn).
    3. If port is closed -> spawn daemon with start_new_session=True, poll until ready or timeout.

    Returns:
        {"status": str, "state": str, "port": int, "pid": Optional[int], "page_url": Optional[str], "log_tail": str}
    """
    norm = normalize_broker_slug(broker)
    port = get_broker_port(norm)

    async with _DaemonFileLock(norm):
        current = await daemon_state(norm)

        if current["state"] == "AUTHENTICATED":
            return {
                "status": "already_up",
                "state": "AUTHENTICATED",
                "port": port,
                "pid": current["pid"],
                "page_url": current["page_url"],
                "log_tail": get_log_tail(norm),
            }

        if current["state"] != "DAEMON_DOWN":
            # Port is open but tab is in non-authenticated state (LOGIN_PAGE, OTP_PAGE, NO_TARGET_TAB, UNKNOWN)
            # Fail-closed: Never spawn a second daemon over an active port.
            return {
                "status": current["state"],
                "state": current["state"],
                "port": port,
                "pid": current["pid"],
                "page_url": current["page_url"],
                "log_tail": get_log_tail(norm),
            }

        # Port is closed (DAEMON_DOWN) -> spawn daemon process
        log_dir = REPO_ROOT / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"daemon-{norm}.log"
        pid_file = REPO_ROOT / "data" / f"daemon-{norm}.pid"

        env = os.environ.copy()
        env["DISPLAY"] = env.get("DISPLAY") or ":0"

        log_fp = open(log_file, "a", encoding="utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "scripts/broker_cdp/session_daemon.py",
                norm,
                "300",
                cwd=str(REPO_ROOT),
                env=env,
                stdout=log_fp,
                stderr=log_fp,
                start_new_session=True,
            )
        finally:
            log_fp.close()

        try:
            with open(pid_file, "w", encoding="utf-8") as f:
                f.write(str(proc.pid))
        except OSError as e:
            logger.warning(f"Failed to write pidfile for {norm}: {e}")

        # Poll until AUTHENTICATED or early exit on login/otp or timeout
        deadline = time.monotonic() + max(0.01, float(wait_s))
        poll_interval = min(1.0, max(0.01, float(wait_s) / 2))

        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)

            st = await daemon_state(norm)
            if st["state"] == "AUTHENTICATED":
                return {
                    "status": "spawned",
                    "state": "AUTHENTICATED",
                    "port": port,
                    "pid": proc.pid,
                    "page_url": st["page_url"],
                    "log_tail": get_log_tail(norm),
                }

            # Return early if interaction is required
            if st["state"] in ("OTP_PAGE", "LOGIN_PAGE"):
                return {
                    "status": st["state"],
                    "state": st["state"],
                    "port": port,
                    "pid": proc.pid,
                    "page_url": st["page_url"],
                    "log_tail": get_log_tail(norm),
                }

            # Check if subprocess died
            if proc.returncode is not None:
                return {
                    "status": "crashed",
                    "state": "DAEMON_DOWN",
                    "port": port,
                    "pid": proc.pid,
                    "page_url": None,
                    "log_tail": get_log_tail(norm),
                }

        # Timeout reached
        final_st = await daemon_state(norm)
        return {
            "status": "timeout",
            "state": final_st.get("state", "UNKNOWN"),
            "port": port,
            "pid": proc.pid,
            "page_url": final_st.get("page_url"),
            "log_tail": get_log_tail(norm),
        }


async def restart_daemon(broker: str, wait_s: int = 90) -> Dict[str, Any]:
    """Safely kill existing daemon and Chrome instances holding the port, then ensure daemon.

    Kill order per contract C6:
    1. Kill daemon first via SIGTERM -> wait up to 10s -> SIGKILL (prevents keepalive loop from surviving).
    2. If port is still held by Chrome, send SIGTERM -> wait -> SIGKILL to Chrome.
    3. Clear pidfile, wait until port is closed, then call ensure_daemon.
    """
    norm = normalize_broker_slug(broker)
    port = get_broker_port(norm)

    daemon_pid = get_daemon_pid(norm)
    chrome_pid = get_cdp_daemon_pid(port) or get_pid_holding_port(port)

    # 1. Kill daemon python process first
    if daemon_pid:
        try:
            pgid = os.getpgid(daemon_pid)
            if pgid == daemon_pid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(daemon_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            try:
                os.kill(daemon_pid, signal.SIGTERM)
            except OSError:
                pass

        # Wait up to 10s for daemon to exit
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                os.kill(daemon_pid, 0)
            except OSError:
                daemon_pid = None
                break

        if daemon_pid:
            try:
                pgid = os.getpgid(daemon_pid)
                if pgid == daemon_pid:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    os.kill(daemon_pid, signal.SIGKILL)
            except OSError:
                pass

    # 2. Kill Chrome if still listening
    if not chrome_pid:
        chrome_pid = get_cdp_daemon_pid(port) or get_pid_holding_port(port)

    if chrome_pid:
        try:
            os.kill(chrome_pid, signal.SIGTERM)
        except OSError:
            pass

        for _ in range(6):
            await asyncio.sleep(0.5)
            try:
                os.kill(chrome_pid, 0)
            except OSError:
                chrome_pid = None
                break

        if chrome_pid:
            try:
                os.kill(chrome_pid, signal.SIGKILL)
            except OSError:
                pass

    # 3. Wait until port is closed
    for _ in range(10):
        if not is_port_open(port):
            break
        await asyncio.sleep(0.5)

    # 4. Remove stale pidfile
    pid_file = REPO_ROOT / "data" / f"daemon-{norm}.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except OSError:
            pass

    # 5. Re-launch via ensure_daemon
    return await ensure_daemon(norm, wait_s=wait_s)
