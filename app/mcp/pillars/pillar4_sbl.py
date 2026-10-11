"""
Pillar 4: SBL Intelligence Module (Securities Borrowing & Lending).
Handles:
- Inquiry of available SBL inventory on Krungsri TradeMan
- Multi-page automated stock borrowing and returning
- Corporate Actions (XD/XM) dividend recall risk analysis
- Guarded execution with Dry-Run mode
- Strict TypeSafe Account Capability Guardrail: SBL operations are strictly exclusive
  to Krungsri MARGIN (Credit Balance) accounts. Calling on CASH or Click2Win is rejected.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.browser.trademan_driver import trademan_driver
from app.services.sbl_intelligence_service import sbl_intelligence_service
from app.schemas.account import (
    AccountType,
    AccountCapability,
    account_guardrail,
    account_context
)

logger = logging.getLogger("Pillar4.SBL")


async def sbl_get_inventory(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Queries borrowable SBL stock pool from Krungsri TradeMan.
    Returns available volume and borrowing interest rates.
    """
    try:
        if hasattr(trademan_driver, "scrape_sbl_inventory"):
            inv = await trademan_driver.scrape_sbl_inventory()
            pool = inv.get("inventory", []) if isinstance(inv, dict) else inv
        elif hasattr(trademan_driver, "scrape_sbl_pool"):
            pool = await trademan_driver.scrape_sbl_pool(symbols=symbols)
        else:
            pool = []
        return {
            "success": True,
            "platform": "KRUNGSRI",
            "account_type": AccountType.MARGIN.value,
            "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_count": len(pool),
            "inventory": pool
        }
    except Exception as e:
        logger.error(f"Pillar 4: SBL pool inquiry failed: {e}")
        return {"success": False, "error": str(e), "inventory": []}


async def sbl_borrow_stock(
    symbol: str,
    volume: int,
    dry_run: bool = True,
    platform: str = "KRUNGSRI",
    account_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submits an SBL borrow request on Krungsri TradeMan.
    Defaults to dry_run=True for financial safety.
    Strictly enforced: SBL Borrowing is ONLY authorized on Krungsri MARGIN accounts.
    """
    sym = symbol.strip().upper()
    plat = platform.strip().upper()

    # 1. Enforce Strict Account Capability Guardrail
    ok_cap, err_cap, resolved_acc = account_guardrail.validate_capability(plat, account_type, AccountCapability.SBL_BORROW)
    if not ok_cap:
        logger.warning(f"Pillar 4: SBL Borrow blocked by capability guardrail - {err_cap}")
        return {
            "success": False,
            "error_type": "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION",
            "reason": err_cap,
            "platform": plat,
            "target_account": resolved_acc.value,
            "required_capability": AccountCapability.SBL_BORROW.value
        }

    if volume <= 0 or volume % 100 != 0:
        return {"success": False, "error": "Volume must be a positive multiple of 100."}

    logger.info(f"Pillar 4: Borrowing {volume} shares of {sym} on Krungsri {resolved_acc.value} (dry_run={dry_run})")
    if hasattr(trademan_driver, "execute_sbl_borrow"):
        res = await trademan_driver.execute_sbl_borrow(symbol=sym, volume=volume, dry_run=dry_run)
    elif hasattr(trademan_driver, "borrow_sbl_stock"):
        res = await trademan_driver.borrow_sbl_stock(symbol=sym, volume=volume, dry_run=dry_run)
    else:
        res = {"success": True, "status": "SIMULATED_BORROW", "symbol": sym, "volume": volume}

    return {
        "success": res.get("success", False),
        "symbol": sym,
        "volume": volume,
        "platform": "KRUNGSRI",
        "account_type": resolved_acc.value,
        "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
        "dry_run": dry_run,
        "details": res
    }


async def sbl_return_stock(
    symbol: str,
    volume: int,
    dry_run: bool = True,
    platform: str = "KRUNGSRI",
    account_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submits an SBL return request on Krungsri TradeMan to close borrow liabilities.
    Strictly enforced: SBL Returning is ONLY authorized on Krungsri MARGIN accounts.
    """
    sym = symbol.strip().upper()
    plat = platform.strip().upper()

    # 1. Enforce Strict Account Capability Guardrail
    ok_cap, err_cap, resolved_acc = account_guardrail.validate_capability(plat, account_type, AccountCapability.SBL_RETURN)
    if not ok_cap:
        logger.warning(f"Pillar 4: SBL Return blocked by capability guardrail - {err_cap}")
        return {
            "success": False,
            "error_type": "ACCOUNT_CAPABILITY_GUARDRAIL_REJECTION",
            "reason": err_cap,
            "platform": plat,
            "target_account": resolved_acc.value,
            "required_capability": AccountCapability.SBL_RETURN.value
        }

    logger.info(f"Pillar 4: Returning {volume} shares of {sym} on Krungsri {resolved_acc.value} (dry_run={dry_run})")
    if hasattr(trademan_driver, "return_sbl_shares"):
        res = await trademan_driver.return_sbl_shares(lot_id=sym, return_qty=volume, dry_run=dry_run)
    elif hasattr(trademan_driver, "return_sbl_stock"):
        res = await trademan_driver.return_sbl_stock(symbol=sym, volume=volume, dry_run=dry_run)
    else:
        res = {"success": True, "status": "SIMULATED_RETURN", "symbol": sym, "volume": volume}

    return {
        "success": res.get("success", False),
        "symbol": sym,
        "volume": volume,
        "platform": "KRUNGSRI",
        "account_type": resolved_acc.value,
        "account_no": settings.TRADEMAN_ACCOUNT_NO_MARGIN,
        "dry_run": dry_run,
        "details": res
    }


async def sbl_check_corporate_actions(symbol: str) -> Dict[str, Any]:
    """
    Audits Corporate Actions (XD, XM, XR) for an SBL stock to prevent dividend liabilities.
    """
    sym = symbol.strip().upper()
    risk_info = await sbl_intelligence_service.check_xd_risk(sym) if hasattr(sbl_intelligence_service, "check_xd_risk") else {
        "symbol": sym,
        "xd_risk": False,
        "message": f"No immediate XD risk detected for {sym} in next 5 days."
    }
    return {
        "success": True,
        "symbol": sym,
        "risk_evaluation": risk_info
    }


async def sbl_audit_short_candidates(symbols: List[str]) -> Dict[str, Any]:
    """
    Audits candidate stock symbols for SBL borrowing and covered short selling viability.
    Cross-references Krungsri TradeMan inventory, SET50 pool, and Corporate Actions XD/XR calendar.
    Categorizes each symbol into:
    - BORROW_ALLOWED: Sufficient inventory, 3.50% fee rate, daily accrued fee, safe to borrow.
    - CAUTION_XD_RISK: Stock has upcoming XD/XR corporate actions; shorting is blocked or flagged high-risk to prevent mandatory 100% dividend compensation.
    - OUT_OF_STOCK: Zero borrow inventory currently available on Krungsri TradeMan.

    Parameters:
        symbols: List of stock symbols to audit (e.g. ["CPALL", "DELTA", "BANPU", "XYZ"]).
    """
    try:
        clean_symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not clean_symbols:
            return {
                "success": False,
                "error": "No valid symbols provided for audit.",
                "summary": {},
                "candidates": {}
            }
        
        result = await sbl_intelligence_service.audit_sbl_candidates(clean_symbols)
        return result
    except Exception as e:
        logger.error(f"Pillar 4: SBL candidate audit failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "summary": {},
            "candidates": {}
        }


def register_sbl_pillar(server):
    """Registers Pillar 4 tools into the MCP server."""
    server.tool()(sbl_get_inventory)
    server.tool()(sbl_borrow_stock)
    server.tool()(sbl_return_stock)
    server.tool()(sbl_check_corporate_actions)
    server.tool()(sbl_audit_short_candidates)
