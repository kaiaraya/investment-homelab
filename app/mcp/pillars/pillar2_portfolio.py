"""
Pillar 2: Account & Portfolio Module (redefined from the former Pillar 5).

Extracted directly from learned workflows:
- portfolio_overview_sync.md
- click2win_portfolio_sync.md
- click2win_price_negotiation.md (open orders detection)

Functions:
- switch_account: Dedicated tool to switch active working account per broker (Krungsri CASH/MARGIN, Liberator single-account CASH)
- portfolio_get_balances: Cash, Line Available, Excess Equity (Dual-Account Equity & TFEX / Cash & Margin)
- portfolio_holdings: Positions, Available Vol, Avg Cost, Unrealized P/L
- current_open_orders: Orders in Queuing(SX) / Unmatched state
- portfolio_sync_db: Snapshot current portfolio to SQLite positions table
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.browser.click2win_driver import click2win_driver
from app.browser.trademan_driver import trademan_driver
from app.services.portfolio_overview_service import PortfolioOverviewService
from app.schemas.account import (
    AccountType,
    AccountCapability,
    AccountEnvironment,
    account_context,
    account_guardrail,
    ACCOUNT_CAPABILITY_MATRIX
)
from app.schemas.mcp_response import MCPToolStatus, create_maintenance_response, create_admin_attention_response
from app.services.kdeconnect_service import KdeConnectService

logger = logging.getLogger("Pillar2.Portfolio")
overview_service = PortfolioOverviewService()


def _classify_order_category(volume: int, matched_volume: int, balance: int, status_raw: str) -> str:
    """
    Single source of truth mapping a broker order (raw status token + volumes) to a
    canonical category used by the Pillar 2 Order Ledger:

    MATCHED | PARTIALLY_MATCHED | UNMATCHED | CANCELLED | REJECTED | UNKNOWN

    Priority order:
      1. Terminal cancel / reject codes.
      2. Volume truth (most reliable when numbers are present).
      3. Raw status text (letters 'M'/'O'/'C' or keywords).
      4. Fallback: positive balance means still open.
    """
    raw = str(status_raw or "").strip().upper()
    code = raw.replace(" ", "")
    vol = int(volume or 0)
    mv = int(matched_volume or 0)
    bal = int(balance or 0)

    # 1. Terminal cancel / reject
    if code in ("C", "CX", "X") or "CANCEL" in raw:
        return "CANCELLED"
    if code in ("R", "RJ") or "REJECT" in raw:
        return "REJECTED"

    # 2. Volume-based truth
    if vol > 0 and bal <= 0 and mv >= vol:
        return "MATCHED"
    if mv > 0 and bal > 0:
        return "PARTIALLY_MATCHED"

    # 3. Raw status text
    if code in ("M",) or "MATCH" in raw or "FILL" in raw or "COMPLETE" in raw:
        return "MATCHED" if bal <= 0 else "PARTIALLY_MATCHED"
    if code in ("P", "PM") or "PARTIAL" in raw:
        return "PARTIALLY_MATCHED"
    if code in ("O", "N", "SX") or any(t in raw for t in ("OPEN", "QUEU", "PENDING", "WAIT", "NEW", "SX")):
        return "UNMATCHED"

    # 4. Fallback
    if bal > 0:
        return "UNMATCHED"
    return "UNKNOWN"


async def portfolio_list_accounts(platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Lists all trading accounts across brokers (Click2Win, Krungsri Securities, Settrade Open API).
    Provides comprehensive clarity on:
    - Broker Name & Account Number
    - Account Type (EQUITY, DERIVATIVES, CASH, MARGIN)
    - Trading Mode: 'เงินจริง' (LIVE) vs 'เงินเสมือน' (SIMULATION / SANDBOX)
    - Authorized Capabilities (e.g. SBL exclusive to Krungsri MARGIN)
    - Active status and switch command instructions
    
    Can optionally filter by platform ('CLICK2WIN', 'KRUNGSRI', 'SETTRADE_OPENAPI').
    Returns both structured JSON accounts list and a readable Markdown summary table.
    """
    plat_filter = platform.upper().strip() if platform else None
    if plat_filter in ["KRUNGSRI", "TRADEMAN"]:
        plat_filter = "KRUNGSRI"
    elif plat_filter in ["SETTRADE_OPENAPI", "SETTRADE"]:
        plat_filter = "SETTRADE_OPENAPI"
    elif plat_filter in ["CLICK2WIN", "C2W"]:
        plat_filter = "CLICK2WIN"

    all_accounts = [
        # Settrade Click2Win (Simulation)
        {
            "account_no": settings.CLICK2WIN_ACCOUNT_NO_EQUITY or "CW32_E_7338419",
            "broker_name": "Settrade Click2Win",
            "platform": "CLICK2WIN",
            "account_type": AccountType.EQUITY.value,
            "environment": AccountEnvironment.SIMULATION.value,
            "environment_label": "🟡 เงินเสมือน (Click2Win Sandbox 5M)",
            "description": "พอร์ตจำลองหุ้น SET วงเงิน 5,000,000 บาท",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("CLICK2WIN", AccountType.EQUITY.value), [])],
            "is_active": (account_context.click2win_active == AccountType.EQUITY),
            "switch_command": 'switch_account(platform="CLICK2WIN", account_type="EQUITY")'
        },
        {
            "account_no": settings.CLICK2WIN_ACCOUNT_NO_DERIVATIVES or "CW32_D_7338419",
            "broker_name": "Settrade Click2Win",
            "platform": "CLICK2WIN",
            "account_type": AccountType.DERIVATIVES.value,
            "environment": AccountEnvironment.SIMULATION.value,
            "environment_label": "🟡 เงินเสมือน (Click2Win TFEX Sandbox 2M)",
            "description": "พอร์ตจำลองอนุพันธ์ TFEX วงเงิน 2,000,000 บาท",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("CLICK2WIN", AccountType.DERIVATIVES.value), [])],
            "is_active": (account_context.click2win_active == AccountType.DERIVATIVES),
            "switch_command": 'switch_account(platform="CLICK2WIN", account_type="DERIVATIVES")'
        },
        # Krungsri Securities (Live)
        {
            "account_no": settings.TRADEMAN_ACCOUNT_NO_CASH or "3024952",
            "broker_name": "Krungsri Securities (TradeMan)",
            "platform": "KRUNGSRI",
            "account_type": AccountType.CASH.value,
            "environment": AccountEnvironment.LIVE.value,
            "environment_label": "🟢 เงินจริง (Krungsri Cash Balance)",
            "description": "บัญชีเงินสด Cash Balance สำหรับซื้อขายหุ้นจริง (ห้ามทำ SBL)",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("KRUNGSRI", AccountType.CASH.value), [])],
            "is_active": (account_context.krungsri_active == AccountType.CASH),
            "switch_command": 'switch_account(platform="KRUNGSRI", account_type="CASH")'
        },
        {
            "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN or "3024959",
            "broker_name": "Krungsri Securities (TradeMan)",
            "platform": "KRUNGSRI",
            "account_type": AccountType.MARGIN.value,
            "environment": AccountEnvironment.LIVE.value,
            "environment_label": "🟢 เงินจริง (Krungsri Credit Balance / Margin)",
            "description": "บัญชีวงเงิน Credit Balance สำหรับซื้อขายหุ้นและยืม/คืนหุ้น SBL (สงวนสิทธิ์เฉพาะบัญชีนี้)",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("KRUNGSRI", AccountType.MARGIN.value), [])],
            "is_active": (account_context.krungsri_active == AccountType.MARGIN),
            "switch_command": 'switch_account(platform="KRUNGSRI", account_type="MARGIN")'
        },
        # Settrade Open API (Sandbox)
        {
            "account_no": settings.SETTRADE_ACCOUNT_NO_EQUITY or "SANDBOX-EQ-001",
            "broker_name": "Settrade Open API (Machine-to-Machine)",
            "platform": "SETTRADE_OPENAPI",
            "account_type": AccountType.EQUITY.value,
            "environment": AccountEnvironment.SANDBOX.value,
            "environment_label": "🟡 เงินเสมือน (Open API Sandbox)",
            "description": "พอร์ตเชื่อมต่อ API ความเร็วสูง (<50ms) สำหรับหุ้น",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("SETTRADE_OPENAPI", AccountType.EQUITY.value), [])],
            "is_active": (account_context.settrade_active == AccountType.EQUITY),
            "switch_command": 'switch_account(platform="SETTRADE_OPENAPI", account_type="EQUITY")'
        },
        {
            "account_no": settings.SETTRADE_ACCOUNT_NO_DERIVATIVES or "SANDBOX-DERIV-002",
            "broker_name": "Settrade Open API (Machine-to-Machine)",
            "platform": "SETTRADE_OPENAPI",
            "account_type": AccountType.DERIVATIVES.value,
            "environment": AccountEnvironment.SANDBOX.value,
            "environment_label": "🟡 เงินเสมือน (Open API TFEX Sandbox)",
            "description": "พอร์ตเชื่อมต่อ API ความเร็วสูง (<50ms) สำหรับอนุพันธ์ TFEX",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("SETTRADE_OPENAPI", AccountType.DERIVATIVES.value), [])],
            "is_active": (account_context.settrade_active == AccountType.DERIVATIVES),
            "switch_command": 'switch_account(platform="SETTRADE_OPENAPI", account_type="DERIVATIVES")'
        },
        # Liberator Securities (Live)
        {
            "account_no": settings.LIBERATOR_USERNAME or "7055938",
            "broker_name": "Liberator Securities (WebTrade)",
            "platform": "LIBERATOR",
            "account_type": AccountType.CASH.value,
            "environment": AccountEnvironment.LIVE.value,
            "environment_label": "🟢 เงินจริง (Liberator WebTrade)",
            "description": "พอร์ตเทรดหุ้นคอมมิชชั่น 0% ผ่าน Liberator WebTrade",
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("LIBERATOR", AccountType.CASH.value), [])],
            "is_active": (account_context.liberator_active == AccountType.CASH),
            "switch_command": 'switch_account(platform="LIBERATOR", account_type="CASH")'
        },
    ]

    filtered = [a for a in all_accounts if (not plat_filter or a["platform"] == plat_filter)]

    # Generate Markdown Table for instant human readability
    table_lines = [
        "| โบรกเกอร์ / สถาบัน | เลขบัญชี | ประเภทบัญชี | ระบบเงิน | สิทธิ์ที่ทำได้ (Capabilities) | สถานะ Active | คำสั่งสลับบัญชี (Switch Command) |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | :--- |"
    ]
    for acc in filtered:
        active_badge = "✅ **ACTIVE**" if acc["is_active"] else "⚪ Standby"
        caps_str = ", ".join(acc["capabilities"])
        cmd_code = f"`{acc['switch_command']}`"
        table_lines.append(
            f"| {acc['broker_name']} | `{acc['account_no']}` | **{acc['account_type']}** | {acc['environment_label']} | {caps_str} | {active_badge} | {cmd_code} |"
        )
    markdown_table = "\n".join(table_lines)

    return {
        "success": True,
        "total_accounts": len(filtered),
        "filter_platform": plat_filter or "ALL",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "markdown_table": markdown_table,
        "accounts": filtered
    }


async def switch_account(platform: str, account_type: str) -> Dict[str, Any]:
    """
    Dedicated tool to switch active working account on target broker platform.
    
    Platforms:
    - CLICK2WIN: 'EQUITY' (Stocks) vs 'DERIVATIVES' (TFEX)
    - KRUNGSRI: 'CASH' (Cash Balance) vs 'MARGIN' (Credit Balance / SBL exclusive)
    - SETTRADE_OPENAPI: 'EQUITY' vs 'DERIVATIVES'
    - LIBERATOR: single-account 'CASH' (no MARGIN / DERIVATIVES to switch)
    """
    plat = platform.upper().strip()
    if plat in ["KRUNGSRI", "TRADEMAN"]:
        target_plat = "KRUNGSRI"
    elif plat in ["SETTRADE_OPENAPI", "SETTRADE"]:
        target_plat = "SETTRADE_OPENAPI"
    elif plat in ["LIBERATOR"]:
        target_plat = "LIBERATOR"
    else:
        target_plat = "CLICK2WIN"

    target_type = account_guardrail.normalize_account_type(target_plat, account_type)

    # Liberator is single-account: flag any clamped non-CASH request truthfully.
    clamp_warning = None
    if target_plat == "LIBERATOR":
        _raw_type = (account_type or "").upper().strip()
        if _raw_type in ["MARGIN", "CREDIT_BALANCE", "CREDIT", "SBL", "DERIVATIVES", "TFEX", "FUTURES"]:
            clamp_warning = (
                f"Liberator Securities is single-account (CASH); "
                f"requested '{_raw_type}' was clamped to CASH."
            )

    # 1. Update UI DOM context if Click2Win / Krungsri TradeMan / Liberator
    res_kss = {}
    try:
        if target_plat == "CLICK2WIN":
            await click2win_driver.switch_account_type(target_type.value)
        elif target_plat == "LIBERATOR":
            # Liberator is single-account (Cash). Verify compatibility instead of
            # attempting a UI switch that does not exist.
            from app.brokers import liberator_plugin
            _lib_ok = await liberator_plugin.switch_account_type(target_type.value)
            if not _lib_ok:
                return create_maintenance_response(
                    reason=(
                        "Liberator Securities is a single-account (Cash Balance) broker; "
                        f"account type '{target_type.value}' is not available."
                    ),
                    escalated=False,
                    details={"platform": "LIBERATOR", "target_type": target_type.value}
                )
        elif target_plat == "KRUNGSRI":
            res_kss = await trademan_driver.switch_account(target_type.value)
            if not res_kss.get("success", False) and res_kss.get("status") == "AWAITING_OTP":
                return res_kss
            elif not res_kss.get("success", False):
                try:
                    kde = KdeConnectService()
                    await kde.notify_admin_screen_help(
                        reason=f"สลับบัญชี Krungsri เป็น {target_type.value} ไม่สำเร็จ",
                        workflow_or_step="trademan_switch_account"
                    )
                except Exception:
                    pass
                return create_maintenance_response(
                    reason=f"Failed to switch Krungsri account: {res_kss.get('error', 'UI switch failed')}",
                    escalated=True,
                    details=res_kss
                )
    except Exception as e:
        logger.error(f"Pillar 2: Switch account failed with exception: {e}")
        try:
            kde = KdeConnectService()
            await kde.notify_admin_screen_help(
                reason=f"สลับบัญชี {target_plat} ล้มเหลว: {str(e)[:80]}",
                workflow_or_step="switch_account"
            )
        except Exception:
            pass
        return create_maintenance_response(
            reason=f"Exception during account switch: {str(e)}",
            escalated=True,
            details={"platform": target_plat, "target_type": target_type.value}
        )

    # 2. Update global account context state
    account_context.set_active(target_plat, target_type)

    # 3. Retrieve authorized capabilities
    caps = ACCOUNT_CAPABILITY_MATRIX.get((target_plat, target_type.value), [])
    
    account_no = ""
    if target_plat == "CLICK2WIN":
        account_no = (
            click2win_driver.active_account_no
            or (settings.CLICK2WIN_ACCOUNT_NO_DERIVATIVES if target_type == AccountType.DERIVATIVES else (settings.CLICK2WIN_ACCOUNT_NO_EQUITY or "CW32_E_7338419"))
        )
    elif target_plat == "KRUNGSRI":
        account_no = (
            res_kss.get("account_no")
            or trademan_driver.active_account_no
            or (settings.TRADEMAN_ACCOUNT_NO_MARGIN if target_type == AccountType.MARGIN else (settings.TRADEMAN_ACCOUNT_NO_CASH or "3024952"))
        )
    elif target_plat == "LIBERATOR":
        account_no = getattr(settings, "LIBERATOR_USERNAME", None) or "7055938"
    else:
        account_no = settings.SETTRADE_ACCOUNT_NO_DERIVATIVES if target_type == AccountType.DERIVATIVES else settings.SETTRADE_ACCOUNT_NO_EQUITY

    logger.info(f"Pillar 2: Switched {target_plat} account to {target_type.value} ({account_no})")
    resp = {
        "success": True,
        "platform": target_plat,
        "active_account_type": target_type.value,
        "account_no": account_no,
        "capabilities": [c.value for c in caps],
        "message": f"Successfully activated {target_plat} account: {target_type.value} ({account_no})",
        "switched_at": datetime.now(timezone.utc).isoformat()
    }
    if res_kss.get("status"):
        resp["ui_status"] = res_kss["status"]
    if res_kss.get("warning"):
        resp["warning"] = res_kss["warning"]
    if clamp_warning:
        resp["warning"] = clamp_warning
    return resp


async def portfolio_get_balances(platform: Optional[str] = None, account_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns purchasing power and balances for Equity and TFEX / Cash and Margin.
    (Cash Balance, Line Available, Credit Limit, Excess Equity)
    """
    plat_raw = (platform or settings.TRADING_PLATFORM).upper().strip()
    if plat_raw in ["KRUNGSRI", "TRADEMAN"]:
        plat = "KRUNGSRI"
    elif plat_raw in ["LIBERATOR", "LIB"]:
        # RCA-007: LIBERATOR must route to the Liberator branch below — previously it
        # fell through to `else: CLICK2WIN`, so `/cash lib` showed Click2Win balances.
        plat = "LIBERATOR"
    elif plat_raw in ["SETTRADE_OPENAPI", "SETTRADE"]:
        plat = "SETTRADE_OPENAPI"
    elif plat_raw in ["CLICK2WIN", "C2W"]:
        plat = "CLICK2WIN"
    else:
        # Anti-Mock + Broker Isolation (RCA-007): an unknown broker name must raise,
        # never silently fall back to Click2Win (would report wrong-broker data).
        raise ValueError(
            f"Unknown trading platform: {platform!r}. "
            "Expected one of: KRUNGSRI/TRADEMAN, LIBERATOR/LIB, SETTRADE_OPENAPI/SETTRADE, CLICK2WIN/C2W."
        )

    active_type = account_guardrail.normalize_account_type(plat, account_type)

    if plat == "CLICK2WIN":
        if hasattr(click2win_driver, "scrape_accounts_summary"):
            res = await click2win_driver.scrape_accounts_summary()
            raw_accounts = res.get("accounts", []) if isinstance(res, dict) else [res]
        elif hasattr(click2win_driver, "list_trading_accounts"):
            raw_accounts = await click2win_driver.list_trading_accounts()
        else:
            raw_accounts = [await click2win_driver.scrape_account_summary()]

        accounts = []
        for acc in raw_accounts:
            t = acc.get("account_type", "EQUITY")
            acc_copy = dict(acc)
            acc_copy["is_active"] = (t == account_context.click2win_active.value)
            acc_copy["capabilities"] = [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("CLICK2WIN", t), [])]
            accounts.append(acc_copy)

        return {
            "platform": "CLICK2WIN",
            "active_account_type": account_context.click2win_active.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accounts": accounts
        }

    elif plat == "KRUNGSRI":
        balances = await trademan_driver.scrape_account_summary() if hasattr(trademan_driver, "scrape_account_summary") else {}
        # RCA-009: scrape_account_summary returns None (not 0.0) for an unreadable value
        # and sets authenticated=False when the page is a SignIn/expired session.
        auth_ok = bool(balances.get("authenticated", True)) if isinstance(balances, dict) else False
        # CLI-RCA-011 (P2a): bind the scraped figures to the account number the driver
        # actually read off the dropdown (``account_no``). A mismatch — or an unreadable
        # number — leaves BOTH accounts with ``None``, so a value can never be rendered
        # under the wrong account header (money-movement safety).
        scraped_no = balances.get("account_no") if isinstance(balances, dict) else None
        # Anti-Mock (CLI-RCA-003): do NOT fabricate a 500k balance when the scraper
        # returned no value — leave it None so callers can say "อ่านไม่ได้" honestly.
        cash_acc = {
            "account_no": settings.TRADEMAN_ACCOUNT_NO_CASH or "3024952",
            "account_type": AccountType.CASH.value,
            "description": "Krungsri Cash Balance Account (Pre-funded Stocks)",
            "is_active": (account_context.krungsri_active == AccountType.CASH),
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("KRUNGSRI", AccountType.CASH.value), [])]
        }
        margin_acc = {
            "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN or "3024959",
            "account_type": AccountType.MARGIN.value,
            "description": "Krungsri Credit Balance / Margin Account (SBL Exclusive)",
            "is_active": (account_context.krungsri_active == AccountType.MARGIN),
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("KRUNGSRI", AccountType.MARGIN.value), [])]
        }

        def _bind(acc: Dict[str, Any]) -> Dict[str, Any]:
            bound = scraped_no is not None and str(scraped_no) == str(acc["account_no"])
            acc["values_bound"] = bound
            # Driver key ``cash_balance`` is really Line Available (selector order, CLI-RCA-011).
            acc["line_available"] = balances.get("cash_balance") if bound else None
            acc["cash_balance"] = None          # not scraped honestly yet -> P2b
            acc["excess_equity"] = balances.get("excess_equity") if bound else None
            return acc

        cash_acc, margin_acc = _bind(cash_acc), _bind(margin_acc)
        return {
            "platform": "KRUNGSRI",
            "authenticated": auth_ok,
            "active_account_type": account_context.krungsri_active.value,
            "scraped_account_no": scraped_no,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accounts": [cash_acc, margin_acc]
        }

    elif plat == "LIBERATOR":
        from app.brokers import liberator_plugin
        summary = await liberator_plugin.get_account_summary()
        lib_acc = {
            "account_no": summary.account_no,
            "account_type": summary.account_type,
            "description": "Liberator WebTrade Cash Balance Account",
            "line_available": summary.line_available,
            "cash_balance": summary.cash_balance,
            "total_equity": summary.total_equity,
            "is_active": True,
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("LIBERATOR", AccountType.CASH.value), [])]
        }
        return {
            "platform": "LIBERATOR",
            "authenticated": True,
            "active_account_type": AccountType.CASH.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accounts": [lib_acc]
        }

    else:  # SETTRADE_OPENAPI
        eq_acc = {
            "account_no": settings.SETTRADE_ACCOUNT_NO_EQUITY or "SANDBOX-EQ-001",
            "account_type": AccountType.EQUITY.value,
            "description": "Settrade Open API Sandbox Equity Account",
            "line_available": 5_000_000.0,
            "cash_balance": 5_000_000.0,
            "is_active": (account_context.settrade_active == AccountType.EQUITY),
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("SETTRADE_OPENAPI", AccountType.EQUITY.value), [])]
        }
        tfex_acc = {
            "account_no": settings.SETTRADE_ACCOUNT_NO_DERIVATIVES or "SANDBOX-DERIV-002",
            "account_type": AccountType.DERIVATIVES.value,
            "description": "Settrade Open API Sandbox Derivatives Account",
            "line_available": 2_000_000.0,
            "cash_balance": 2_000_000.0,
            "is_active": (account_context.settrade_active == AccountType.DERIVATIVES),
            "capabilities": [c.value for c in ACCOUNT_CAPABILITY_MATRIX.get(("SETTRADE_OPENAPI", AccountType.DERIVATIVES.value), [])]
        }
        return {
            "platform": "SETTRADE_OPENAPI",
            "authenticated": True,
            "active_account_type": account_context.settrade_active.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "accounts": [eq_acc, tfex_acc]
        }


async def portfolio_holdings(platform: Optional[str] = None, account_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns current active portfolio holdings for the specified or active account.
    (Symbol, Total Volume, Available Volume, Avg Cost, Market Price, Unrealized P/L)
    """
    plat_raw = (platform or settings.TRADING_PLATFORM).upper().strip()
    if plat_raw in ["KRUNGSRI", "TRADEMAN"]:
        plat = "KRUNGSRI"
    elif plat_raw in ["LIBERATOR"]:
        plat = "LIBERATOR"
    else:
        plat = "CLICK2WIN"
    target_acc = account_guardrail.normalize_account_type(plat, account_type)

    try:
        if plat == "CLICK2WIN":
            holdings = await click2win_driver.scrape_portfolio(account_type=target_acc.value)
            return {
                "platform": "CLICK2WIN",
                "account_type": target_acc.value,
                "count": len(holdings),
                "holdings": holdings
            }
        elif plat == "LIBERATOR":
            from app.brokers import liberator_plugin
            port = await liberator_plugin.get_portfolio()
            holdings = [p.model_dump() for p in port.positions]
            return {
                "platform": "LIBERATOR",
                "account_type": target_acc.value,
                "count": len(holdings),
                "holdings": holdings
            }
        else:
            holdings = await trademan_driver.scrape_portfolio()
            for h in holdings:
                h["account_type"] = target_acc.value
            return {
                "platform": "KRUNGSRI",
                "account_type": target_acc.value,
                "count": len(holdings),
                "holdings": holdings
            }
    except Exception as e:
        logger.error(f"Pillar 2: Failed to fetch holdings ({e}). Triggering maintenance guardrail...")
        try:
            kde = KdeConnectService()
            await kde.notify_admin_screen_help(
                reason=f"ดึงข้อมูล Portfolio ล้มเหลว ({plat} {target_acc.value}): {str(e)[:80]}",
                workflow_or_step="portfolio_holdings"
            )
        except Exception:
            pass
        return create_maintenance_response(
            reason=f"Failed to fetch portfolio holdings for {plat} {target_acc.value}: {str(e)}",
            escalated=True,
            details={"platform": plat, "account_type": target_acc.value}
        )


async def current_open_orders(platform: Optional[str] = None, account_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches open / queuing orders that are currently unmatched on the board (Queuing(SX)).
    Used by Pillar 6 Strategy to perform price negotiation.
    Supports Click2Win, Krungsri TradeMan, and Liberator (single-account CASH).
    """
    plat_raw = (platform or settings.TRADING_PLATFORM).upper().strip()
    if plat_raw in ["KRUNGSRI", "TRADEMAN"]:
        plat = "KRUNGSRI"
    elif plat_raw in ["LIBERATOR"]:
        plat = "LIBERATOR"
    else:
        plat = "CLICK2WIN"
    target_acc = account_guardrail.normalize_account_type(plat, account_type)

    try:
        if plat == "CLICK2WIN":
            orders = await click2win_driver.scrape_unmatched_orders(account_type=target_acc.value)
        elif plat == "LIBERATOR":
            from app.brokers import liberator_plugin
            orders = await liberator_plugin.get_open_orders()
        else:
            orders = await trademan_driver.scrape_unmatched_orders()
    except Exception as e:
        logger.warning(f"Pillar 2: Failed to fetch unmatched orders ({e})")
        orders = []

    unmatched = [
        o for o in orders 
        if any(term in str(o.get("status", "")).upper() for term in ["QUEUE", "SX", "OPEN", "PARTIAL"])
        or (plat == "LIBERATOR" and int(o.get("balance", 0) or 0) > 0)
    ]
    return {
        "platform": plat,
        "account_type": target_acc.value,
        "total_orders": len(orders),
        "unmatched_count": len(unmatched),
        "unmatched_orders": unmatched
    }


async def current_orders(
    platform: Optional[str] = None,
    account_type: Optional[str] = None,
    include_closed: bool = True
) -> Dict[str, Any]:
    """
    Order Ledger — lists ALL orders sent to the broker (matched + partial + unmatched),
    each classified into MATCHED / PARTIALLY_MATCHED / UNMATCHED / CANCELLED / REJECTED.

    Answers: "รายการ Order ที่ส่งไปแล้วให้ Broker — อันไหน Matched อันไหน Unmatched".
    Unlike `current_open_orders` (unmatched-only, for price negotiation), this preserves the
    full lifetime of each sent order.

    Supported: KRUNGSRI (TradeMan CASH/MARGIN) and LIBERATOR (single-account CASH).
    Click2Win full ledger is not yet implemented — use `current_open_orders` for it.

    Args:
        platform: 'KRUNGSRI' | 'LIBERATOR' (defaults to active TRADING_PLATFORM).
        account_type: 'CASH' | 'MARGIN' (Krungsri); ignored for Liberator.
        include_closed: when False, terminal rows (CANCELLED/REJECTED) are omitted.
    """
    plat_raw = (platform or settings.TRADING_PLATFORM).upper().strip()
    if plat_raw in ["KRUNGSRI", "TRADEMAN"]:
        plat = "KRUNGSRI"
    elif plat_raw == "LIBERATOR":
        plat = "LIBERATOR"
    else:
        plat = "CLICK2WIN"

    if plat not in ("KRUNGSRI", "LIBERATOR"):
        return {
            "success": False,
            "status": MCPToolStatus.GUARDRAIL_REJECTED.value,
            "platform": plat,
            "message": (
                "Order Ledger (matched/unmatched) is implemented for KRUNGSRI and LIBERATOR only. "
                "For Click2Win use current_open_orders (unmatched-only)."
            ),
        }

    target_acc = account_guardrail.normalize_account_type(plat, account_type)

    try:
        if plat == "KRUNGSRI":
            raw_orders = await trademan_driver.scrape_all_orders()
        else:
            from app.brokers import liberator_plugin
            raw_orders = await liberator_plugin.get_all_orders()
    except Exception as e:
        logger.error(f"Pillar 2: Failed to fetch order ledger ({e}). Escalating...")
        try:
            kde = KdeConnectService()
            await kde.notify_admin_screen_help(
                reason=f"ดึงรายการ Order ล้มเหลว ({plat} {target_acc.value}): {str(e)[:80]}",
                workflow_or_step="current_orders"
            )
        except Exception:
            pass
        return create_maintenance_response(
            reason=f"Failed to fetch order ledger for {plat} {target_acc.value}: {str(e)}",
            escalated=True,
            details={"platform": plat, "account_type": target_acc.value}
        )

    counts = {"MATCHED": 0, "PARTIALLY_MATCHED": 0, "UNMATCHED": 0, "CANCELLED": 0, "REJECTED": 0, "UNKNOWN": 0}
    ledger: List[Dict[str, Any]] = []
    for o in raw_orders:
        vol = int(o.get("volume", 0) or 0)
        mv = int(o.get("matched_volume", o.get("matched", 0)) or 0)
        bal = int(o.get("balance", 0) or 0)
        status_raw = str(o.get("status", ""))
        category = _classify_order_category(vol, mv, bal, status_raw)
        counts[category] = counts.get(category, 0) + 1
        if not include_closed and category in ("CANCELLED", "REJECTED"):
            continue
        ledger.append({
            "broker_order_no": str(o.get("broker_order_no", "")),
            "symbol": str(o.get("symbol", "")).upper(),
            "side": str(o.get("side", "")).upper(),
            "volume": vol,
            "matched_volume": mv,
            "balance": bal,
            "price": float(o.get("price", 0.0) or 0.0),
            "status_raw": status_raw,
            "status_category": category,
            "time": o.get("time"),
        })

    return {
        "success": True,
        "status": MCPToolStatus.SUCCESS.value,
        "platform": plat,
        "account_type": target_acc.value,
        "total": len(ledger),
        "matched_count": counts["MATCHED"],
        "partially_matched_count": counts["PARTIALLY_MATCHED"],
        "unmatched_count": counts["UNMATCHED"],
        "cancelled_count": counts["CANCELLED"],
        "rejected_count": counts["REJECTED"],
        "unknown_count": counts["UNKNOWN"],
        "include_closed": include_closed,
        "orders": ledger,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def portfolio_sync_db() -> Dict[str, Any]:
    """
    Forces an immediate snapshot of current holdings into SQLite positions table.
    """
    res = await overview_service.run_overview() if hasattr(overview_service, "run_overview") else {}
    return {
        "success": True,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "summary": res
    }


def register_portfolio_pillar(server):
    """Registers Pillar 2 (Account & Portfolio) tools into the MCP server."""
    server.tool()(portfolio_list_accounts)
    server.tool()(switch_account)
    server.tool()(portfolio_get_balances)
    server.tool()(portfolio_holdings)
    server.tool()(current_open_orders)
    server.tool()(current_orders)
    server.tool()(portfolio_sync_db)
