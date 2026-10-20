# -*- coding: utf-8 -*-
"""Per-broker config: CDP port, Chrome profile, login hook, target-tab hook.

The two session daemons shared almost everything except (a) the login flow and
(b) which target tabs to open. This module is the single place those differ.
"""
import asyncio
import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from app.core.config import settings

logger = logging.getLogger("broker_cdp_brokers")

# ────────────────────────────────────────────────────────────────────────────
# KSS — Settrade Streaming via Krungsri SSO (port 9333)
# ────────────────────────────────────────────────────────────────────────────

SSO_STREAMING_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming"
SSO_SBL_START_URL = "https://www.krungsrisecurities.com/th/SBL/start.aspx"
SSO_SBL_DISCLAIMER_URL = "https://www.krungsrisecurities.com/th/disclaimer-sbl/Default.aspx?start=sbl"


async def kss_login(ctx: BrowserContext, page: Page, timeout_seconds: int = 300) -> bool:
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


async def kss_open_tabs(ctx: BrowserContext):
    """Ensure both Streaming and SBL Real Time tabs are opened from the authenticated session."""
    has_streaming = any("streamingpage" in p.url.lower() or "settrade" in p.url.lower() for p in ctx.pages)
    if not has_streaming:
        logger.info("Opening Settrade Streaming tab via direct SSO URL...")
        page_streaming = await ctx.new_page()
        try:
            await page_streaming.goto(SSO_STREAMING_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            logger.warning(f"Streaming SSO navigation error: {e}")
        for _ in range(15):
            await asyncio.sleep(2)
            if any("streamingpage" in p.url.lower() for p in ctx.pages):
                logger.info("Streaming tab opened successfully.")
                break
    else:
        logger.info("Streaming tab already open.")

    has_sbl = any(
        "sblweb" in p.url.lower() or "mainsbl" in p.url.lower() or "disclaimer-sbl" in p.url.lower()
        for p in ctx.pages
    )
    if not has_sbl:
        logger.info("Opening SBL Real Time tab via start endpoint...")
        page_sbl = await ctx.new_page()
        try:
            await page_sbl.goto(SSO_SBL_START_URL, wait_until="domcontentloaded", timeout=45000)
            await page_sbl.wait_for_timeout(3000)
            if "disclaimer-sbl" in page_sbl.url.lower():
                logger.info("Landed on SBL Disclaimer page. Clicking SBL Real Time button...")
                for sel in [
                    "a:has-text('SBL Real Time')",
                    "a[href*='start.aspx']",
                    "img[src*='sbl' i]",
                    "#sbls",
                ]:
                    btn = await page_sbl.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        logger.info(f"Clicked SBL trigger: {sel}")
                        break
        except Exception as e:
            logger.warning(f"SBL SSO navigation error: {e}")

        for _ in range(15):
            await asyncio.sleep(2)
            for p in ctx.pages:
                if "sblweb" in p.url.lower() or "mainsbl" in p.url.lower():
                    logger.info(f"SBL Real Time tab opened: {p.url}")
                    return
        logger.info("SBL tab opened (or disclaimer page active).")
    else:
        logger.info("SBL Real Time tab already open.")


# ────────────────────────────────────────────────────────────────────────────
# Liberator — WebTrade (port 9334)
# ────────────────────────────────────────────────────────────────────────────

LIBERATOR_LOGIN_URL = "https://webtrade.liberator.co.th/login"
LIBERATOR_PORTFOLIO_URL = "https://webtrade.liberator.co.th/Portfolio"
LIBERATOR_TRADE_URL = "https://webtrade.liberator.co.th/Trade"
LIBERATOR_SESSION_FILE = os.path.abspath("data/liberator_session.json")


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


async def liberator_login(ctx: BrowserContext, page: Page, timeout_seconds: int = 300) -> bool:
    """Handle initial login or session resume for Liberator."""
    # 1. Fast path: check if existing cookies in data/liberator_session.json work
    if os.path.exists(LIBERATOR_SESSION_FILE):
        try:
            with open(LIBERATOR_SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            if cookies:
                await ctx.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} cookies from {LIBERATOR_SESSION_FILE}. Testing /Portfolio...")
                await page.goto(LIBERATOR_PORTFOLIO_URL, wait_until="domcontentloaded", timeout=20000)
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

    logger.info(f"Navigating to {LIBERATOR_LOGIN_URL}...")
    await page.goto(LIBERATOR_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)

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

    for submit_sel in ["button:has-text('เข้าสู่ระบบ')", "button:has-text('Login')", "button[type='submit']"]:
        btn = await page.query_selector(submit_sel)
        if btn and await btn.is_visible():
            await btn.click()
            logger.info("Clicked Liberator login. Waiting for OTP (LINE Relay / SMS / RDP)...")
            break

    waited = 0
    while waited < timeout_seconds:
        if _is_authenticated_landing(page.url):
            logger.info(f"Liberator Login successful! Landed on: {page.url}")
            cookies = await ctx.cookies()
            with open(LIBERATOR_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies}, f, indent=2)
            logger.info(f"Persisted {len(cookies)} cookies to {LIBERATOR_SESSION_FILE}")
            return True

        if waited % 15 == 0:
            logger.info(f"Waiting for Liberator OTP confirmation... ({waited}s / {timeout_seconds}s) [URL: {page.url}]")
        await page.wait_for_timeout(3000)
        waited += 3

    logger.warning("Timed out waiting for Liberator login/OTP.")
    return False


async def liberator_open_tabs(ctx: BrowserContext):
    """Ensure Portfolio and Trade tabs are open."""
    # Match the URL PATH ("/trade"), not a bare substring: "trade" is a substring of
    # the "webtrade" host, so `"trade" in url` would make the Portfolio page itself
    # look like an already-open Trade tab and skip the open.
    has_trade = any("/trade" in p.url.lower() or "/order" in p.url.lower() for p in ctx.pages)
    if not has_trade:
        logger.info("Opening Liberator Trade tab...")
        new_page = await ctx.new_page()
        try:
            await new_page.goto(LIBERATOR_TRADE_URL, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            logger.debug(f"Trade tab open notice: {e}")


# ────────────────────────────────────────────────────────────────────────────
# Registry
# ────────────────────────────────────────────────────────────────────────────

BROKERS = {
    "kss": {
        "label": "KSS",
        "port": 9333,
        "profile_dir": os.path.abspath("data/kss_chrome_profile"),
        "log_file": os.path.abspath("data/kss_chrome.log"),
        "login": kss_login,
        "open_tabs": kss_open_tabs,
        "targets": ["streaming", "sbl", "sso", "any"],
        "default_target": "streaming",
        "probe_prefix": "probe",  # data/probes/probe_<target>_<stamp>.json
        "handoff_prefix": "PROBE",  # docs/handoff/PROBE-<TARGET>-<stamp>.md
    },
    "liberator": {
        "label": "Liberator",
        "port": 9334,
        "profile_dir": os.path.abspath("data/liberator_chrome_profile"),
        "log_file": os.path.abspath("data/liberator_chrome.log"),
        "login": liberator_login,
        "open_tabs": liberator_open_tabs,
        "targets": ["portfolio", "trade", "market", "any"],
        "default_target": "portfolio",
        "probe_prefix": "probe_liberator",
        "handoff_prefix": "PROBE-LIBERATOR",
    },
}
