"""Pure price planner for the nego menu (ต่อราคา) — one source of truth for
computing a target price from the live board, used by the N3 postback flow.

The two modes, per the user's decision (2026-10-26):

- ``match``  — cross the spread to fill immediately (aggressive).
- ``lure``   — join the queue at my own side's best price, never crossing
               ("ต่อท้ายคิวที่ราคา bid/offer เดิม" — the one that does NOT match).

SHORT/COVER/SHORT-sell are bound by the SET uptick rule, which is enforced by
``app.services.validator.validator.validate_short_uptick`` — the SSOT. Never
re-derive the rule here.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.services.validator import validator


def _f(v: Optional[float]) -> Optional[float]:
    """Coerce a board cell to float, or None when it is unreadable."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def plan_price(
    side: str,
    mode: str,
    bid: Optional[float],
    offer: Optional[float],
    last: Optional[float],
    old_price: Optional[float],
) -> Dict:
    """Compute the target price for one order.

    Returns ``{"ok": True, "price": float}`` or ``{"ok": False, "reason": str}``.
    ``mode`` is ``"match"`` or ``"lure"``; ``side`` is BUY/SELL/SHORT/COVER.
    """
    s = (side or "").strip().upper()
    m = (mode or "").strip().lower()
    if m == "passive":
        m = "lure"
    bid = _f(bid)
    offer = _f(offer)
    last = _f(last)

    if m not in ("match", "lure"):
        return {"ok": False, "reason": f"unknown mode {mode!r}"}
    if s not in ("BUY", "SELL", "SHORT", "COVER"):
        return {"ok": False, "reason": f"unknown side {side!r}"}

    is_buy = s in ("BUY", "COVER")

    # Which board leg does this mode need? A missing leg is fail-closed.
    if m == "match":
        # Aggressive: hit the far side (buy -> offer, sell -> bid).
        leg = offer if is_buy else bid
        leg_name = "offer" if is_buy else "bid"
    else:
        # Passive: join my own side's queue (buy -> bid, sell -> offer).
        leg = bid if is_buy else offer
        leg_name = "bid" if is_buy else "offer"

    if leg is None:
        return {"ok": False, "reason": f"อ่าน {leg_name} ไม่ได้ (board ว่าง)"}

    price = leg

    # SHORT is a sell side bound by the strict uptick rule: price must be strictly
    # above the last traded price. "match" at the bid is legal only when bid > last.
    if s == "SHORT":
        if last is None:
            return {"ok": False, "reason": "อ่านราคาล่าสุด (last) ไม่ได้ — ไม่ส่ง SHORT (uptick)"}
        ok, err = validator.validate_short_uptick(price, last)
        if not ok:
            if m == "match":
                # A short cannot legally match at the bid under uptick — offer lure instead.
                return {"ok": False, "reason": f"Match ไม่ได้ตามกฎ uptick — {err}"}
            # Lure at the offer is usually > last; if not, step one tick above last.
            price = validator.get_next_tick(last, steps=1)
            if price <= last:
                return {"ok": False, "reason": f"ไม่สามารถตั้งราคาเหนือ last ตามกฎ uptick — {err}"}

    # A target equal to the current price is a no-op amend — skip, never submit.
    if old_price is not None and abs(price - float(old_price)) < 1e-9:
        return {"ok": False, "reason": "NO_CHANGE"}

    return {"ok": True, "price": round(price, 2)}


__all__ = ["plan_price"]
