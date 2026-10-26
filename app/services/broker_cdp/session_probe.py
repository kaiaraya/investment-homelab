# -*- coding: utf-8 -*-
"""CDP read-only session probe for broker daemons.

Inspects whether running CDP daemons (9333/9334) hold authenticated tabs
without launching browsers, navigating, or triggering logins/OTPs.
"""
from datetime import datetime, timezone
import asyncio
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from scripts.broker_cdp.brokers import LOGIN_MARKERS, is_authenticated_path
from scripts.broker_cdp.client import (
    BROKER_CDP_PORTS,
    cdp_url_for,
    connect_cdp,
    is_cdp_available,
    resolve_target_tab,
)

logger = logging.getLogger("broker_cdp_session_probe")

DEFAULT_PURPOSES = {
    "kss": "streaming",
    "krungsri": "streaming",
    "lib": "portfolio",
    "liberator": "portfolio",
}


def get_cdp_daemon_pid(port: int) -> Optional[int]:
    """Find the main Chrome process PID listening on the remote debugging port.

    Scans /proc on Linux without spawning subprocesses.
    Filters out renderers, zygotes, and crashpad handlers.
    """
    if not port:
        return None
    try:
        proc_dir = "/proc"
        if not os.path.exists(proc_dir):
            return None
        port_arg = f"--remote-debugging-port={port}"
        for entry in os.listdir(proc_dir):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    raw = fh.read().decode(errors="replace")
                if port_arg in raw and "--type=" not in raw and ("chrome" in raw or "chromium" in raw):
                    return pid
            except (OSError, IOError):
                continue
    except Exception:
        pass
    return None


def _resolve_purpose(broker: str, purpose: Optional[str]) -> str:
    if purpose:
        return purpose.strip().lower()
    b_clean = (broker or "").strip().lower()
    return DEFAULT_PURPOSES.get(b_clean, "streaming")


async def cdp_session_status(broker: str, purpose: Optional[str] = None) -> Dict[str, Any]:
    """Inspect the live Chrome CDP session for a broker tab without modifying state.

    Enforces:
    - Strictly read-only: no browser launches, no page navigations, no logins/OTPs.
    - Timeout of 2s per step; daemon down returns DAEMON_DOWN (never raises).
    - State in: AUTHENTICATED | LOGIN_PAGE | NO_TARGET_TAB | DAEMON_DOWN | UNKNOWN

    Returns:
        {
            "broker": str,
            "purpose": str,
            "state": str,
            "daemon_up": bool,
            "port": int,
            "target_found": bool,
            "url": Optional[str],
            "url_path": Optional[str],
            "checked_at": str,
            "reason": str,
        }
    """
    b_raw = (broker or "").strip().lower()
    resolved_purpose = _resolve_purpose(b_raw, purpose)
    port = BROKER_CDP_PORTS.get(b_raw, 0)
    checked_at = datetime.now(timezone.utc).isoformat()
    pid = get_cdp_daemon_pid(port)

    result: Dict[str, Any] = {
        "broker": broker,
        "purpose": resolved_purpose,
        "state": "UNKNOWN",
        "daemon_up": False,
        "port": port,
        "pid": pid,
        "target_found": False,
        "url": None,
        "url_path": None,
        "checked_at": checked_at,
        "reason": "",
    }

    try:
        cdp_url = cdp_url_for(b_raw)
    except Exception as e:
        result["state"] = "UNKNOWN"
        result["reason"] = f"Invalid broker configuration: {e}"
        return result

    # 1. Daemon availability check (timeout 2s)
    try:
        daemon_ok = await asyncio.wait_for(
            asyncio.to_thread(is_cdp_available, cdp_url, 2.0),
            timeout=2.5,
        )
    except Exception:
        daemon_ok = False

    if not daemon_ok:
        result["state"] = "DAEMON_DOWN"
        result["daemon_up"] = False
        result["reason"] = f"CDP daemon on port {port} not reachable (timeout 2s)"
        return result

    result["daemon_up"] = True

    # 2. Attach over CDP (timeout 2s)
    pw = None
    try:
        pw, _browser, ctx = await asyncio.wait_for(
            connect_cdp(cdp_url, broker=b_raw),
            timeout=2.0,
        )
    except Exception as e:
        result["state"] = "DAEMON_DOWN"
        result["daemon_up"] = False
        result["reason"] = f"Failed to attach over CDP to port {port}: {e}"
        return result

    try:
        # 3. Resolve target tab (timeout 2s)
        client_broker = "liberator" if b_raw in ("lib", "liberator") else b_raw
        try:
            page = await asyncio.wait_for(
                resolve_target_tab(ctx, resolved_purpose, client_broker),
                timeout=2.0,
            )
        except Exception as e:
            page = None
            logger.debug("resolve_target_tab error: %s", e)

        if page is None:
            result["state"] = "NO_TARGET_TAB"
            result["target_found"] = False
            result["reason"] = f"No tab matching purpose '{resolved_purpose}' found on daemon"
            return result

        raw_url = page.url or ""
        parsed = urlparse(raw_url if "://" in raw_url else ("//" + raw_url))
        url_path = parsed.path or ""

        if raw_url in ("", "about:blank", "chrome://newtab/"):
            result["state"] = "NO_TARGET_TAB"
            result["target_found"] = False
            result["url"] = raw_url
            result["url_path"] = url_path
            result["reason"] = f"Target tab is empty ({raw_url})"
            return result

        result["target_found"] = True
        result["url"] = raw_url
        result["url_path"] = url_path

        # 4. Guard LOGIN_MARKERS first
        url_lower = raw_url.lower()
        path_lower = url_path.lower()
        if any(marker.lower() in path_lower or marker.lower() in url_lower for marker in LOGIN_MARKERS):
            result["state"] = "LOGIN_PAGE"
            result["reason"] = f"Target tab is at login/otp marker ({url_path})"
            return result

        # 5. Check AUTH_PATHS contract
        if is_authenticated_path(b_raw, resolved_purpose, raw_url):
            result["state"] = "AUTHENTICATED"
            result["reason"] = f"Target tab matches authenticated path ({url_path})"
            return result

        # 6. Fallback
        result["state"] = "UNKNOWN"
        result["reason"] = f"Target tab URL unrecognized ({url_path})"
        return result

    except Exception as e:
        result["state"] = "UNKNOWN"
        result["reason"] = f"Unexpected probe error: {e}"
        return result
    finally:
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass
