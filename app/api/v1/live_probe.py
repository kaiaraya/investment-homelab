"""
Live On-Demand Probes & Time Warp Simulation API.
Provides endpoints for:
1. Zero-risk Live DOM Scraping probes (Portfolio, EE/Cash, SBL stock, Unmatched, Bid/Offer).
2. Direct triggers for 3.1, 3.4, and 3.5 without waiting for the clock.
3. Time Warp clock controls (speed, fast-forward, pause/resume).
4. Scenario Matrix execution (Scenarios 1 to 5).
"""

import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from app.core.virtual_clock import virtual_clock
from app.browser.auth_driver import auth_driver
from app.browser.trademan_driver import trademan_driver
from app.browser.broker_factory import get_broker_driver, get_auth_driver
from app.services.phase3_scheduler import phase3_scheduler
from app.services.scenario_matrix import scenario_matrix
from app.services.sbl_intelligence_service import sbl_intelligence_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["Simulation & Live Probes"])


# -------------------------------------------------------------
# Request Schemas
# -------------------------------------------------------------

class ClockSpeedRequest(BaseModel):
    speed_multiplier: float = 60.0
    start_time: str = "09:30"


class AdvanceTimeRequest(BaseModel):
    target_time: str  # e.g. "10:15", "11:00", "15:30", "16:35"


class ScenarioRunRequest(BaseModel):
    scenario: int  # 1 to 5
    hitl_mode: str = "auto"  # "auto" or "interactive"


# -------------------------------------------------------------
# 1. Virtual Clock Controls
# -------------------------------------------------------------

@router.get("/clock")
def get_clock_status():
    """Returns the current status of the Virtual Clock."""
    return virtual_clock.format_status()


@router.post("/clock/speed")
def set_clock_speed(req: ClockSpeedRequest):
    """Sets accelerated clock mode (e.g. 60x where 1 real second = 1 virtual minute)."""
    virtual_clock.set_accelerated_mode(req.speed_multiplier, req.start_time)
    return virtual_clock.format_status()


@router.post("/clock/advance")
def advance_clock(req: AdvanceTimeRequest):
    """Fast-forwards virtual clock directly to target hour."""
    virtual_clock.advance_to(req.target_time)
    return virtual_clock.format_status()


@router.post("/clock/realtime")
def reset_to_realtime():
    """Restores real system time."""
    virtual_clock.set_real_time_mode()
    return virtual_clock.format_status()


@router.post("/clock/pause")
def pause_clock():
    """Pauses the virtual clock."""
    virtual_clock.pause()
    return virtual_clock.format_status()


@router.post("/clock/resume")
def resume_clock():
    """Resumes the virtual clock."""
    virtual_clock.resume()
    return virtual_clock.format_status()


# -------------------------------------------------------------
# 2. 5 Comprehensive Scenario Matrix Runners
# -------------------------------------------------------------

@router.post("/scenario/run")
async def run_scenario(req: ScenarioRunRequest):
    """Executes one of the 5 comprehensive trading scenarios."""
    s_num = req.scenario
    mode = req.hitl_mode

    if s_num == 1:
        return await scenario_matrix.run_scenario_1_normal(mode)
    elif s_num == 2:
        return await scenario_matrix.run_scenario_2_tpsl_triggers(mode)
    elif s_num == 3:
        return await scenario_matrix.run_scenario_3_volatility_rebound(mode)
    elif s_num == 4:
        return await scenario_matrix.run_scenario_4_unmatched_negotiation_failed(mode)
    elif s_num == 5:
        return await scenario_matrix.run_scenario_5_sbl_held_carrying_fee(mode)
    else:
        raise HTTPException(status_code=400, detail="Invalid scenario number (Choose 1 to 5).")


# -------------------------------------------------------------
# 3. Live On-Demand Probes (Zero Financial Risk - Real Web DOM)
# -------------------------------------------------------------

@router.post("/live/probe/portfolio")
async def probe_live_portfolio(account_type: Optional[str] = Query(None, description="EQUITY or DERIVATIVES")):
    """Immediately scrapes holdings from active broker/Click2Win session (Zero Risk)."""
    driver = get_broker_driver()
    if hasattr(driver, "scrape_portfolio"):
        import inspect
        sig = inspect.signature(driver.scrape_portfolio)
        if "account_type" in sig.parameters:
            holdings = await driver.scrape_portfolio(account_type=account_type)
        else:
            holdings = await driver.scrape_portfolio()
    else:
        holdings = []
    return {"status": "SUCCESS", "count": len(holdings), "holdings": holdings}


@router.post("/live/probe/account")
async def probe_live_account():
    """Immediately scrapes Excess Equity and Cash from active broker/Click2Win (Zero Risk)."""
    driver = get_broker_driver()
    acc = await driver.scrape_account_summary()
    return {"status": "SUCCESS", "account": acc}


@router.post("/live/probe/sbl-stock")
async def probe_live_sbl_stock(symbol: str = Query(..., description="Stock symbol to query (e.g. CPALL)")):
    """Immediately checks SBL inventory for a stock (Read-only, Zero Risk)."""
    driver = get_broker_driver()
    if hasattr(driver, "scrape_sbl_inventory"):
        info = await driver.scrape_sbl_inventory(symbol)
    else:
        info = {"symbol": symbol, "available_volume": 0, "status": "NOT_SUPPORTED_IN_SANDBOX"}
    return {"status": "SUCCESS", "sbl_info": info}


@router.post("/live/probe/sbl-all-tabs")
async def probe_live_sbl_all_tabs():
    """Immediately scrapes all SBL tabs: SET50, XD/XR corporate actions, and SBL Portfolio lots."""
    driver = get_broker_driver()
    if hasattr(driver, "scrape_sbl_all_tabs"):
        raw_sbl = await driver.scrape_sbl_all_tabs()
    else:
        raw_sbl = {"status": "SUCCESS", "data": {"sbl_lots": []}}
    return raw_sbl


@router.post("/live/probe/sbl-intelligence")
async def probe_live_sbl_intelligence():
    """Scrapes all SBL tabs and executes Gemini AI decision supervision."""
    driver = get_broker_driver()
    if hasattr(driver, "scrape_sbl_all_tabs"):
        raw_sbl = await driver.scrape_sbl_all_tabs()
    else:
        raw_sbl = {"status": "SUCCESS", "data": {"sbl_lots": []}}
    sbl_data = raw_sbl.get("data", {})
    holdings = await driver.scrape_portfolio()
    analysis = await sbl_intelligence_service.analyze_sbl_decision(sbl_data, holdings)
    return {
        "status": "SUCCESS",
        "sbl_data": sbl_data,
        "holdings_count": len(holdings),
        "ai_analysis": analysis
    }


@router.post("/live/probe/krungsri-sbl/sync")
async def probe_krungsri_sbl_sync():
    """Triggers an On-Demand full scan of Krungsri SBL Real Time (/sblweb/MainSBL.aspx)."""
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
    res = await krungsri_sbl_driver.scrape_full_pool(headless=True)
    return res


@router.get("/live/probe/krungsri-sbl/cached")
async def probe_krungsri_sbl_cached():
    """Returns cached Krungsri SBL Real Time inventory and XD/XR risks."""
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
    data = krungsri_sbl_driver.get_cached_data()
    return {"status": "SUCCESS", "data": data}


@router.get("/live/probe/krungsri-sbl/check-risk")
async def probe_krungsri_sbl_check_risk(symbol: str = Query(..., description="Stock symbol to evaluate")):
    """Checks symbol against Krungsri SBL XD/XR risk calendar and available borrow pool."""
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver
    risk_info = krungsri_sbl_driver.check_symbol_risk(symbol)
    return {"status": "SUCCESS", "risk_info": risk_info}


@router.post("/live/probe/unmatched")
async def probe_live_unmatched(account_type: Optional[str] = Query(None, description="EQUITY or DERIVATIVES")):
    """Immediately reads unmatched orders from active broker/Click2Win Order Status (Zero Risk)."""
    driver = get_broker_driver()
    if hasattr(driver, "scrape_unmatched_orders"):
        orders = await driver.scrape_unmatched_orders(account_type=account_type)
    else:
        orders = []
    return {"status": "SUCCESS", "count": len(orders), "unmatched_orders": orders}


@router.post("/live/probe/bid-offer")
async def probe_live_bid_offer(symbol: str = Query(..., description="Stock symbol (e.g. CPALL)")):
    """Immediately reads top Bid/Offer from active broker/Click2Win (Zero Risk)."""
    driver = get_broker_driver()
    bid_offer = await driver.get_market_bid_offer(symbol)
    return {"status": "SUCCESS", "symbol": symbol, "market_depth": bid_offer}


# -------------------------------------------------------------
# 4. Live Trigger Probes (Trigger scheduled centers immediately)
# -------------------------------------------------------------

@router.post("/live/trigger/overview")
async def trigger_overview_now():
    """Forces an immediate run of 3.1 Portfolio Overview & LINE notification."""
    res = await phase3_scheduler.trigger_portfolio_overview()
    return {"status": "SUCCESS", "result": res}


@router.post("/live/apply-tpsl")
async def apply_live_tpsl(
    tp_pct: float = Query(5.0, description="Take profit percentage (default: 5.0%)"),
    sl_pct: float = Query(3.0, description="Stop loss percentage (default: 3.0%)")
):
    """
    Applies automatic Take Profit (+5%) and Stop Loss (-3%) to all open positions in SQLite.
    Properly aligns with LONG (TP > Cost, SL < Cost) and SHORT (TP < Cost, SL > Cost).
    """
    from app.db.session import AsyncSessionLocal
    from app.services.portfolio_overview_service import portfolio_overview_service

    async with AsyncSessionLocal() as db:
        updated = await portfolio_overview_service.apply_percentage_tpsl_to_open_positions(db, tp_pct, sl_pct)
        return {
            "status": "SUCCESS",
            "updated_count": len(updated),
            "tp_pct": tp_pct,
            "sl_pct": sl_pct,
            "positions": updated
        }



@router.post("/live/trigger/negotiation")
async def trigger_negotiation_now(round_name: str = Query("11:00")):
    """Forces an immediate run of 3.4 Price Negotiation Round."""
    res = await phase3_scheduler.trigger_price_negotiation(round_name)
    return {"status": "SUCCESS", "result": res}


@router.post("/live/trigger/eod")
async def trigger_eod_now():
    """Forces an immediate run of 3.5 End-of-Day Summary & Report."""
    res = await phase3_scheduler.trigger_eod_summary()
    return {"status": "SUCCESS", "result": res}


@router.get("/live/snapshot")
async def take_live_snapshot():
    """Captures diagnostic screenshot and HTML dump of the current live browser."""
    res = await auth_driver.take_diagnostic_snapshot("live_debug")
    return {"status": "SUCCESS", "snapshot": res, "url": auth_driver.current_url}


@router.get("/schedule")
def get_daily_schedule():
    """Returns the 8 market regimes and today's random execution points."""
    return phase3_scheduler.get_daily_schedule()


@router.post("/live/probe/set-summary")
async def probe_set_summary(period_label: str = Query("10:30", description="Label for market observation period")):
    """Scrapes SET market index stats, saves to SQLite, and sends 1-line update to LINE."""
    from app.services.market_monitor_service import market_monitor_service
    res = await market_monitor_service.capture_and_report(period_label=period_label)
    return {"status": "SUCCESS", "result": res}


@router.post("/live/trigger/random-point")
async def trigger_random_point_now(round_time: str = Query("11:15")):
    """Forces an immediate run of the combined 3.2-3.4 random point routine."""
    res = await phase3_scheduler.trigger_random_execution_point(round_time=round_time)
    return {"status": "SUCCESS", "result": res}
