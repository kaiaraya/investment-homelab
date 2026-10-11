"""
Pillar 3: Trade Execution Module.
Handles:
- Direct order execution for Equity & TFEX
- Settrade Open API direct execution for Click2Win sandbox (< 50ms)
- Krungsri TradeMan guarded execution (Read-Only/Dry-run safety)
- Order cancellation and order price amendment
- Pre-trade safety guardrails (Board lot & Max value limits)
- Strict TypeSafe Account Capability Guardrails (Equity vs Derivatives / Cash vs Margin)
"""

import time
import logging
from typing import Dict, Any, Optional
from decimal import Decimal

from app.core.config import settings
from app.services.validator import PreTradeValidator
from app.browser.click2win_driver import click2win_driver
from app.browser.trademan_driver import trademan_driver
from app.schemas.account import (
    AccountType,
    AccountCapability,
    account_guardrail,
    account_context
)

logger = logging.getLogger("Pillar3.Trade")
validator = PreTradeValidator()


def _get_settrade_investor():
    if settings.SETTRADE_APP_ID and settings.SETTRADE_APP_SECRET:
        try:
            from settrade_v2 import Investor
            return Investor(
                app_id=settings.SETTRADE_APP_ID,
                app_secret=settings.SETTRADE_APP_SECRET,
                broker_id=settings.SETTRADE_BROKER_ID or "SANDBOX",
                app_code=settings.SETTRADE_APP_CODE or "SANDBOX",
                is_auto_queue=False
            )
        except Exception as e:
            logger.warning(f"Pillar 3: Settrade Investor init failed: {e}")
    return None


async def trade_place_order(
    symbol: str,
    side: str,
    volume: int,
    price: float,
    position: Optional[str] = "AUTO",
    price_type: str = "Limit",
    platform: str = "CLICK2WIN",
    account_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submits a Buy/Sell or Long/Short order.
    Executes directly via Settrade Open API if configured, or falls back to Browser automation.
    Enforces Pre-trade validation guards and strict Multi-Account Capability Guardrails.
    """
    sym = symbol.strip().upper()
    s = side.strip().upper()
    pos = (position or "AUTO").strip().upper()
    plat_raw = platform.strip().upper()
    if plat_raw in ["KRUNGSRI", "TRADEMAN"]:
        plat = "KRUNGSRI"
    elif plat_raw in ["SETTRADE_OPENAPI", "SETTRADE"]:
        plat = "SETTRADE_OPENAPI"
    elif plat_raw in ["LIBERATOR"]:
        plat = "LIBERATOR"
    else:
        plat = "CLICK2WIN"

    # 1. Determine Required Account Capability by Symbol Type
    is_tfex = (click2win_driver.detect_account_type_for_symbol(sym) == "DERIVATIVES")
    req_cap = AccountCapability.TFEX_TRADE if is_tfex else AccountCapability.EQUITY_TRADE

    # 2. Strict Account Capability Guardrail Validation
    ok_cap, err_cap, resolved_acc = account_guardrail.validate_capability(plat, account_type, req_cap)
    if not ok_cap:
        logger.warning(f"Pillar 3: Order blocked by capability guardrail - {err_cap}")
        return {
            "success": False,
            "error_type": "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION",
            "reason": err_cap,
            "platform": plat,
            "target_account": resolved_acc.value,
            "required_capability": req_cap.value
        }

    # 3. Pre-trade Risk & Strict Asset Action Validation
    ok_val, err_val = validator.validate_all(
        symbol=sym,
        side=s,
        volume=volume,
        price=price,
        position=pos if is_tfex else None
    )
    if not ok_val:
        return {
            "success": False,
            "error_type": "PRE_TRADE_GUARDRAIL_REJECTION",
            "reason": err_val
        }

    # 4. Route Order Execution
    if plat in ["CLICK2WIN", "SETTRADE_OPENAPI"]:
        investor = _get_settrade_investor()
        if investor and (settings.SETTRADE_ACCOUNT_NO_EQUITY or settings.SETTRADE_ACCOUNT_NO_DERIVATIVES):
            try:
                t0 = time.time()
                if resolved_acc == AccountType.EQUITY:
                    eq_acc = settings.SETTRADE_ACCOUNT_NO_EQUITY or "SANDBOX-EQ-001"
                    eq = investor.Equity(account_no=eq_acc)
                    res = eq.place_order(
                        symbol=sym,
                        side="Buy" if s in ["BUY", "COVER"] else "Sell",
                        volume=volume,
                        price=price,
                        price_type=price_type,
                        pin=settings.SETTRADE_PIN or "000000"
                    )
                else:
                    deri_acc = settings.SETTRADE_ACCOUNT_NO_DERIVATIVES or "SANDBOX-DERIV-002"
                    deri = investor.Derivatives(account_no=deri_acc)
                    res = deri.place_order(
                        symbol=sym,
                        side=s.capitalize(),  # "Long" or "Short"
                        position=pos.capitalize() if pos in ["OPEN", "CLOSE", "AUTO"] else "Auto",
                        volume=volume,
                        price=price,
                        price_type=price_type
                    )
                elapsed_ms = (time.time() - t0) * 1000
                logger.info(f"Pillar 3: Settrade API order executed in {elapsed_ms:.1f}ms: {res}")
                return {
                    "success": True,
                    "order_no": str(res.get("orderNo") or res.get("order_no", "")),
                    "platform": f"{plat} (Settrade Open API)",
                    "account_type": resolved_acc.value,
                    "execution_time_ms": elapsed_ms,
                    "response": res
                }
            except Exception as e:
                logger.warning(f"Pillar 3: Settrade API place_order error ({e}), trying browser driver fallback...")

        # Fallback to Click2Win browser driver
        res_browser = await click2win_driver.execute_order(
            symbol=sym,
            side=s,
            volume=volume,
            price=price,
            position=pos,
            price_type=price_type,
            account_type=resolved_acc.value
        )
        return {
            "success": res_browser.get("success", False),
            "order_no": res_browser.get("order_no") or res_browser.get("broker_order_no"),
            "platform": "CLICK2WIN (Browser)",
            "account_type": resolved_acc.value,
            "response": res_browser
        }

    elif plat in ["LIBERATOR"]:
        logger.info(f"Pillar 3: Liberator order request on account {resolved_acc.value} (Guarded mode)")
        from app.brokers import liberator_plugin
        from app.brokers.base import OrderRequest
        res_lib = await liberator_plugin.place_order(OrderRequest(
            symbol=sym,
            side=s,
            volume=volume,
            price=price,
            pin=settings.LIBERATOR_PIN or "000000"
        ))
        return {
            "success": res_lib.success,
            "order_no": res_lib.order_id,
            "platform": "LIBERATOR",
            "account_type": resolved_acc.value,
            "response": res_lib.raw_response,
            "message": res_lib.message
        }

    # Path 2: Krungsri TradeMan (Guarded)
    logger.info(f"Pillar 3: Krungsri TradeMan order request on account {resolved_acc.value} (Guarded mode)")
    res_kss = await trademan_driver.execute_order(
        symbol=sym,
        side=s,
        volume=volume,
        price=price,
        dry_run=True  # Strictly guarded for Live safety
    )
    return {
        "success": res_kss.get("success", False),
        "platform": "KRUNGSRI (Guarded Simulator)",
        "account_type": resolved_acc.value,
        "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN if resolved_acc == AccountType.MARGIN else settings.TRADEMAN_ACCOUNT_NO_CASH,
        "response": res_kss
    }


async def trade_cancel_order(
    order_no: str,
    symbol: Optional[str] = None,
    platform: str = "CLICK2WIN"
) -> Dict[str, Any]:
    """Cancels an existing open/queuing order."""
    plat = platform.strip().upper()
    if plat in ["CLICK2WIN", "C2W"]:
        investor = _get_settrade_investor()
        if investor and settings.SETTRADE_ACCOUNT_NO_EQUITY:
            try:
                eq = investor.Equity(account_no=settings.SETTRADE_ACCOUNT_NO_EQUITY)
                res = eq.cancel_order(order_no=order_no)
                return {"success": True, "platform": "CLICK2WIN (Settrade Open API)", "response": res}
            except Exception as e:
                logger.warning(f"Pillar 3: Settrade API cancel failed: {e}")

        # Browser cancel fallback
        res_browser = await click2win_driver.cancel_order(order_no=order_no, symbol=symbol)
        return {"success": res_browser.get("success", False), "platform": "CLICK2WIN (Browser)", "response": res_browser}

    return {"success": False, "error": "Krungsri live order cancellation requires manual supervision."}


async def trade_modify_price(
    order_no: str,
    new_price: float,
    symbol: Optional[str] = None,
    platform: str = "CLICK2WIN"
) -> Dict[str, Any]:
    """Modifies the price of an open order on the board."""
    plat = platform.strip().upper()
    if plat in ["CLICK2WIN", "C2W"]:
        investor = _get_settrade_investor()
        if investor and settings.SETTRADE_ACCOUNT_NO_EQUITY:
            try:
                eq = investor.Equity(account_no=settings.SETTRADE_ACCOUNT_NO_EQUITY)
                res = eq.change_order(order_no=order_no, new_price=new_price)
                return {"success": True, "platform": "CLICK2WIN (Settrade Open API)", "response": res}
            except Exception as e:
                logger.warning(f"Pillar 3: Settrade API change_order failed: {e}")

        res_browser = await click2win_driver.modify_order_price(order_no=order_no, new_price=new_price)
        return {"success": res_browser.get("success", False), "platform": "CLICK2WIN (Browser)", "response": res_browser}

    return {"success": False, "error": "Krungsri live price modification is guarded."}


def register_trade_pillar(server):
    """Registers Pillar 3 tools into the MCP server."""
    server.tool()(trade_place_order)
    server.tool()(trade_cancel_order)
    server.tool()(trade_modify_price)
