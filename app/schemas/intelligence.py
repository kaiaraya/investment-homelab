from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.order import OrderSide


class ExtractedOrder(BaseModel):
    symbol: str
    side: OrderSide
    volume: int
    price: float
    reason: Optional[str] = None
    section: Optional[str] = None  # e.g. "5.1 Hard Exit & Cut Loss", "5.2 Climax TP"
    is_valid_lot: bool = True
    validation_error: Optional[str] = None
    volume_pct: Optional[float] = None  # e.g. 50.0 for "half", 100.0 for "all"
    is_relative_volume: bool = False
    clamped_from_volume: Optional[int] = None  # Original requested volume if clamped
    price_advantage_pct: Optional[float] = None  # Positive % if current market is better than target
    price_advantage_label: Optional[str] = None  # e.g. "ราคาตลาดดีกว่าเป้า +0.55%"
    order_id: Optional[str] = None


class ExtractedWatchlistTrigger(BaseModel):
    symbol: str
    action: str  # SELL, COVER, BUY, SHORT
    volume: int
    condition: str  # PRICE_BELOW, PRICE_ABOVE
    trigger_price: float
    current_status: Optional[str] = None  # e.g. "HOLD 600 หุ้น ติดลบ -1.96%"
    section: Optional[str] = None
    notes: Optional[str] = None


class ExtractedHoldPosition(BaseModel):
    symbol: str
    volume: int
    position_type: str = "LONG"  # "LONG" or "SHORT"
    current_return_pct: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    cost_price: Optional[float] = None
    current_price: Optional[float] = None
    days_held: Optional[int] = None
    group_type: Optional[str] = "ACTIVE_SWING"  # "ACTIVE_SWING" or "WEED_OUT"
    warning_note: Optional[str] = None
    note: Optional[str] = None


class SignalParseResult(BaseModel):
    total_parsed: int
    immediate_orders: List[ExtractedOrder] = Field(default_factory=list)
    watchlist_triggers: List[ExtractedWatchlistTrigger] = Field(default_factory=list)
    hold_positions: List[ExtractedHoldPosition] = Field(default_factory=list)
    raw_sections_found: List[str] = Field(default_factory=list)
    queued_order_ids: List[str] = Field(default_factory=list)
    strategy_summary: Optional[str] = None
    source_method: str = "gemini_3.6_flash"  # "gemini_3.6_flash" or "regex_fallback"
    retry_count: int = 0
    error_message: Optional[str] = None


class ExtractedTPSL(BaseModel):
    symbol: str
    side: str = "LONG"  # LONG or SHORT
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    notes: Optional[str] = None


class TPSLParseResult(BaseModel):
    items: List[ExtractedTPSL] = Field(default_factory=list)
    confidence: float = 1.0
    source_method: str = "gemini_api"  # gemini_api or regex_fallback


class EODOrderItem(BaseModel):
    symbol: str
    side: str
    volume: int
    price: float
    status: str  # MATCHED, CANCELLED, REJECTED, UNMATCHED
    broker_order_no: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: Optional[str] = None


class SBLHoldingItem(BaseModel):
    symbol: str
    borrowed_volume: int
    borrow_date: str
    days_held: int
    accrued_fee_thb: float
    ex_dividend_warning: Optional[str] = None


class EODReportSummary(BaseModel):
    report_time: str
    total_orders: int
    matched_count: int
    failed_or_unmatched_count: int
    orders_matched: List[EODOrderItem] = Field(default_factory=list)
    orders_unmatched: List[EODOrderItem] = Field(default_factory=list)
    realized_pnl_thb: float = 0.0
    realized_pnl_pct: float = 0.0
    unrealized_pnl_thb: float = 0.0
    excess_equity_thb: float = 0.0  # ค่า EE
    cash_balance_thb: float = 0.0
    sbl_holdings: List[SBLHoldingItem] = Field(default_factory=list)
    strategy_notes: Optional[str] = None
