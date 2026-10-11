from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator
from app.schemas.auth import HybridBaseModel, BrokerPlatform


class SBLCategory(str, Enum):
    SET50 = "SET50"
    SET100 = "SET100"
    NEWSEC = "NEWSEC"
    XD_XR = "XD_XR"


class SBLStockItem(HybridBaseModel):
    symbol: str = Field(..., description="Stock symbol (e.g. CPALL, DELTA)")
    available_qty: int = Field(default=0, ge=0, description="Available share volume for borrowing")
    borrow_fee_pct: float = Field(default=3.50, description="Borrow fee interest rate % p.a.")
    initial_margin_pct: float = Field(default=50.0, description="Initial Margin requirement %")
    category: SBLCategory = Field(default=SBLCategory.SET50, description="Pool category")
    corporate_action_sign: Optional[str] = Field(default=None, description="XD, XR, XM or other corporate signs")
    page_number: int = Field(default=1, description="Page index where item was found")
    is_borrowable: bool = Field(default=True, description="True if available_qty > 0 and not blocked by XD/XR")

    @field_validator("symbol", mode="before")
    @classmethod
    def clean_symbol(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return str(v)


class SBLCategorySummary(HybridBaseModel):
    category: SBLCategory
    total_pages_scraped: int = Field(default=0)
    total_stocks: int = Field(default=0)
    total_borrowable_shares: int = Field(default=0)
    stocks: List[SBLStockItem] = Field(default_factory=list)


class SBLComprehensiveSnapshot(HybridBaseModel):
    broker: BrokerPlatform = Field(default=BrokerPlatform.TRADEMAN, description="Broker platform")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Scrape timestamp")
    categories: Dict[str, SBLCategorySummary] = Field(default_factory=dict)
    grand_total_stocks: int = Field(default=0)
    grand_total_borrowable_shares: int = Field(default=0)
