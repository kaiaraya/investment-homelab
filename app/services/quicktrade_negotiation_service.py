"""Krungsri Quick Trade passive price negotiation policy (Pillar 6).

Pure, browser-free policy core plus the orchestration that binds it to the Quick
Trade driver (``app/brokers/krungsri/quicktrade_driver.py``). Broker-isolated:
nothing here touches TradeMan's cancel/resend path or any other broker.

Safety invariants (``TASK-krungsri-quicktrade-passive-negotiate``):
1. **PASSIVE ONLY** - BUY -> Best Bid 1, SELL -> Best Offer 1; never cross the spread.
2. **SET UPTICK RULE for SHORT** - ``target = max(Best Offer 1, LastPrice)``; if
   ``Best Offer 1 < LastPrice`` (down-tick) the amendment is FAIL-CLOSED with
   ``UPTICK_VIOLATION`` - a short may never be amended to a price below last.
3. **VOLUME INTEGRITY** - only the price is amended; the volume stays equal to the
   order's remaining balance.
4. **ANTI-MOCK** - an unreadable quote yields a failure, never a guessed price.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    SHORT = "SHORT"
    OPEN_SHORT = "OPEN_SHORT"
    COVER = "COVER"      # buy-to-cover: a BUY on the tape
    LONG = "LONG"        # buy-to-open: a BUY on the tape


class NegotiationOutcome(str, Enum):
    OK = "OK"
    NO_CHANGE = "NO_CHANGE"
    UPTICK_VIOLATION = "UPTICK_VIOLATION"
    NO_QUOTE = "NO_QUOTE"
    UNSUPPORTED_SIDE = "UNSUPPORTED_SIDE"


class Quote(BaseModel):
    symbol: str
    best_bid: Optional[float] = None
    best_offer: Optional[float] = None
    last: Optional[float] = None


class OrderSnapshot(BaseModel):
    order_no: str
    symbol: str
    side: str
    price: float
    balance: int                      # unfilled volume - must remain unchanged
    account_no: Optional[str] = None
    trade_date: Optional[str] = None


class NegotiationDecision(BaseModel):
    outcome: NegotiationOutcome
    side: str = ""
    current_price: float = 0.0
    target_price: Optional[float] = None
    volume: Optional[int] = None       # always == the order balance (invariant 3)
    reason: str = ""


# --- pure policy ----------------------------------------------------------

_BUY_SIDES = {Side.BUY, Side.COVER, Side.LONG}
_SELL_SIDES = {Side.SELL}
_SHORT_SIDES = {Side.SHORT, Side.OPEN_SHORT}


def _normalise_side(side: Any) -> Optional[Side]:
    if isinstance(side, Side):
        return side
    try:
        return Side(str(side or "").strip().upper())
    except ValueError:
        return None


def compute_passive_price(
    side: Any,
    best_bid: Optional[float],
    best_offer: Optional[float],
    last: Optional[float],
) -> NegotiationDecision:
    """Compute the passive target price for ``side`` from the live quote.

    Returns a :class:`NegotiationDecision` whose ``outcome`` is ``OK`` + ``target_price``
    on success, or an explicit failure (``UPTICK_VIOLATION`` / ``NO_QUOTE`` /
    ``UNSUPPORTED_SIDE``) - never a fabricated figure.
    """
    s = _normalise_side(side)
    if s is None:
        return NegotiationDecision(
            outcome=NegotiationOutcome.UNSUPPORTED_SIDE,
            reason=f"unsupported side {side!r}",
        )

    if s in _BUY_SIDES:
        if best_bid is None:
            return NegotiationDecision(
                outcome=NegotiationOutcome.NO_QUOTE, reason="best bid unavailable")
        return NegotiationDecision(outcome=NegotiationOutcome.OK, target_price=best_bid)

    if s in _SELL_SIDES:
        if best_offer is None:
            return NegotiationDecision(
                outcome=NegotiationOutcome.NO_QUOTE, reason="best offer unavailable")
        return NegotiationDecision(outcome=NegotiationOutcome.OK, target_price=best_offer)

    # SHORT / OPEN_SHORT - SET uptick rule: never amend below LastPrice.
    if best_offer is None or last is None:
        return NegotiationDecision(
            outcome=NegotiationOutcome.NO_QUOTE,
            reason="best offer and last price are both required for a short amendment",
        )
    if best_offer < last:
        return NegotiationDecision(
            outcome=NegotiationOutcome.UPTICK_VIOLATION,
            reason="Best Offer 1 < LastPrice (down-tick) - short may not be amended below last",
        )
    return NegotiationDecision(outcome=NegotiationOutcome.OK, target_price=max(best_offer, last))


def plan_negotiation(order: OrderSnapshot, quote: Quote) -> NegotiationDecision:
    """Bind a live quote to an order and produce the final decision.

    Preserves the order's remaining volume (invariant 3) and flips a no-op amendment
    (target == current price) to ``NO_CHANGE`` so the caller never re-submits needlessly.
    """
    d = compute_passive_price(order.side, quote.best_bid, quote.best_offer, quote.last)
    d.side = order.side
    d.current_price = order.price
    d.volume = order.balance
    if d.outcome is NegotiationOutcome.OK and d.target_price == order.price:
        d.outcome = NegotiationOutcome.NO_CHANGE
        d.reason = "target price equals the current price - nothing to amend"
    return d


# --- orchestration (binds the policy to the Quick Trade driver) ------------

async def negotiate_order_price(
    order_no: str,
    *,
    account_no: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    price: Optional[float] = None,
    balance: Optional[int] = None,
    trade_date: Optional[str] = None,
    pin: Optional[str] = None,
    dry_run: Optional[bool] = None,
    execute: bool = True,
) -> Dict[str, Any]:
    """Passively re-price an existing Krungsri Quick Trade order.

    Resolves the order snapshot from the driver when fields are missing, reads the
    live quote, applies the policy, and (on ``OK`` + ``execute``) amends the price
    in place via the driver. Never fabricates a result: unreadable quote/order, an
    uptick violation or a driver error are all reported as failures.
    """
    # Lazy import keeps this module browser-free at import time.
    from app.brokers.krungsri.quicktrade_driver import quicktrade_driver

    order_no = str(order_no or "").strip()
    if not order_no:
        return {"success": False, "order_no": order_no,
                "outcome": NegotiationOutcome.UNSUPPORTED_SIDE.value,
                "error": "order_no is required"}

    # 1. Resolve the order snapshot (fill any missing field from the ledger).
    if None in (symbol, side, price, balance):
        snap = await quicktrade_driver.get_order(order_no, account_no=account_no)
        if not snap.get("success"):
            return {"success": False, "order_no": order_no,
                    "error": snap.get("error", "order lookup failed")}
        symbol = symbol or snap.get("symbol")
        side = side or snap.get("side")
        price = price if price is not None else snap.get("price")
        balance = balance if balance is not None else snap.get("balance")
        account_no = account_no or snap.get("account_no")

    if not symbol or not side or price is None or balance is None:
        return {"success": False, "order_no": order_no, "symbol": symbol, "side": side,
                "price": price, "balance": balance,
                "error": "incomplete order snapshot (need symbol/side/price/balance)"}

    order = OrderSnapshot(order_no=order_no, symbol=str(symbol).strip().upper(),
                          side=str(side).strip(), price=float(price), balance=int(balance),
                          account_no=account_no, trade_date=trade_date)

    # 2. Live quote.
    q = await quicktrade_driver.get_quote(order.symbol, account_no=order.account_no)
    if not q.get("success"):
        return {"success": False, "order_no": order_no, "symbol": order.symbol,
                "error": q.get("error", "quote lookup failed")}

    quote = Quote(symbol=q.get("symbol") or order.symbol, best_bid=q.get("best_bid"),
                  best_offer=q.get("best_offer"), last=q.get("last"))
    decision = plan_negotiation(order, quote)

    result: Dict[str, Any] = {
        "success": decision.outcome in (NegotiationOutcome.OK, NegotiationOutcome.NO_CHANGE),
        "order_no": order_no,
        "symbol": order.symbol,
        "side": order.side,
        "outcome": decision.outcome.value,
        "current_price": decision.current_price,
        "target_price": decision.target_price,
        "volume": decision.volume,
        "reason": decision.reason,
        "quote": {"best_bid": quote.best_bid, "best_offer": quote.best_offer, "last": quote.last},
        "amendment": None,
        "submitted": None,
        "dry_run": None,
    }

    # 3. Amend in place (only on OK + execute).
    if decision.outcome is NegotiationOutcome.OK and execute:
        amendment = await quicktrade_driver.amend_price(
            order_no, decision.target_price, account_no=order.account_no or "",
            trade_date=trade_date, pin=pin, dry_run=dry_run)
        result["amendment"] = amendment
        result["success"] = bool(amendment.get("success"))
        # Anti-Mock: mirror the send state at the top level so a REST/remote consumer never has to
        # infer a live amendment from ``success`` alone (DRY-RUN ⇒ success True + submitted False).
        result["submitted"] = amendment.get("submitted")
        result["dry_run"] = amendment.get("dry_run")
        if not amendment.get("success"):
            result["error"] = amendment.get("error")
    elif decision.outcome is NegotiationOutcome.UPTICK_VIOLATION:
        result["error"] = decision.reason

    return result
