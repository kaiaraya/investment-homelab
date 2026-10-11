import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import Position, SBLBorrowLot
from app.schemas.intelligence import ExtractedTPSL
from app.services.portfolio_overview_service import portfolio_overview_service
from app.services.price_negotiation_service import price_negotiation_service
from app.services.parser import signal_parser

router = APIRouter()
logger = logging.getLogger(__name__)


class NaturalLanguageTPSLRequest(BaseModel):
    message: str


@router.post("/overview", summary="Trigger 3.1 Portfolio Overview")
async def trigger_portfolio_overview(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Manually triggers the 3.1 Portfolio Overview and silent reconciliation workflow."""
    return await portfolio_overview_service.run_overview(db)


@router.post("/negotiate", summary="Trigger 3.4 Price Negotiation Round")
async def trigger_price_negotiation(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Runs an immediate Price Negotiation round evaluating Bid1/Offer1 for unmatched orders."""
    return await price_negotiation_service.run_negotiation_round(db)


@router.get("/positions", summary="Get Current Positions with TP/SL")
async def get_positions(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Retrieves all tracked positions, their TP/SL prices, and SBL pending return statuses."""
    stmt = select(Position).order_by(Position.volume.desc())
    res = await db.execute(stmt)
    positions = res.scalars().all()
    return [
        {
            "symbol": p.symbol,
            "position_type": p.position_type,
            "volume": p.volume,
            "avg_cost": p.avg_cost,
            "current_price": p.current_price,
            "prior_close_price": p.prior_close_price,
            "unrealized_pnl": p.unrealized_pnl,
            "take_profit_price": p.take_profit_price,
            "stop_loss_price": p.stop_loss_price,
            "is_sbl_pending_return": p.is_sbl_pending_return,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None
        }
        for p in positions
    ]


@router.post("/tpsl/natural-language", summary="Set TP/SL using Thai Natural Language")
async def set_tpsl_natural_language(
    payload: NaturalLanguageTPSLRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Parses a Thai conversational message (e.g. 'CPALL TP 68 SL 62, AP Short TP 7.50 SL 8.10')
    using Gemini AI / regex fallback and updates database positions.
    """
    tpsl_res = await signal_parser.parse_multi_stock_tpsl(payload.message)
    if not tpsl_res.items:
        raise HTTPException(status_code=400, detail="Could not extract any stock TP/SL values from message.")
    
    updated = await portfolio_overview_service.apply_tpsl_items(db, tpsl_res.items)
    return {
        "success": True,
        "method": tpsl_res.source_method,
        "confidence": tpsl_res.confidence,
        "updated_count": len(updated),
        "items": updated
    }


# ==============================================================================
# Daily Scenario Simulation Endpoints (10:00 - 19:30 Time-Warp Lab)
# ==============================================================================
from app.services.daily_scenario_runner import daily_scenario_runner
import os


class MarkdownLoadRequest(BaseModel):
    content: Optional[str] = None
    filename: Optional[str] = None


class RunStepRequest(BaseModel):
    slot_id: str


class ToggleLineRequest(BaseModel):
    enabled: bool


@router.get("/scenario/files", summary="List Available Strategy Markdown Files")
async def list_strategy_files() -> List[Dict[str, str]]:
    """Returns list of strategy markdown files found in the workspace."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    found = []
    candidates = [
        "DailyScenarioTest.md",
        "dailyorder.md",
        "ตัวอย่างคำสั่ง/usecase1.md",
        "ManualTest.md"
    ]
    for c in candidates:
        full_path = os.path.join(base_dir, c)
        if os.path.exists(full_path):
            found.append({"filename": c, "path": full_path})
    return found


@router.post("/scenario/load-markdown", summary="Load & Parse Strategy Markdown")
async def load_scenario_markdown(payload: MarkdownLoadRequest) -> Dict[str, Any]:
    """Parses strategy markdown text or loads it from a workspace file."""
    text_to_parse = payload.content

    if not text_to_parse and payload.filename:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        full_path = os.path.join(base_dir, payload.filename)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                text_to_parse = f.read()
        else:
            raise HTTPException(status_code=404, detail=f"File not found: {payload.filename}")

    if not text_to_parse:
        raise HTTPException(status_code=400, detail="Either 'content' or 'filename' must be provided.")

    return await daily_scenario_runner.load_markdown_strategy(text_to_parse)


@router.post("/scenario/run-step", summary="Run Single Time Slot in Daily Scenario")
async def run_scenario_step(payload: RunStepRequest) -> Dict[str, Any]:
    """Advances virtual clock to target slot and executes active/passive actions."""
    try:
        return await daily_scenario_runner.run_step(payload.slot_id)
    except Exception as e:
        logger.error(f"Error running scenario step {payload.slot_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenario/run-full", summary="Run Full 8-Slot Daily Scenario (10:00 - 19:30)")
async def run_scenario_full() -> Dict[str, Any]:
    """Runs all 8 time slots sequentially in accelerated Time-Warp mode (~10 seconds)."""
    try:
        return await daily_scenario_runner.run_full_day()
    except Exception as e:
        logger.error(f"Error running full scenario: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenario/toggle-line", summary="Toggle Live LINE Notification Push")
async def toggle_scenario_line(payload: ToggleLineRequest) -> Dict[str, Any]:
    """Enables or disables real LINE push during scenario testing."""
    state = daily_scenario_runner.toggle_live_line(payload.enabled)
    return {"live_line_enabled": state}


@router.get("/scenario/status", summary="Get Daily Scenario Runner Status")
async def get_scenario_status() -> Dict[str, Any]:
    """Retrieves runner status, execution logs, and live LINE toggle state."""
    return daily_scenario_runner.get_status()


# =========================================================================
# Dedicated Live Order Negotiation Endpoints (TradeMan Real System)
# =========================================================================

class NegotiationLineRequest(BaseModel):
    broker_order_no: str
    symbol: str
    side: str
    current_price: float
    target_price: float
    volume: int
    reason: Optional[str] = None


class NegotiationDirectModifyRequest(BaseModel):
    broker_order_no: str
    symbol: str
    side: str
    new_price: float
    volume: int
    bypass_dry_run: bool = False


@router.get("/scenario/negotiation/live-orders", summary="Scrape & Evaluate Live Unmatched Orders from TradeMan")
async def get_live_negotiation_orders() -> Dict[str, Any]:
    """
    Directly scrapes TradeMan Order Status DOM for open/unmatched orders,
    queries Top Bid (Bid 1) and Top Offer (Offer 1) in real-time,
    and returns calculated negotiation proposals.
    """
    try:
        orders = await price_negotiation_service.scan_and_evaluate_live_orders()
        return {
            "status": "SUCCESS",
            "count": len(orders),
            "orders": orders
        }
    except Exception as e:
        logger.error(f"Error scraping live orders for negotiation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scenario/negotiation/dispatch-line", summary="Send Interactive Negotiation Card to LINE")
async def dispatch_negotiation_card_to_line(payload: NegotiationLineRequest) -> Dict[str, Any]:
    """Dispatches an interactive HITL approval card for a specific order to the user's LINE."""
    proposal = {
        "broker_order_no": payload.broker_order_no,
        "symbol": payload.symbol.upper(),
        "side": payload.side.upper(),
        "current_price": payload.current_price,
        "target_price": payload.target_price,
        "volume": payload.volume,
        "reason": payload.reason or f"ต่อราคาตามกรอบ Bid 1 / Offer 1 สำหรับ {payload.symbol.upper()}",
        "needs_adjustment": True
    }
    await price_negotiation_service.dispatch_single_order_card(proposal)
    return {
        "status": "SUCCESS",
        "message": f"Dispatched negotiation card for {payload.symbol} ({payload.broker_order_no}) to LINE"
    }


@router.post("/scenario/negotiation/execute-direct", summary="Execute Price Modification Directly on TradeMan")
async def execute_direct_price_modification(
    payload: NegotiationDirectModifyRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Executes price modification directly on TradeMan (or dry run simulation).
    Supports bypass_dry_run toggle for live order modification.
    """
    try:
        res = await price_negotiation_service.execute_price_adjustment(
            db=db,
            broker_order_no=payload.broker_order_no,
            symbol=payload.symbol.upper(),
            side=payload.side.upper(),
            new_price=payload.new_price,
            volume=payload.volume,
            bypass_dry_run=payload.bypass_dry_run,
            force_live=True
        )
        return {
            "status": "SUCCESS",
            "result": res
        }
    except Exception as e:
        logger.error(f"Error executing direct price modification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
