# -*- coding: utf-8 -*-
"""KSS Persistent Chrome Session Daemon & Keep-Alive Service.

Keeps a Chrome instance running with DevTools Protocol (CDP) enabled,
manages Krungsri SSO login once with OTP, opens target tabs (Streaming, SBL),
and performs lightweight periodic heartbeats to prevent session timeout.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from typing import Optional

from playwright.async_api import BrowserContext, Page, async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.config import settings
from scripts.kss.cdp_client import DEFAULT_CDP_PORT, DEFAULT_CDP_URL, is_cdp_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kss_session_daemon")

PROFILE_DIR = os.path.abspath("data/kss_chrome_profile")
LOG_FILE = os.path.abspath("data/kss_chrome.log")


def launch_chrome_process(cdp_port: int = DEFAULT_CDP_PORT) -> subprocess.Popen:
    """Launch Chrome with remote debugging enabled."""
    if is_cdp_available(f"http://127.0.0.1:{cdp_port}"):
        logger.info(f"Chrome is already running on CDP port {cdp_port}. Reusing existing instance.")
        return None

    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

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
        f"--remote-debugging-port={cdp_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1440,960",
        "about:blank",
    ]
    logger.info(f"Launching Chrome: {' '.join(cmd)}")
    log_fp = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_fp)

    # Wait for CDP to respond
    cdp_url = f"http://127.0.0.1:{cdp_port}"
    for _ in range(30):
        if is_cdp_available(cdp_url, timeout=1.0):
            logger.info(f"Chrome DevTools Protocol ready at {cdp_url}")
            return proc
        time.sleep(1)

    raise TimeoutError(f"Chrome CDP did not become responsive on port {cdp_port} within 30 seconds.")


async def perform_initial_login(page: Page, timeout_seconds: int = 300) -> bool:
    """Handle initial Krungsri SSO login and wait for OTP completion."""
    u, p = settings.KRUNGSRI_USERNAME, settings.KRUNGSRI_PASSWORD
    login_url = settings.KRUNGSRI_LOGIN_URL or "https://www.krungsrisecurities.com"

    logger.info(f"Navigating to {login_url}...")
    await page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)

    body = await page.inner_text("body")
    is_already_in = any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) or "member" in page.url.lower()

    if not is_already_in:
        logger.info("Filling Krungsri credentials...")
        filled_user = False
        for sel in ["#login_username", "input[name*='user' i]", "#txtUsername"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(u)
                filled_user = True
                break

        for sel in ["#login_password", "input[name*='pass' i]", "#txtPassword"]:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.fill(p)
                break

        if filled_user:
            for submit_sel in ["#login", "button[type='submit']", "input[type='submit']"]:
                btn = await page.query_selector(submit_sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    logger.info("Clicked login button. Waiting for OTP (SMS / LINE Relay / RDP)...")
                    break

        # Await OTP and login transition
        waited = 0
        while waited < timeout_seconds:
            body = await page.inner_text("body")
            if any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) or "member" in page.url.lower():
                logger.info(f"Login successful! Landed on: {page.url}")
                return True
            if waited % 15 == 0:
                logger.info(f"Waiting for OTP confirmation... ({waited}s / {timeout_seconds}s) [URL: {page.url}]")
            await page.wait_for_timeout(3000)
            waited += 3

        logger.warning("Timed out waiting for login/OTP completion.")
        return False

    logger.info("Already logged in to Krungsri SSO!")
    return True


SSO_STREAMING_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming"


async def open_target_tabs(ctx: BrowserContext):
    """Open the Settrade Streaming tab via the direct SSO endpoint.

    The 'โปรแกรม Streaming' link sits in a hidden dropdown (never visible)
    and the popup() JS fallback throws ReferenceError, so navigate the SSO
    URL directly instead.
    """
    if any("streamingpage" in p.url.lower() for p in ctx.pages):
        logger.info("Streaming tab already open.")
        return
    logger.info("Opening Settrade Streaming tab via direct SSO URL...")
    page = await ctx.new_page()
    try:
        await page.goto(SSO_STREAMING_URL, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        logger.warning(f"SSO navigation error: {e}")
    for _ in range(30):
        await asyncio.sleep(2)
        for p in ctx.pages:
            if "streamingpage" in p.url.lower():
                logger.info(f"Streaming tab opened: {p.url}")
                return
    logger.warning("Streaming tab did not appear after SSO navigation.")


async def run_keepalive_loop(ctx: BrowserContext, interval_seconds: int = 300):
    """Periodic subtle activity to keep session alive."""
    logger.info(f"=== KSS Session Keep-Alive active (ping every {interval_seconds}s) ===")
    cycle = 0
    while True:
        await asyncio.sleep(interval_seconds)
        cycle += 1
        active_tabs = len(ctx.pages)
        logger.info(f"[Heartbeat #{cycle}] Active tabs: {active_tabs}")
        for idx, page in enumerate(ctx.pages):
            try:
                # Lightweight DOM touch
                title = await page.title()
                await page.evaluate("() => ({ time: Date.now(), title: document.title })")
                logger.debug(f"  Tab {idx}: {title[:30]} ({page.url[:50]})")
            except Exception as e:
                logger.debug(f"  Tab {idx} ping error: {e}")


async def start_daemon(cdp_port: int = DEFAULT_CDP_PORT, keepalive_interval: int = 300):
    """Main daemon runner."""
    launch_chrome_process(cdp_port)
    cdp_url = f"http://127.0.0.1:{cdp_port}"

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url)
    ctx = browser.contexts[0]
    initial_page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    logged_in = await perform_initial_login(initial_page)
    if logged_in:
        await open_target_tabs(ctx)

    await run_keepalive_loop(ctx, interval_seconds=keepalive_interval)


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 300
    try:
        asyncio.run(start_daemon(keepalive_interval=interval))
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user.")
