# -*- coding: utf-8 -*-
"""Liberator Persistent Chrome Session Daemon & Keep-Alive Service.

Keeps a Chrome instance running with DevTools Protocol (CDP) on port 9334,
handles Liberator login with 2FA OTP once, saves and reuses cookies from
data/liberator_session.json, opens target tabs, and sends periodic heartbeats.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.config import settings
from scripts.liberator.liberator_cdp_client import (
    DEFAULT_LIBERATOR_CDP_PORT,
    DEFAULT_LIBERATOR_CDP_URL,
    is_cdp_available,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("liberator_session_daemon")

PROFILE_DIR = os.path.abspath("data/liberator_chrome_profile")
LOG_FILE = os.path.abspath("data/liberator_chrome.log")
SESSION_FILE = os.path.abspath("data/liberator_session.json")


def launch_chrome_process(cdp_port: int = DEFAULT_LIBERATOR_CDP_PORT) -> Optional[subprocess.Popen]:
    """Launch Chrome with remote debugging on Liberator port."""
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
    logger.info(f"Launching Liberator Chrome: {' '.join(cmd)}")
    log_fp = open(LOG_FILE, "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_fp)

    cdp_url = f"http://127.0.0.1:{cdp_port}"
    for _ in range(30):
        if is_cdp_available(cdp_url, timeout=1.0):
            logger.info(f"Liberator Chrome DevTools Protocol ready at {cdp_url}")
            return proc
        time.sleep(1)

    raise TimeoutError(f"Chrome CDP did not become responsive on port {cdp_port} within 30 seconds.")


def _is_authenticated_landing(url: str) -> bool:
    """True when a Liberator URL is an authenticated page (off /login and off /otp).

    Matches the URL PATH, not the full URL: "trade" is a substring of the "webtrade"
    host, so a naive substring match would treat the OTP page (/otp) as authenticated.
    A bare root ("/" or "") is also rejected so an in-flight redirect never wins.
    """
    path = urlparse(url).path.lower()
    if path in ("", "/"):
        return False
    return "login" not in path and "otp" not in path


async def perform_initial_login(ctx: BrowserContext, page: Page, timeout_seconds: int = 300) -> bool:
    """Handle initial login or session resume for Liberator."""
    # 1. Fast path: check if existing cookies in data/liberator_session.json work
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            if cookies:
                await ctx.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from {SESSION_FILE}. Testing /Portfolio...")
                await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                if _is_authenticated_landing(page.url):
                    logger.info(f"Existing Liberator session is VALID! Landed on {page.url}")
                    return True
                logger.info("Saved cookies expired. Proceeding to fresh login...")
        except Exception as e:
            logger.debug(f"Cookie resume notice: {e}")

    # 2. Fresh login
    user = settings.LIBERATOR_USERNAME
    pwd = settings.LIBERATOR_PASSWORD
    login_url = "https://webtrade.liberator.co.th/login"

    logger.info(f"Navigating to {login_url}...")
    await page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)

    # Check if already authenticated
    if "login" not in page.url.lower():
        logger.info(f"Already logged in! Landed on {page.url}")
        return True

    logger.info("Filling Liberator credentials...")
    for user_sel in ["input[type='text']", "input[name*='user' i]", "#username"]:
        el = await page.query_selector(user_sel)
        if el and await el.is_visible():
            await el.fill(user)
            break

    for pass_sel in ["input[type='password']", "input[name*='pass' i]", "#password"]:
        el = await page.query_selector(pass_sel)
        if el and await el.is_visible():
            await el.fill(pwd)
            break

    # Click login button
    for submit_sel in ["button:has-text('เข้าสู่ระบบ')", "button:has-text('Login')", "button[type='submit']"]:
        btn = await page.query_selector(submit_sel)
        if btn and await btn.is_visible():
            await btn.click()
            logger.info("Clicked Liberator login. Waiting for OTP (LINE Relay / SMS / RDP)...")
            break

    # Wait for OTP submission and landing on Portfolio / Dashboard
    waited = 0
    while waited < timeout_seconds:
        if _is_authenticated_landing(page.url):
            logger.info(f"Liberator Login successful! Landed on: {page.url}")
            # Save cookies
            cookies = await ctx.cookies()
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies}, f, indent=2)
            logger.info(f"Persisted {len(cookies)} cookies to {SESSION_FILE}")
            return True

        if waited % 15 == 0:
            logger.info(f"Waiting for Liberator OTP confirmation... ({waited}s / {timeout_seconds}s) [URL: {page.url}]")
        await page.wait_for_timeout(3000)
        waited += 3

    logger.warning("Timed out waiting for Liberator login/OTP.")
    return False


async def open_target_tabs(ctx: BrowserContext):
    """Ensure Portfolio and Trade tabs are open."""
    # Match the URL PATH ("/trade"), not a bare substring: "trade" is a substring of
    # the "webtrade" host, so `"trade" in url` would make the Portfolio page itself
    # look like an already-open Trade tab and skip the open.
    has_trade = any("/trade" in p.url.lower() or "/order" in p.url.lower() for p in ctx.pages)
    if not has_trade:
        logger.info("Opening Liberator Trade tab...")
        new_page = await ctx.new_page()
        try:
            await new_page.goto("https://webtrade.liberator.co.th/Trade", wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            logger.debug(f"Trade tab open notice: {e}")


async def run_keepalive_loop(ctx: BrowserContext, interval_seconds: int = 300):
    """Periodic subtle activity to keep Liberator session alive."""
    logger.info(f"=== Liberator Session Keep-Alive active (ping every {interval_seconds}s) ===")
    cycle = 0
    while True:
        await asyncio.sleep(interval_seconds)
        cycle += 1
        active_tabs = len(ctx.pages)
        logger.info(f"[Heartbeat #{cycle}] Liberator active tabs: {active_tabs}")
        for idx, page in enumerate(ctx.pages):
            try:
                title = await page.title()
                await page.evaluate("() => ({ time: Date.now(), title: document.title })")
                logger.debug(f"  Tab {idx}: {title[:30]} ({page.url[:50]})")
            except Exception as e:
                logger.debug(f"  Tab {idx} ping error: {e}")


async def start_daemon(cdp_port: int = DEFAULT_LIBERATOR_CDP_PORT, keepalive_interval: int = 300):
    """Main Liberator daemon runner."""
    launch_chrome_process(cdp_port)
    cdp_url = f"http://127.0.0.1:{cdp_port}"

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(cdp_url)
    ctx = browser.contexts[0]
    initial_page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    logged_in = await perform_initial_login(ctx, initial_page)
    if logged_in:
        await open_target_tabs(ctx)

    await run_keepalive_loop(ctx, interval_seconds=keepalive_interval)


if __name__ == "__main__":
    interval = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 300
    try:
        asyncio.run(start_daemon(keepalive_interval=interval))
    except KeyboardInterrupt:
        logger.info("Liberator daemon stopped by user.")
