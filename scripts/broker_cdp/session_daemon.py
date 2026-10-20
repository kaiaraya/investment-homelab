# -*- coding: utf-8 -*-
"""Shared broker session daemon: launch Chrome (CDP), login once, keep alive.

Run directly (legacy argv form) or via `scripts/broker_probe.py --broker <slug> start-session`.

Usage:
    .venv/bin/python scripts/broker_cdp/session_daemon.py kss 300
    .venv/bin/python scripts/broker_cdp/session_daemon.py liberator 300
"""
import asyncio
import logging
import os
import subprocess
import sys
import time
from typing import Optional

from playwright.async_api import BrowserContext, async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.config import settings  # noqa: E402
from scripts.broker_cdp.client import cdp_url_for, is_cdp_available  # noqa: E402
from scripts.broker_cdp.brokers import BROKERS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("broker_cdp_session_daemon")


def launch_chrome_process(broker: str, cdp_port: Optional[int] = None) -> Optional[subprocess.Popen]:
    """Launch Chrome with remote debugging enabled (reuse existing instance if up)."""
    cfg = BROKERS[broker]
    port = cdp_port or cfg["port"]
    profile_dir = cfg["profile_dir"]
    log_file = cfg["log_file"]

    if is_cdp_available(f"http://127.0.0.1:{port}"):
        logger.info(f"Chrome is already running on CDP port {port}. Reusing existing instance.")
        return None

    os.makedirs(profile_dir, exist_ok=True)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    chrome_bin = settings.PLAYWRIGHT_CHROME_EXECUTABLE
    if not chrome_bin or not os.path.exists(chrome_bin):
        for candidate in ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]:
            if os.path.exists(candidate):
                chrome_bin = candidate
                break

    if not chrome_bin or not os.path.exists(chrome_bin):
        raise FileNotFoundError("Google Chrome or Chromium executable not found on host.")

    cmd = [
        chrome_bin,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1440,960",
        "about:blank",
    ]
    logger.info(f"Launching {cfg['label']} Chrome: {' '.join(cmd)}")
    log_fp = open(log_file, "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_fp)

    cdp_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        if is_cdp_available(cdp_url, timeout=1.0):
            logger.info(f"{cfg['label']} Chrome DevTools Protocol ready at {cdp_url}")
            return proc
        time.sleep(1)

    raise TimeoutError(f"Chrome CDP did not become responsive on port {port} within 30 seconds.")


async def run_keepalive_loop(ctx: BrowserContext, interval_seconds: int = 300, label: str = "") -> None:
    """Periodic subtle activity to keep the session alive."""
    logger.info(f"=== {label} Session Keep-Alive active (ping every {interval_seconds}s) ===")
    cycle = 0
    while True:
        await asyncio.sleep(interval_seconds)
        cycle += 1
        active_tabs = len(ctx.pages)
        logger.info(f"[Heartbeat #{cycle}] {label} active tabs: {active_tabs}")
        for idx, page in enumerate(ctx.pages):
            try:
                title = await page.title()
                await page.evaluate("() => ({ time: Date.now(), title: document.title })")
                logger.debug(f"  Tab {idx}: {title[:30]} ({page.url[:50]})")
            except Exception as e:
                logger.debug(f"  Tab {idx} ping error: {e}")


async def start_daemon(broker: str, keepalive_interval: int = 300) -> None:
    """Main daemon runner: launch Chrome, login once, open tabs, keep alive."""
    cfg = BROKERS[broker]
    launch_chrome_process(broker)

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url_for(broker))
    ctx = browser.contexts[0]
    initial_page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    logged_in = await cfg["login"](ctx, initial_page)
    if logged_in:
        await cfg["open_tabs"](ctx)

    await run_keepalive_loop(ctx, interval_seconds=keepalive_interval, label=cfg["label"])


if __name__ == "__main__":
    broker = sys.argv[1] if len(sys.argv) > 1 else "kss"
    interval = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 300
    if broker not in BROKERS:
        print(f"Unknown broker '{broker}'. Choose from: {', '.join(BROKERS)}")
        sys.exit(1)
    try:
        asyncio.run(start_daemon(broker, keepalive_interval=interval))
    except KeyboardInterrupt:
        logger.info(f"{BROKERS[broker]['label']} daemon stopped by user.")
