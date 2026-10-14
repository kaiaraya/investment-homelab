"""Krungsri Quick Trade passive price negotiation REST API (Pillar 6).

POST /api/v1/krungsri/quicktrade/negotiate-price
Broker-isolated: this router only drives the Quick Trade driver.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.quicktrade_negotiation_service import negotiate_order_price

router = APIRouter()


class NegotiatePriceRequest(BaseModel):
    order_no: str
    account_no: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    price: Optional[float] = None
    balance: Optional[int] = None
    trade_date: Optional[str] = None
    dry_run: Optional[bool] = None


@router.post("/negotiate-price")
async def negotiate_price(payload: NegotiatePriceRequest) -> Dict[str, Any]:
    """Passively re-price an existing Krungsri Quick Trade order.

    BUY -> Best Bid 1, SELL -> Best Offer 1, SHORT -> max(Best Offer 1, LastPrice)
    with a FAIL-CLOSED ``UPTICK_VIOLATION`` when Best Offer 1 < LastPrice. The volume
    is never changed; submission is gated by ``settings.DRY_RUN_MODE``.
    """
    return await negotiate_order_price(
        order_no=payload.order_no,
        account_no=payload.account_no,
        symbol=payload.symbol,
        side=payload.side,
        price=payload.price,
        balance=payload.balance,
        trade_date=payload.trade_date,
        dry_run=payload.dry_run,
    )
