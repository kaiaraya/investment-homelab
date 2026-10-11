"""
Remote Model Context Protocol (MCP) Server for Investment Homelab.
Enables AI Agents on remote Tailscale devices (e.g. Antigravity IDE) to:
1. Inspect Settrade Click2Win & Krungsri TradeMan browser sessions, DOM, and screenshots.
2. Query live portfolio holdings and balances across both platforms (Equity & TFEX).
3. Safely execute orders on Click2Win sandbox, view open orders, modify prices, and cancel orders.
4. Enforce Read-Only safety guardrail on Krungsri live accounts.
5. Inquire SBL borrowable inventory and monitor SET market regimes.
"""

import os
import re
import sys
import base64
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

from mcp.server.mcpserver import MCPServer
from mcp.server.sse import TransportSecuritySettings

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.click2win_auth_driver import click2win_auth_driver
from app.browser.click2win_driver import click2win_driver
from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.browser.trademan_simulator import virtual_simulator
from app.browser.popup_manager import popup_manager
from app.services.portfolio_overview_service import PortfolioOverviewService
from app.services.market_monitor_service import market_monitor_service
from app.services.validator import PreTradeValidator
from app.services.trade_dispatcher import trade_dispatcher
from app.services.workflow_engine import workflow_engine
from app.core.events import event_bus
from app.schemas.auth import OTPPayload, OTPSource

logger = logging.getLogger("RemoteMCPServer")

# Background Krungsri login task tracker
_active_krungsri_login_task: Optional[asyncio.Task] = None

# Initialize MCP Server instance
mcp_server = MCPServer(name="InvestmentHomelab-TradingGateway")
portfolio_service = PortfolioOverviewService()
order_validator = PreTradeValidator()

TAILSCALE_HOST = "100.88.217.33"
FASTAPI_PORT = 8000
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "data", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


# ==============================================================================
# Helper Functions for Platform Routing
# ==============================================================================

def resolve_platform(platform: Optional[str] = None) -> str:
    """
    Resolves user-supplied platform string to internal platform key ('CLICK2WIN' or 'TRADEMAN').
    Defaults to settings.TRADING_PLATFORM if not provided.
    """
    if not platform:
        return getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").upper().strip()
    p = platform.upper().strip()
    if p in ["KRUNGSRI", "TRADEMAN"]:
        return "TRADEMAN"
    if p in ["CLICK2WIN", "C2W"]:
        return "CLICK2WIN"
    return p


def get_platform_drivers(platform: Optional[str] = None):
    """Returns (driver, auth_driver, human_readable_label) for the given platform."""
    plat = resolve_platform(platform)
    if plat == "TRADEMAN":
        return trademan_driver, auth_driver, "KRUNGSRI (TradeMan)"
    return click2win_driver, click2win_auth_driver, "CLICK2WIN (Sandbox)"


# ==============================================================================
# 1. BROWSER & VISUAL INSPECTION TOOLS
# ==============================================================================

@mcp_server.tool()
async def browser_open(
    platform: Optional[str] = None,
    url: Optional[str] = None,
    headed: bool = False
) -> str:
    """
    Opens or attaches to the Google Chrome browser session on Home-lab.
    Restores saved session cookies if available.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    - url: Optional target URL (defaults to platform streaming or trademan page)
    - headed: If True, opens visible window on home-lab display (:0). Default is False (headless).
    """
    settings.PLAYWRIGHT_HEADLESS = not headed
    if headed and "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"

    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)
    streaming_c2w = "https://click2win.settrade.com/realtime/streaming7/StreamingPage.jsp"
    default_url = streaming_c2w if plat == "CLICK2WIN" else getattr(settings, "TRADEMAN_URL", "https://trademan.in.th")
    target_url = url or default_url

    page = await auth.launch_browser(resume_state=True)
    if not auth.is_authenticated:
        await auth.verify_saved_session()

    if target_url and (page.url != target_url and "StreamingPage" not in page.url):
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
        except Exception as e:
            logger.warning(f"Initial navigation notice: {e}")

    await popup_manager.dismiss_popups(page)
    title = await page.title()
    mode_str = "Headed (Visible on Desktop)" if headed else "Headless (Background)"
    return (
        f"✅ Chrome Browser initialized successfully ({mode_str})\n"
        f"• Platform: {label}\n"
        f"• URL: {page.url}\n"
        f"• Title: '{title}'\n"
        f"• Authenticated Session: {auth.is_authenticated}"
    )


@mcp_server.tool()
async def browser_screenshot(name: Optional[str] = None, platform: Optional[str] = None) -> str:
    """
    Captures a high-resolution screenshot of the active browser page on Home-lab.
    Returns:
    1. Clickable Tailscale HTTP URL to view in browser.
    2. Base64 data URI image for direct visual rendering in remote IDEs.
    - name: Optional descriptive name for the screenshot
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    page = auth.page
    if not page or (hasattr(page, "is_closed") and page.is_closed()):
        page = await auth.launch_browser(resume_state=True)

    base_name = name or f"remote_snap_{plat.lower()}_{int(datetime.now(timezone.utc).timestamp())}"
    clean_name = re.sub(r'[^\w\-]', '_', base_name)
    file_name = f"{clean_name}.png"
    out_path = os.path.join(SCREENSHOT_DIR, file_name)

    await page.screenshot(path=out_path, full_page=False)

    # Read image bytes for Base64 encoding
    with open(out_path, "rb") as f:
        img_bytes = f.read()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")

    http_url = f"http://{TAILSCALE_HOST}:{FASTAPI_PORT}/screenshots/{file_name}"

    return (
        f"📸 Screenshot captured successfully ({label}):\n"
        f"• Tailscale URL: {http_url}\n"
        f"• Local Path: {out_path}\n"
        f"• Active Page: {page.url}\n\n"
        f"![Screenshot]({http_url})\n\n"
        f"Base64 Data URI:\n`data:image/png;base64,{b64_data}`"
    )


@mcp_server.tool()
async def browser_snapshot(max_elements: int = 50, platform: Optional[str] = None) -> str:
    """
    Extracts interactive DOM elements (buttons, inputs, links, tables) with clean CSS selectors and visible text.
    - max_elements: Maximum interactive elements to return (default: 50).
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    page = auth.page
    if not page or (hasattr(page, "is_closed") and page.is_closed()):
        page = await auth.launch_browser(resume_state=True)

    await popup_manager.dismiss_popups(page)

    elements = await page.evaluate("""() => {
        const items = [];
        const interactive = document.querySelectorAll('button, a, input, select, [role="button"], tr[data-symbol], th');
        for (let i = 0; i < interactive.length; i++) {
            const el = interactive[i];
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden') {
                let selector = el.id ? '#' + el.id : (el.name ? `input[name="${el.name}"]` : el.tagName.toLowerCase());
                if (el.innerText && el.innerText.trim().length > 0 && el.innerText.trim().length < 30) {
                    selector += `:has-text("${el.innerText.trim()}")`;
                }
                items.push({
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.placeholder || '').trim().replace(/\\s+/g, ' ').slice(0, 50),
                    selector: selector,
                    type: el.type || ''
                });
            }
        }
        return items;
    }""")

    limited = elements[:max_elements]
    lines = [f"DOM Snapshot ({label}): Found {len(elements)} visible elements (showing {len(limited)}):"]
    for i, el in enumerate(limited, 1):
        txt = f" (text: '{el['text']}')" if el['text'] else ""
        lines.append(f"{i:2d}. <{el['tag']}> {el['selector']}{txt}")

    return "\n".join(lines)


@mcp_server.tool()
async def browser_click(selector: str, platform: Optional[str] = None) -> str:
    """
    Clicks an element specified by CSS selector or text with automatic popup dismiss checks.
    - selector: CSS selector or text selector (e.g. 'button:has-text("Portfolio")')
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    page = auth.page
    if not page or (hasattr(page, "is_closed") and page.is_closed()):
        page = await auth.launch_browser(resume_state=True)

    await popup_manager.dismiss_popups(page)
    el = await page.wait_for_selector(selector, state="visible", timeout=8000)
    if not el:
        return f"❌ Element not found or not visible: '{selector}' on {label}"
    await el.click()
    await asyncio.sleep(0.5)
    await popup_manager.dismiss_popups(page)
    return f"✅ Clicked successfully: '{selector}' on {label}"


@mcp_server.tool()
async def browser_navigate(url: str, platform: Optional[str] = None) -> str:
    """
    Navigates the active browser page to a specific URL.
    - url: Destination URL.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    page = auth.page
    if not page or (hasattr(page, "is_closed") and page.is_closed()):
        page = await auth.launch_browser(resume_state=True)

    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    await popup_manager.dismiss_popups(page)
    return f"✅ Navigated to {url} on {label}. Title: '{await page.title()}'"


# ==============================================================================
# 2. ACCOUNT, PORTFOLIO & SESSION TOOLS (Dual-Platform)
# ==============================================================================

@mcp_server.tool()
async def check_session(platform: Optional[str] = None) -> str:
    """
    Checks active login status, session cookies, account equity, and SET index values.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    is_auth = await auth.verify_saved_session()
    acc = await driver.scrape_account_summary()
    url = auth.page.url if auth.page and not (hasattr(auth.page, "is_closed") and auth.page.is_closed()) else "N/A"

    if plat == "CLICK2WIN":
        return (
            f"📊 Click2Win Session & Account Status:\n"
            f"• Platform: {label}\n"
            f"• Authenticated: {'✅ YES' if is_auth else '❌ NO (Session Expired or Inactive)'}\n"
            f"• Active URL: {url}\n"
            f"• Line Available: ฿{acc.get('excess_equity', 0):,.2f}\n"
            f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}"
        )
    else:
        market = await trademan_driver.scrape_set_index_summary()
        return (
            f"📊 Krungsri TradeMan Session & Account Status:\n"
            f"• Platform: {label}\n"
            f"• Authenticated: {'✅ YES' if is_auth else '❌ NO (Session Expired or Inactive)'}\n"
            f"• Active URL: {url}\n"
            f"• Excess Equity (EE): ฿{acc.get('excess_equity', 0):,.2f}\n"
            f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}\n"
            f"• Line Available: ฿{acc.get('line_available', 0):,.2f}\n"
            f"• SET Index: {market.get('current_index', 0):,.2f} ({market.get('pct_change', 0):+.2f}%)"
        )


@mcp_server.tool()
async def trademan_check_session(platform: Optional[str] = None) -> str:
    """Backwards-compatible alias for check_session, defaulting to Krungsri TradeMan."""
    return await check_session(platform=platform or "TRADEMAN")


@mcp_server.tool()
async def login_broker_session(platform: Optional[str] = None) -> str:
    """
    Performs initial or refresh login to generate and store browser cookie sessions.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    For Click2Win: Uses .env credentials to complete zero-OTP login and saves session to data/click2win_session.json.
    For Krungsri: Initiates login using .env credentials, detects 2FA SMS prompt, and returns the broker Ref Code so submit_otp_code can be called.
    """
    global _active_krungsri_login_task
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    if plat == "CLICK2WIN":
        if await auth.verify_saved_session():
            acc = await driver.scrape_account_summary()
            return (
                f"✅ Click2Win session is already active and authenticated!\n"
                f"• Platform: {label}\n"
                f"• Session file: {settings.CLICK2WIN_SESSION_PATH}\n"
                f"• Active URL: {auth.current_url or 'N/A'}\n"
                f"• Excess Equity: ฿{acc.get('excess_equity', 0):,.2f}\n"
                f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}"
            )

        if not settings.CLICK2WIN_USERNAME or not settings.CLICK2WIN_PASSWORD:
            return "❌ Error: CLICK2WIN_USERNAME or CLICK2WIN_PASSWORD is not configured in .env on Home-lab."

        logger.info(f"Triggering Click2Win automated login for user {settings.CLICK2WIN_USERNAME}...")
        try:
            res = await auth.login(
                username=settings.CLICK2WIN_USERNAME,
                password=settings.CLICK2WIN_PASSWORD,
                pin=settings.CLICK2WIN_PIN
            )
            if getattr(res, "success", False):
                acc = await driver.scrape_account_summary()
                return (
                    f"✅ Click2Win Login Successful!\n"
                    f"• Platform: {label}\n"
                    f"• Session cookie saved to: {settings.CLICK2WIN_SESSION_PATH}\n"
                    f"• Active URL: {auth.current_url}\n"
                    f"• Excess Equity: ฿{acc.get('excess_equity', 0):,.2f}\n"
                    f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}\n"
                    f"• Paper trading sandbox is ready for orders."
                )
            else:
                msg = getattr(res, "message", "Unknown error")
                return f"❌ Click2Win login failed: {msg}. Please check credentials or inspect /screenshots/."
        except Exception as e:
            return f"❌ Exception during Click2Win login: {str(e)}"

    else:
        # Krungsri TradeMan
        if await auth.verify_saved_session():
            acc = await driver.scrape_account_summary()
            return (
                f"✅ Krungsri TradeMan session is already active and authenticated!\n"
                f"• Platform: {label}\n"
                f"• Session file: {settings.SESSION_STATE_PATH}\n"
                f"• Active URL: {auth.current_url or 'N/A'}\n"
                f"• Excess Equity: ฿{acc.get('excess_equity', 0):,.2f}\n"
                f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}\n"
                f"• No re-login or OTP needed."
            )

        if not settings.KRUNGSRI_USERNAME or not settings.KRUNGSRI_PASSWORD:
            return "❌ Error: KRUNGSRI_USERNAME or KRUNGSRI_PASSWORD is not configured in .env on Home-lab."

        # If already running and awaiting OTP
        if _active_krungsri_login_task and not _active_krungsri_login_task.done() and auth.status == "AWAITING_OTP":
            ref = auth.current_ref or "N/A"
            return (
                f"🔑 Krungsri 2FA SMS OTP is already awaiting input!\n"
                f"• Broker Ref Code: [{ref}]\n"
                f"• Status: AWAITING_OTP\n"
                f"• Please check SMS on your phone and run:\n"
                f"  submit_otp_code(otp=\"XXXXXX\")"
            )

        logger.info("Initiating Krungsri TradeMan automated login...")
        _active_krungsri_login_task = asyncio.create_task(
            auth.login(
                username=settings.KRUNGSRI_USERNAME,
                password=settings.KRUNGSRI_PASSWORD
            )
        )

        # Poll for up to 15 seconds to detect OTP screen or direct authentication
        for _ in range(30):
            await asyncio.sleep(0.5)
            if _active_krungsri_login_task.done():
                exc = _active_krungsri_login_task.exception()
                if exc:
                    return f"❌ Krungsri login failed: {exc}"
                res = _active_krungsri_login_task.result()
                if getattr(res, "success", False):
                    return (
                        f"✅ Krungsri TradeMan Login Successful!\n"
                        f"• Platform: {label}\n"
                        f"• Session saved to: {settings.SESSION_STATE_PATH}\n"
                        f"• Active URL: {auth.current_url}"
                    )
                else:
                    return f"❌ Krungsri login ended without success: {getattr(res, 'message', 'Unknown error')}"

            if auth.status == "AWAITING_OTP":
                ref = auth.current_ref or "N/A"
                return (
                    f"🔑 2FA SMS OTP Required for Krungsri Securities!\n"
                    f"• Platform: {label}\n"
                    f"• Status: AWAITING_OTP\n"
                    f"• Broker Ref Code: [{ref}]\n"
                    f"• Next Action: Please check the SMS on your mobile phone for Ref Code [{ref}], and call:\n"
                    f"  submit_otp_code(otp=\"XXXXXX\")\n"
                    f"• Note: If KDE Connect is active on your phone, the OTP will be relayed automatically."
                )

        return (
            f"⏳ Krungsri login request dispatched.\n"
            f"• Current Status: {auth.status}\n"
            f"• Browser is loading portal. Call check_session(platform='KRUNGSRI') or login_broker_session(platform='KRUNGSRI') in a few seconds."
        )


@mcp_server.tool()
async def submit_otp_code(otp: str) -> str:
    """
    Submits a 6-digit 2FA SMS OTP to complete Krungsri Securities login.
    - otp: 6-digit numeric string received via SMS
    """
    global _active_krungsri_login_task
    clean_otp = str(otp).strip()
    if not (clean_otp.isdigit() and len(clean_otp) == 6):
        return f"❌ Invalid OTP format: '{otp}'. OTP must be exactly 6 numeric digits (e.g., '123456')."

    if auth_driver.is_authenticated:
        return (
            f"ℹ️ Krungsri TradeMan is already authenticated and active.\n"
            f"• URL: {auth_driver.current_url or 'N/A'}\n"
            f"• No OTP submission needed."
        )

    if auth_driver.status != "AWAITING_OTP" and (not _active_krungsri_login_task or _active_krungsri_login_task.done()):
        return (
            f"⚠️ No active Krungsri login flow currently awaiting OTP (Current status: {auth_driver.status}).\n"
            f"Please call login_broker_session(platform='KRUNGSRI') first to initiate login."
        )

    ref = auth_driver.current_ref or "N/A"
    logger.info(f"Submitting 6-digit OTP for Ref [{ref}] via MCP tool...")

    await event_bus.publish_otp(
        OTPPayload(
            source=OTPSource.API_MANUAL,
            otp=clean_otp,
            ref=auth_driver.current_ref
        )
    )

    # Wait up to 15 seconds for login task to complete or auth status to become AUTHENTICATED
    for _ in range(30):
        await asyncio.sleep(0.5)
        if auth_driver.is_authenticated or auth_driver.status == "AUTHENTICATED":
            return (
                f"✅ Krungsri TradeMan 2FA OTP Accepted & Session Established!\n"
                f"• Platform: KRUNGSRI (TradeMan Live)\n"
                f"• Session state saved to: {settings.SESSION_STATE_PATH}\n"
                f"• Active URL: {auth_driver.current_url}\n"
                f"• You can now use all portfolio and trading inspection tools."
            )
        if _active_krungsri_login_task and _active_krungsri_login_task.done():
            exc = _active_krungsri_login_task.exception()
            if exc:
                return f"❌ Krungsri login failed after OTP submission: {exc}"
            res = _active_krungsri_login_task.result()
            if getattr(res, "success", False):
                return (
                    f"✅ Krungsri TradeMan Login Successful!\n"
                    f"• Session saved to: {settings.SESSION_STATE_PATH}\n"
                    f"• Active URL: {auth_driver.current_url}"
                )
            else:
                msg = getattr(res, "message", "Unknown error")
                return f"❌ Krungsri login failed: {msg}"

    return (
        f"⏳ OTP '{clean_otp[:2]}****' submitted for Ref [{ref}].\n"
        f"• Status: {auth_driver.status}\n"
        f"• Processing SSO navigation. Call check_session(platform='KRUNGSRI') in a few seconds to verify status."
    )


@mcp_server.tool()
async def trademan_submit_otp(otp: str) -> str:
    """Backwards-compatible alias for submit_otp_code."""
    return await submit_otp_code(otp=otp)


@mcp_server.tool()
async def get_portfolio_overview(
    platform: Optional[str] = None,
    account_type: Optional[str] = None
) -> str:
    """
    Queries current portfolio holdings, unrealized profit/loss, and balances.
    Supports both Settrade Click2Win (Equity & TFEX Derivatives) and Krungsri TradeMan.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    - account_type: Optional 'EQUITY' or 'DERIVATIVES' (for Click2Win)
    """
    plat = resolve_platform(platform)
    if plat == "CLICK2WIN":
        positions = await click2win_driver.scrape_portfolio(account_type=account_type)
        target_str = f"[{account_type.upper()}] " if account_type else ""
        if not positions:
            return f"💼 Click2Win Portfolio {target_str}currently has 0 open holdings in sandbox."
        lines = [f"💼 Click2Win Portfolio Holdings {target_str}({len(positions)} positions):"]
        for p in positions:
            lines.append(
                f"• **{p.get('symbol', '-')}**: {p.get('volume', 0):,} shares/contracts "
                f"@ Avg ฿{p.get('avg_cost', 0):,.2f} | Current ฿{p.get('market_price', 0):,.2f} "
                f"(P/L: ฿{p.get('unrealized_pnl', 0):+,.2f})"
            )
        return "\n".join(lines)
    else:
        # Krungsri TradeMan portfolio
        res = await portfolio_service.run_overview()
        report = res.get("report")
        if report:
            return f"💼 Portfolio Overview Report:\n\n{report}"
        positions_count = res.get("positions_count", 0)
        missing_tpsl = res.get("missing_tpsl", [])
        return (
            f"💼 Portfolio Overview Summary:\n"
            f"• Active Positions: {positions_count}\n"
            f"• Stocks Missing TP/SL: {len(missing_tpsl)}\n"
            f"• Missing TP/SL List: {', '.join(missing_tpsl) if missing_tpsl else 'None (All Protected)'}"
        )


@mcp_server.tool()
async def get_account_balance(platform: Optional[str] = None) -> str:
    """
    Discovers and lists account numbers, purchasing power, line, and cash balances
    for Click2Win (Dual Equity & Derivatives accounts) or Krungsri TradeMan.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    if hasattr(driver, "scrape_accounts_summary"):
        summary = await driver.scrape_accounts_summary()
        accounts = summary.get("accounts", [])
        active_type = summary.get("active_account_type", "EQUITY")
        lines = [
            f"📊 Active Platform: {label}",
            f"• Active Account Mode: {active_type}\n",
            "📋 Discovered Accounts:"
        ]
        for acc in accounts:
            lines.append(
                f"• [{acc.get('account_type', 'EQUITY')}] Account: {acc.get('account_no', '-')}\n"
                f"  - Line Available: ฿{acc.get('line_available', 0):,.2f}\n"
                f"  - Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}\n"
                f"  - Total Equity: ฿{acc.get('total_equity', 0):,.2f}"
            )
        return "\n".join(lines)
    else:
        acc = await driver.scrape_account_summary()
        return (
            f"📊 Active Platform: {label}\n"
            f"• Excess Equity (EE): ฿{acc.get('excess_equity', 0):,.2f}\n"
            f"• Cash Balance: ฿{acc.get('cash_balance', 0):,.2f}\n"
            f"• Line Available: ฿{acc.get('line_available', 0):,.2f}"
        )


@mcp_server.tool()
async def list_trading_accounts() -> str:
    """Alias for get_account_balance."""
    return await get_account_balance()


@mcp_server.tool()
async def get_portfolio(account_type: Optional[str] = None, platform: Optional[str] = None) -> str:
    """Alias for get_portfolio_overview."""
    return await get_portfolio_overview(platform=platform, account_type=account_type)


# ==============================================================================
# 3. TRADING EXECUTION & ORDER MANAGEMENT TOOLS
# ==============================================================================

@mcp_server.tool()
async def place_order(
    symbol: str,
    side: str,
    volume: int,
    price: float,
    platform: Optional[str] = None,
    account_type: Optional[str] = None,
    pin: Optional[str] = None
) -> str:
    """
    Submits a trade order to Click2Win (Sandbox Live Execution) or Krungsri (Safety Guarded).
    - symbol: Stock ticker (e.g. 'PTT', 'CPALL') or TFEX series (e.g. 'S50M24')
    - side: 'BUY', 'SELL', 'LONG', 'SHORT'
    - volume: Quantity (shares or contracts)
    - price: Limit price in THB
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    - account_type: Optional 'EQUITY' or 'DERIVATIVES' (auto-detected if omitted)
    - pin: Optional 4-6 digit trading PIN
    """
    plat = resolve_platform(platform)

    # SAFETY GUARD: Krungsri live order execution is locked in read-only mode per user decision
    if plat == "TRADEMAN":
        return (
            "🛡️ [KRUNGSRI READ-ONLY SAFETY GUARD]:\n"
            "Direct live order execution on Krungsri Securities (TradeMan) is currently locked in "
            "READ-ONLY mode to protect real funds. Please use platform='CLICK2WIN' to test order "
            "execution safely in the sandbox, or use simulate_order_validation for offline dry-run testing."
        )

    # Click2Win Execution
    detected_type = click2win_driver.detect_account_type_for_symbol(symbol)
    act_type = account_type or detected_type

    # For equity, run board lot and tick size checks
    if act_type == "EQUITY":
        valid_lot, lot_err = order_validator.validate_board_lot(volume)
        if not valid_lot:
            return f"❌ Pre-Trade Validation Rejected: {lot_err}"
        valid_tick, tick_err = order_validator.validate_tick_size(price)
        if not valid_tick:
            return f"❌ Pre-Trade Validation Rejected: {tick_err}"

    result = await click2win_driver.execute_order(
        symbol=symbol,
        side=side,
        volume=volume,
        price=price,
        account_type=act_type,
        pin=pin or getattr(settings, "CLICK2WIN_PIN", "000000"),
        auto_launch=True
    )

    success = result.get("success", False)
    status_icon = "✅" if success else "❌"
    return (
        f"{status_icon} Click2Win Sandbox Order Execution Result:\n"
        f"• Status: {result.get('status', 'UNKNOWN')}\n"
        f"• Order No: {result.get('broker_order_no', '-')}\n"
        f"• Order: {side.upper()} {volume:,} {symbol.upper()} @ ฿{price:,.2f}\n"
        f"• Account Mode: {result.get('account_type', act_type)}\n"
        f"• Message: {result.get('message', result.get('error', '-'))}"
    )


@mcp_server.tool()
async def execute_order(
    symbol: str,
    side: str,
    volume: int,
    price: float,
    account_type: Optional[str] = None,
    pin: Optional[str] = None,
    platform: Optional[str] = None
) -> str:
    """Alias for place_order."""
    return await place_order(
        symbol=symbol,
        side=side,
        volume=volume,
        price=price,
        platform=platform,
        account_type=account_type,
        pin=pin
    )


@mcp_server.tool()
async def get_open_orders(
    platform: Optional[str] = None,
    account_type: Optional[str] = None
) -> str:
    """
    Queries unmatched/open orders waiting in queue on the broker/sandbox platform.
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    - account_type: Optional 'EQUITY' or 'DERIVATIVES' (for Click2Win)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    if hasattr(driver, "scrape_unmatched_orders"):
        kwargs = {}
        if "account_type" in driver.scrape_unmatched_orders.__code__.co_varnames:
            kwargs["account_type"] = account_type
        orders = await driver.scrape_unmatched_orders(**kwargs)
    else:
        orders = []

    if not orders:
        return f"ℹ️ No open/unmatched orders currently waiting in queue on {label}."

    lines = [f"📋 Open Orders on {label} ({len(orders)} total):"]
    for o in orders:
        lines.append(
            f"• [{o.get('broker_order_no', '-')}] {o.get('side', '')} {o.get('volume', 0):,} {o.get('symbol', '')} "
            f"@ ฿{o.get('price', 0):,.2f} (Status: {o.get('status', 'OPEN')})"
        )
    return "\n".join(lines)


@mcp_server.tool()
async def cancel_order(
    order_no: str,
    symbol: str = "",
    platform: Optional[str] = None
) -> str:
    """
    Cancels a pending queued order on the active broker/sandbox platform.
    - order_no: Broker order ID to cancel
    - symbol: Optional stock ticker or series
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    if hasattr(driver, "cancel_order"):
        res = await driver.cancel_order(broker_order_no=order_no, symbol=symbol)
        status_icon = "✅" if res.get("success", False) else "❌"
        return f"{status_icon} Cancel Order on {label}: {res.get('message', res.get('status', 'DONE'))}"
    return f"❌ Cancel order not supported on {label}."


@mcp_server.tool()
async def modify_order_price(
    order_no: str,
    symbol: str,
    new_price: float,
    side: str = "BUY",
    platform: Optional[str] = None
) -> str:
    """
    Adjusts the limit price of an open order via Price Negotiation (Cancel & Re-submit).
    - order_no: Broker order ID to modify
    - symbol: Stock ticker or series
    - new_price: New target limit price in THB
    - side: 'BUY' or 'SELL'
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    plat = resolve_platform(platform)
    driver, auth, label = get_platform_drivers(plat)

    if hasattr(driver, "modify_order_price"):
        res = await driver.modify_order_price(
            broker_order_no=order_no,
            symbol=symbol,
            side=side,
            new_price=new_price,
            bypass_dry_run=True
        )
        status_icon = "✅" if res.get("success", False) else "❌"
        return f"{status_icon} Modify Order Price on {label}: {res.get('message', res.get('status', 'DONE'))}"
    return f"❌ Modify order price not supported on {label}."


@mcp_server.tool()
async def cancel_or_modify_order(
    order_no: str,
    symbol: str = "",
    side: str = "BUY",
    new_price: Optional[float] = None,
    platform: Optional[str] = None
) -> str:
    """
    Modifies limit price of an open order, or cancels it if new_price is not provided.
    - order_no: Broker order ID
    - symbol: Stock ticker or series
    - side: 'BUY' or 'SELL'
    - new_price: Optional new price
    - platform: 'CLICK2WIN' or 'KRUNGSRI' (default: active platform)
    """
    if new_price and new_price > 0:
        return await modify_order_price(order_no=order_no, symbol=symbol, new_price=new_price, side=side, platform=platform)
    return await cancel_order(order_no=order_no, symbol=symbol, platform=platform)


@mcp_server.tool()
async def switch_default_platform(platform: str) -> str:
    """
    Switches the default active trading platform for the homelab session.
    - platform: 'CLICK2WIN' (Sandbox) or 'KRUNGSRI' / 'TRADEMAN' (Live Production)
    """
    plat = resolve_platform(platform)
    if plat not in ["CLICK2WIN", "TRADEMAN"]:
        return f"❌ Invalid platform '{platform}'. Must be 'CLICK2WIN' or 'KRUNGSRI'."
    settings.TRADING_PLATFORM = plat
    db_target = "investment_homelab_click2win.db" if plat == "CLICK2WIN" else "investment_homelab.db"
    return (
        f"✅ Active Trading Platform switched successfully to: {plat}\n"
        f"• Broker Driver: {get_broker_driver().__class__.__name__}\n"
        f"• Target Database: {db_target} (Strictly Isolated)\n"
        f"• Real Money Risk: {'NONE (100% Paper Sandbox)' if plat == 'CLICK2WIN' else 'READ-ONLY GUARDED'}"
    )


@mcp_server.tool()
async def switch_trading_platform(platform: str) -> str:
    """Alias for switch_default_platform."""
    return await switch_default_platform(platform=platform)


@mcp_server.tool()
async def switch_click2win_account(account_type: str) -> str:
    """
    Switches the active account tab on Settrade Click2Win between Equity and Derivatives.
    - account_type: 'EQUITY' (หุ้น) or 'DERIVATIVES' (TFEX อนุพันธ์)
    """
    target = account_type.upper().strip()
    if target not in ["EQUITY", "DERIVATIVES"]:
        return f"❌ Invalid account type '{account_type}'. Must be 'EQUITY' or 'DERIVATIVES'."
    res = await click2win_driver.switch_account_type(target)
    status_icon = "✅" if res else "❌"
    return f"{status_icon} Click2Win Account Mode switched to: {target}"


# ==============================================================================
# 4. DRY-RUN SIMULATION & MARKET INTELLIGENCE TOOLS
# ==============================================================================

@mcp_server.tool()
async def simulate_order_validation(
    symbol: str,
    side: str,
    volume: int,
    price: float
) -> str:
    """
    Performs offline dry-run pre-trade risk validation and executes order in Virtual Simulator.
    Guaranteed ZERO risk to live broker account.
    - symbol: Stock ticker (e.g. 'DELTA', 'CPALL')
    - side: 'BUY' or 'SELL'
    - volume: Number of shares (must be multiple of 100 board lot)
    - price: Price in THB (must match official SET tick size)
    """
    sym = symbol.upper().strip()
    side_clean = side.upper().strip()

    if side_clean not in ["BUY", "SELL", "SHORT", "COVER"]:
        return f"❌ Invalid side '{side}'. Must be BUY, SELL, SHORT, or COVER."

    # 1. Validate Board Lot (multiple of 100)
    valid_lot, lot_err = order_validator.validate_board_lot(volume)
    if not valid_lot:
        return f"❌ Pre-Trade Validation Failed: {lot_err}"

    # 2. Validate Tick Size
    valid_tick, tick_err = order_validator.validate_tick_size(price)
    if not valid_tick:
        return f"❌ Pre-Trade Validation Failed: {tick_err}"

    # 3. Validate Value Limit (Ceiling)
    total_val = volume * price
    max_val = float(settings.MAX_ORDER_VALUE_THB)
    if total_val > max_val:
        return f"❌ Pre-Trade Risk Rejected: Total value ฿{total_val:,.2f} exceeds ceiling of ฿{max_val:,.2f}"

    # 4. Safe Simulation Execution via Virtual Simulator
    sim_order = await virtual_simulator.execute_simulated_order(
        symbol=sym,
        side=side_clean,
        volume=volume,
        price=price
    )

    order_no = sim_order.get("broker_order_no", sim_order.get("order_id", "SIM-OK"))
    status = sim_order.get("status", "SUBMITTED")

    return (
        f"🛡️ [SIMULATION DRY-RUN ONLY] Pre-Trade Validation PASSED:\n"
        f"• Mode: 100% Isolated Virtual Simulator (Zero Broker Risk)\n"
        f"• Order: {side_clean} {volume:,} {sym} @ ฿{price:,.2f}\n"
        f"• Total Value: ฿{total_val:,.2f}\n"
        f"• Board Lot Check: ✅ Multiplier of 100 Passed\n"
        f"• Tick Size Check: ✅ SET Spread Passed (Spread: {order_validator.get_set_tick_size(price)})\n"
        f"• Ceiling Check: ✅ Under ฿{max_val:,.2f}\n"
        f"• Simulator Status: {status} in Virtual Sandbox (ID: {order_no})"
    )


@mcp_server.tool()
async def inquire_sbl_pool(symbol: Optional[str] = None) -> str:
    """
    Inspects Securities Borrowing & Lending (SBL) available inventory, borrow rates,
    and corporate action conflicts (XD/XR) without submitting any borrow order.
    - symbol: Optional stock ticker (e.g. 'PTT', 'CPALL') to filter specific inventory.
    """
    if trade_dispatcher.is_live or auth_driver.is_authenticated:
        sbl_data = await trademan_driver.scrape_sbl_inventory(symbol=symbol)
    else:
        # Simulator fallback if browser session is unauthenticated
        sbl_lots = virtual_simulator.get_sbl_lots_snapshot()
        sbl_data = {
            "source": "Simulator",
            "available_lots": sbl_lots,
            "message": "Running in Test/Simulator fallback."
        }

    lines = [f"📈 SBL Pool Inquiry Results (Filter: {symbol or 'All Available'}):"]
    if isinstance(sbl_data, dict):
        for k, v in sbl_data.items():
            if isinstance(v, list):
                lines.append(f"• {k}: {len(v)} items")
                for item in v[:5]:
                    lines.append(f"   - {item}")
                if len(v) > 5:
                    lines.append(f"   - ... and {len(v)-5} more")
            else:
                lines.append(f"• {k}: {v}")
    else:
        lines.append(str(sbl_data))

    return "\n".join(lines)


@mcp_server.tool()
async def get_market_regime() -> str:
    """
    Retrieves current SET index snapshot, percentage change, trading value, and market regime assessment.
    """
    res = await market_monitor_service.capture_and_report(period_label="RemoteMCP")
    snapshot = res.get("snapshot", {})
    summary = res.get("summary_text", "")

    pct = snapshot.get("pct_change", 0.0)
    regime = "BULLISH 🐂" if pct > 0.5 else ("BEARISH 🐻" if pct < -0.5 else "SIDEWAYS 🦀")

    return (
        f"📈 Market Regime & SET Status:\n"
        f"• Market Regime: {regime}\n"
        f"• Snapshot: {summary}\n"
        f"• Index: {snapshot.get('current_index', 0):,.2f} ({snapshot.get('pct_change', 0):+.2f}%)\n"
        f"• High / Low: {snapshot.get('high', 0):,.2f} / {snapshot.get('low', 0):,.2f}\n"
        f"• Market Value: ฿{snapshot.get('value_mb', 0):,.0f} MB"
    )


@mcp_server.tool()
async def workflow_list() -> str:
    """
    Lists all available learned workflows (.md files) and their descriptions.
    """
    workflows = workflow_engine.list_workflows()
    if not workflows:
        return "ℹ️ No learned workflows found in `learned_workflows/` directory."

    lines = [f"📋 Learned Workflows Available ({len(workflows)} total):"]
    for i, wf_name in enumerate(workflows, 1):
        lines.append(f"{i}. **{wf_name}** (`learned_workflows/{wf_name}.md`)")
    return "\n".join(lines)


@mcp_server.tool()
async def report_feedback_and_correct(
    workflow_name: str,
    failed_step: int,
    correct_selector: str,
    action: Optional[str] = None,
    explanation: str = ""
) -> str:
    """
    Self-Annealing Tool: Enables Remote AI agents or developers to correct automated UI behaviors live.
    Updates the workflow specification runbook (learned_workflows/<name>.md) automatically.
    - workflow_name: Name of workflow (e.g. 'click2win_order_submit', 'portfolio_overview_sync')
    - failed_step: Step number to update (e.g. 1, 2, 3)
    - correct_selector: The working CSS selector or text locator
    - action: Optional action type ('CLICK', 'TYPE', 'WAIT', 'NAVIGATE')
    - explanation: Brief explanation of the UI shift or fix
    """
    result = workflow_engine.update_workflow_step(
        name=workflow_name,
        step_num=failed_step,
        new_selector=correct_selector,
        new_action=action,
        explanation=explanation
    )
    if result.get("success", False):
        return (
            f"🧠 [SELF-ANNEALING SUCCESS] Workflow '{workflow_name}' updated successfully:\n"
            f"• Step: {failed_step}\n"
            f"• New Selector: `{correct_selector}`\n"
            f"• Explanation: {explanation}\n"
            f"• Runbook: `{result.get('filepath')}`\n"
            f"Future executions will automatically use this updated selector."
        )
    return f"❌ Self-Annealing failed: {result.get('error', 'Unknown error')}"


# ==============================================================================
# 5. SSE APP FACTORY
# ==============================================================================

def get_sse_app():
    """
    Returns the Starlette ASGI application for SSE and Messages handling.
    Configured with DNS rebinding protection disabled to permit Tailscale IP traffic seamlessly.
    """
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return mcp_server.sse_app(
        sse_path="/sse",
        message_path="/messages/",
        transport_security=security
    )
