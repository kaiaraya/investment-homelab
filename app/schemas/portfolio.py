from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
from pydantic import Field, field_validator
from app.schemas.auth import HybridBaseModel, BrokerPlatform


class PositionType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    BORROWED = "BORROWED"


class HoldingPosition(HybridBaseModel):
    raw_symbol: str = Field(..., description="Raw symbol string from broker DOM, e.g. 'AOT(S)' or 'CPALL'")
    symbol: str = Field(..., description="Cleaned uppercase symbol, e.g. 'AOT'")
    position_type: PositionType = Field(default=PositionType.LONG, description="LONG, SHORT, or BORROWED")
    volume: int = Field(default=0, ge=0, description="Available sellable/coverable volume")
    on_hand: int = Field(default=0, ge=0, description="Total on-hand volume")
    sellable: int = Field(default=0, ge=0, description="Sellable volume")
    avg_cost: float = Field(default=0.0, ge=0.0, description="Average cost per share in THB")
    current_price: float = Field(default=0.0, ge=0.0, description="Current market price in THB")
    prior_close_price: Optional[float] = Field(default=None, description="Previous trading day close price")
    cost_value: float = Field(default=0.0, description="Total cost value in THB")
    market_value: float = Field(default=0.0, description="Total market value in THB")
    unrealized_pnl: float = Field(default=0.0, description="Unrealized profit/loss in THB")
    pnl_pct: float = Field(default=0.0, description="Unrealized profit/loss percentage")
    take_profit_price: Optional[float] = Field(default=None, description="Calculated TP level")
    stop_loss_price: Optional[float] = Field(default=None, description="Calculated SL level")

    @field_validator("symbol", mode="before")
    @classmethod
    def clean_symbol(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.replace("(S)", "").replace("(B)", "").strip().upper()
        return str(v)


class AccountSummary(HybridBaseModel):
    broker: BrokerPlatform = Field(default=BrokerPlatform.TRADEMAN, description="Broker platform")
    account_no: Optional[str] = Field(default=None, description="Trading account number")
    line_available: float = Field(default=0.0, description="Line available / credit limit in THB")
    cash_balance: float = Field(default=0.0, description="Cash balance in THB")
    excess_equity: float = Field(default=0.0, description="Excess equity (EE) in THB")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of scraping")


class PortfolioSnapshot(HybridBaseModel):
    broker: BrokerPlatform = Field(default=BrokerPlatform.TRADEMAN, description="Broker platform")
    account: Optional[AccountSummary] = Field(default=None, description="Account cash and limits")
    positions: List[HoldingPosition] = Field(default_factory=list, description="List of holding positions")
    total_cost: float = Field(default=0.0, description="Sum of cost values across all positions")
    total_market_value: float = Field(default=0.0, description="Sum of market values")
    total_unrealized_pnl: float = Field(default=0.0, description="Sum of unrealized PnL")
    overall_pnl_pct: float = Field(default=0.0, description="Overall portfolio PnL percentage")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Snapshot timestamp")
