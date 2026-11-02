# -*- coding: utf-8 -*-
"""Per-broker config: CDP port, Chrome profile, login hook, target-tab hook.

The two session daemons shared almost everything except (a) the login flow and
(b) which target tabs to open. This module is the single place those differ.
"""
import asyncio
import json
import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from app.core.config import settings
from scripts.broker_cdp.otp_relay import check_line_otp_once, request_line_otp

logger = logging.getLogger("broker_cdp_brokers")

# ────────────────────────────────────────────────────────────────────────────
# Path Contract & Authenticated URL Specs
# ────────────────────────────────────────────────────────────────────────────

AUTH_PATHS = {
    ("kss", "streaming"): ["wme2.settrade.com/realtime/streaming7/StreamingPage"],
    ("kss", "sbl"):       ["krungsrisecurities.com/sblweb/MainSBL.aspx"],
    ("kss", "member"):    ["krungsrisecurities.com/th/member/"],
    ("lib", "portfolio"): ["webtrade.liberator.co.th/Market",
                           "webtrade.liberator.co.th/Portfolio",
                           "webtrade.liberator.co.th/Trade"],
}

LOGIN_MARKERS = ["/login", "login.aspx", "/signin", "/otp", "/twofa", "/member/login", "/auth/"]


def is_authenticated_path(broker: str, purpose: str, url: str) -> bool:
    """Check whether the given URL matches the authenticated path contract for broker/purpose.

    Enforces:
    1. Rejects if any LOGIN_MARKERS match (path or full URL).
    2. Rejects bare root paths (/ or empty).
    3. Matches host and path prefix against AUTH_PATHS for (broker, purpose).
    """
    if not url:
        return False

    url_clean = url.strip().lower()
    parsed = urlparse(url if "://" in url else ("//" + url))
    path_clean = (parsed.path or "").lower()

    # Guard LOGIN_MARKERS first (case-insensitive)
    for marker in LOGIN_MARKERS:
        m = marker.lower()
        if m in path_clean or m in url_clean:
            return False

    if path_clean in ("", "/"):
        return False

    b_key = "lib" if (broker or "").lower() in ("lib", "liberator") else (broker or "").lower()
    p_key = (purpose or "").lower()

    candidates = AUTH_PATHS.get((b_key, p_key))
    if not candidates:
        candidates = AUTH_PATHS.get(((broker or "").lower(), p_key))
    if not candidates:
        return False

    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    host_and_path = f"{netloc}{parsed.path}".lower()

    for auth_path in candidates:
        target = auth_path.lower()
        if target.startswith("www."):
            target = target[4:]
        if host_and_path.startswith(target):
            if target.endswith("/"):
                return True
            rem = host_and_path[len(target):]
            if rem == "" or rem[0] in ("/", "?", "#", "."):
                return True

    return False


# ────────────────────────────────────────────────────────────────────────────
# KSS — Settrade Streaming via Krungsri SSO (port 9333)
# ────────────────────────────────────────────────────────────────────────────

SSO_STREAMING_URL = "https://www.krungsrisecurities.com/Put_SSO_Settrade.aspx?Page=streaming"
SSO_SBL_START_URL = "https://www.krungsrisecurities.com/th/SBL/start.aspx"
SSO_SBL_DISCLAIMER_URL = "https://www.krungsrisecurities.com/th/disclaimer-sbl/Default.aspx?start=sbl"


# ────────────────────────────────────────────────────────────────────────────
# OTP prompt detection / fill — shared by every CDP login flow
# (selectors mirrored from app/browser/auth_driver.py::_detect_otp_prompt)
# ────────────────────────────────────────────────────────────────────────────

OTP_INPUT_SELECTORS = [
    "input[placeholder*='OTP' i]",
    "#otp",
    "input#otp",
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "#login_otp",
    "input#login_otp",
    "input[name='otp']",
    "input[type='text'][maxlength='6']",
    "input[type='tel'][maxlength='6']",
    "input#txtOTP",
    "input[name='txtOTP']",
]


async def _detect_otp_prompt(page: Page):
    """Return (is_otp, ref_code, otp_sel) — same detection logic as auth_driver."""
    otp_sel = None
    for sel in OTP_INPUT_SELECTORS:
        el = await page.query_selector(sel)
        if el and await el.is_visible():
            otp_sel = sel
            break
    body = await page.inner_text("body") if page else ""
    has_otp_text = any(
        k in body for k in ["รหัสอ้างอิง", "Ref", "OTP", "One Time Password", "SMS OTP"]
    )
    if not otp_sel and not has_otp_text:
        return False, None, None
    ref_code = None
    ref_match = re.search(
        r"(?:Ref(?:\.|erence)?|รหัสอ้างอิง)\s*[:：]?\s*([A-Za-z0-9]{3,8})", body, re.IGNORECASE
    )
    if ref_match:
        ref_code = ref_match.group(1).strip()
    return True, ref_code, otp_sel or "input[maxlength='6']"


async def _fill_otp_input(page: Page, otp_sel: str, otp_val: str) -> bool:
    """Fill the OTP input + best-effort submit. Never raises."""
    try:
        el = await page.query_selector(otp_sel)
        if not el or not await el.is_visible():
            return False
        await el.fill(otp_val)
        await asyncio.sleep(0.3)
        for submit_sel in [
            "button[type='submit']",
            "button:has-text('ยืนยัน')",
            "button:has-text('Confirm')",
            "button:has-text('Submit')",
        ]:
            btn = await page.query_selector(submit_sel)
            if btn and await btn.is_visible():
                await btn.click()
                logger.info("Clicked OTP submit button.")
                break
        return True
    except Exception as e:
        logger.warning(f"[CDP OTP] fill/submit failed: {e}")
        return False


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
        otp_requested = False
        while waited < timeout_seconds:
            body = await page.inner_text("body")
            if any(k in body for k in ["ยินดีต้อนรับ", "creditbalance"]) or "member" in page.url.lower():
                logger.info(f"Login successful! Landed on: {page.url}")
                return True

            # --- LINE OTP relay (แบบเดิม, non-blocking) ---
            is_otp, ref_code, otp_sel = await _detect_otp_prompt(page)
            if is_otp and not otp_requested:
                otp_requested = True
                logger.info(f"OTP prompt detected (ref={ref_code}). Requesting via LINE relay...")
                await request_line_otp("KRUNGSRI", ref=ref_code, timeout_seconds=timeout_seconds)
            elif is_otp:
                otp_val = await check_line_otp_once("KRUNGSRI")
                if otp_val and otp_sel:
                    await _fill_otp_input(page, otp_sel, otp_val)

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
    otp_requested = False
    while waited < timeout_seconds:
        if _is_authenticated_landing(page.url):
            logger.info(f"Liberator Login successful! Landed on: {page.url}")
            cookies = await ctx.cookies()
            with open(LIBERATOR_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"cookies": cookies}, f, indent=2)
            logger.info(f"Persisted {len(cookies)} cookies to {LIBERATOR_SESSION_FILE}")
            return True

        # --- LINE OTP relay (แบบเดิม, non-blocking) ---
        is_otp, ref_code, otp_sel = await _detect_otp_prompt(page)
        if is_otp and not otp_requested:
            otp_requested = True
            logger.info(f"OTP prompt detected (ref={ref_code}). Requesting via LINE relay...")
            await request_line_otp("LIBERATOR", ref=ref_code, timeout_seconds=timeout_seconds)
        elif is_otp:
            otp_val = await check_line_otp_once("LIBERATOR")
            if otp_val and otp_sel:
                await _fill_otp_input(page, otp_sel, otp_val)

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
