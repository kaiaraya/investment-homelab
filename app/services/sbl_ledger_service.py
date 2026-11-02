"""SBL lot reconciliation — the broker ledger is the source of truth.

Our ``sbl_borrow_lots`` table is a convenience cache: it carries the fee rate,
the return history and the tax metadata that MainSBL does not hand back. It is
*not* authoritative for "how much am I still short of", because a borrow can be
executed in the SBL window without our postback ever persisting a row (the DOM
submit succeeds and the response parse fails), and a returned lot quietly
disappears from the broker while our row stays ACTIVE forever.

So before every ``/sbl`` display — and before any ``all`` volume resolve — we
reconcile the table against ``active_borrow_transactions`` straight off the
MainSBL page:

* a ref_no the broker reports but we do not store  → insert it
* a ref_no we store but the broker no longer has   → close it (FULLY_RETURNED)
* a row we store with more shares than the broker  → clamp ``remaining_qty``

Destructive closes are refused when the scrape comes back empty or non-live, so
a broken DOM can never wipe the book.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.db.models import SBLBorrowLot

logger = logging.getLogger(__name__)

DEFAULT_FEE_RATE = 3.50
LIVE_SOURCES = {"sbl_read_cdp"}


def _parse_tran_date(raw: Any) -> Optional[date]:
    """MainSBL hands back ``DD/MM/YYYY``; be forgiving about anything else."""
    text = str(raw or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _as_int(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


async def reconcile_sbl_lots(db: Any, force_browser: bool = False) -> Dict[str, Any]:
    """Upsert ``sbl_borrow_lots`` from the live MainSBL borrow ledger.

    Returns a report dict; ``ok=False`` means nothing was written (fail-closed).
    """
    from app.brokers.krungsri.sbl_realtime_driver import krungsri_sbl_driver

    try:
        snap = await krungsri_sbl_driver.scrape_full_pool(force_browser=force_browser)
    except Exception as exc:  # noqa: BLE001 — never break a read command
        logger.warning("SBL reconcile: scrape failed: %s", exc)
        return {"ok": False, "code": "SBL_SCRAPE_FAILED", "reason": str(exc)}

    if not snap.get("success"):
        return {"ok": False, "code": "SBL_SCRAPE_FAILED",
                "reason": snap.get("message") or "scrape_full_pool returned success=false"}

    source = str(snap.get("source") or "")
    if source and source not in LIVE_SOURCES:
        return {"ok": False, "code": "SBL_NOT_LIVE",
                "reason": f"ledger source was {source!r}, not live CDP"}

    txs: List[Dict[str, Any]] = list(snap.get("active_borrow_transactions") or [])
    res = await db.execute(select(SBLBorrowLot))
    existing = list(res.scalars().all())
    by_tx = {str(lot.broker_tx_id): lot for lot in existing if lot.broker_tx_id}

    if not txs:
        if any(lot.status in ("ACTIVE", "PARTIAL_RETURNED") for lot in existing):
            # Broker says "nothing outstanding" while we hold live rows. Either
            # every position was returned or the table failed to render. We
            # cannot tell the two apart, so refuse to close the book.
            return {"ok": False, "code": "SBL_LEDGER_EMPTY",
                    "reason": "ledger returned 0 active borrows; refusing to close local lots"}
        return {"ok": True, "created": 0, "updated": 0, "closed": 0, "source": source}

    seen: set[str] = set()
    created = updated = 0

    for tx in txs:
        ref = str(tx.get("ref_no") or "").strip()
        symbol = str(tx.get("symbol") or "").strip().upper()
        qty = _as_int(tx.get("quantity"))
        if not ref or not symbol or qty <= 0:
            logger.warning("SBL reconcile: skipping malformed ledger row %s", tx)
            continue
        seen.add(ref)

        borrow_date = _parse_tran_date(tx.get("tran_date")) or date.today()
        price = _as_float(tx.get("borrow_price"))

        lot = by_tx.get(ref)
        if lot is None:
            db.add(SBLBorrowLot(
                lot_id=f"SBL-{symbol}-{ref}",
                broker_tx_id=ref,
                symbol=symbol,
                borrow_qty=qty,
                remaining_qty=qty,
                borrow_price=price,
                borrow_fee_rate=DEFAULT_FEE_RATE,
                borrow_date=borrow_date,
                status="ACTIVE",
            ))
            created += 1
            continue

        # Never let the cache claim more outstanding shares than the broker holds.
        if lot.remaining_qty != qty:
            lot.remaining_qty = qty
            updated += 1
        if lot.borrow_qty < qty:
            lot.borrow_qty = qty
            updated += 1
        if price and lot.borrow_price != price:
            lot.borrow_price = price
            updated += 1
        if lot.status not in ("ACTIVE", "PARTIAL_RETURNED"):
            lot.status = "PARTIAL_RETURNED" if lot.remaining_qty < lot.borrow_qty else "ACTIVE"
            updated += 1

    closed = 0
    for lot in existing:
        ref = str(lot.broker_tx_id or "").strip()
        if ref and ref in seen:
            continue
        if lot.status not in ("ACTIVE", "PARTIAL_RETURNED"):
            continue
        lot.status = "FULLY_RETURNED"
        lot.remaining_qty = 0
        lot.return_date = lot.return_date or date.today()
        closed += 1

    if created or updated or closed:
        await db.commit()

    logger.info("SBL reconcile: +%d created, %d updated, %d closed (source=%s)",
                created, updated, closed, source)
    return {"ok": True, "created": created, "updated": updated,
            "closed": closed, "source": source, "ledger_rows": len(txs)}
