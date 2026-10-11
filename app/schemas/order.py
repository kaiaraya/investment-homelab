from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"
    LONG = "LONG"


class OrderPosition(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    AUTO = "AUTO"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    OPEN = "OPEN"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    MATCHED = "MATCHED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    CARRY_OVER_PENDING = "CARRY_OVER_PENDING"
    EXPIRED_EOD = "EXPIRED_EOD"
    AWAITING_HITL_CONFIRMATION = "AWAITING_HITL_CONFIRMATION"
    SCHEDULED = "SCHEDULED"



class OrderBase(BaseModel):
    symbol: str = Field(..., description="Stock or TFEX symbol, e.g. CPALL, SPALIU26")
    side: OrderSide = Field(..., description="BUY, SELL, SHORT, COVER, LONG")
    position: Optional[str] = Field(default=None, description="OPEN, CLOSE, AUTO (TFEX)")
    volume: int = Field(..., gt=0, description="Volume of shares or contracts")
    price: float = Field(..., gt=0, description="Price in THB")


class OrderCreate(OrderBase):
    source: Optional[str] = "api"
    broker_order_no: Optional[str] = None


class OrderResponse(OrderBase):
    order_id: str
    broker_order_no: Optional[str] = None
    position: Optional[str] = None
    status: OrderStatus
    error_message: Optional[str] = None
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceAdjustmentResult(BaseModel):
    success: bool
    status: str
    symbol: str
    side: str
    old_order_no: str
    new_order_no: str
    new_price: float
    volume: int
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class CancelOrderResult(BaseModel):
    success: bool
    status: str
    broker_order_no: str
    symbol: Optional[str] = None
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())

