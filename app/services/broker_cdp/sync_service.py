# -*- coding: utf-8 -*-
"""Portfolio auto-sync over the CDP gateway — scrape balance + holdings, UPSERT into DB.

``sync_portfolio_from_cdp(broker)`` is the *writer* for the multi-account tables
introduced in B.1 (``broker_accounts`` + ``positions``). It connects to the broker's
live Chrome tab through ``manager.get_tab``, scrapes the balance header and holdings
grid/table, and UPSERTs both tables keyed by ``account_no`` (and, for positions,
``(account_no, symbol)``).

Broker slugs: ``kss`` (Settrade Streaming via Krungsri SSO → ``KRUNGSRI``) and
``lib`` / ``liberator`` (Liberator WebTrade → ``LIBERATOR``).

Read-only and fail-closed (Anti-Mock):

* never clicks an order, never submits, never switches account;
* an unreadable cell is stored as ``None`` — never a fabricated ``0.00``;
* the account number is read off the screen (not assumed from config) so a value is
  never written under the wrong account header (money-movement safety, RCA-011).

Hooks: post-login (``scripts/broker_cdp/session_daemon.py``) and pre-trade (the
Phase-B order-draft handler) call this before relying on line-available / holdings.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import BrokerAccount, Order, Position
from app.db.session import AsyncSessionLocal
from app.services.broker_cdp.manager import get_tab

logger = logging.getLogger(__name__)

# broker slug (CLI) -> CDP slug / DB broker name / target tab
_BROKER_META: Dict[str, Dict[str, str]] = {
    "kss": {"cdp": "kss", "broker": "KRUNGSRI", "target": "streaming"},
    "lib": {"cdp": "liberator", "broker": "LIBERATOR", "target": "portfolio"},
    "liberator": {"cdp": "liberator", "broker": "LIBERATOR", "target": "portfolio"},
}

#: 7-digit account number, e.g. "3024952 (Equity)" -> "3024952".
_ACCOUNT_NO_RE = re.compile(r"\b(\d{7})\b")


# --------------------------------------------------------------------------- #
# Normalisation helpers (pure — unit-testable without a browser)
# --------------------------------------------------------------------------- #
def _to_float(value: Any) -> Optional[float]:
    """Best-effort float; ``None``/unparseable -> ``None`` (Anti-Mock)."""
    if value is None:
        return None
    try:
        v = float(str(value).replace(",", "").strip())
        return v
    except (TypeError, ValueError):
        return None


def map_kss_account_type(raw: Any) -> Optional[str]:
    """Map the KSS ``A/C Type :`` header text to a DB account_type code.

    ``"Credit Balance"`` -> ``CREDIT_BALANCE``, ``"Cash"`` -> ``CASH_BALANCE``;
    unreadable -> ``None`` (the caller keeps the previous value).
    """
    r = (str(raw or "")).strip().lower()
    if "credit" in r or "margin" in r:
        return "CREDIT_BALANCE"
    if "cash" in r:
        return "CASH_BALANCE"
    return None


def map_liberator_account_type(raw: Any) -> Optional[str]:
    r = (str(raw or "")).strip().upper()
    if "CREDIT" in r or "MARGIN" in r:
        return "CREDIT_BALANCE"
    if "CASH" in r:
        return "CASH_BALANCE"
    return None


def extract_account_no(text: Any) -> Optional[str]:
    """Pull the first 7-digit account number out of a header/selector string."""
    m = _ACCOUNT_NO_RE.search(str(text or ""))
    return m.group(1) if m else None


#: Trailing single-letter board/position marker in the KSS Streaming symbol cell,
#: e.g. ``"TISCO (S)"`` / ``"TU (B)"`` (CLI-RCA-002: the web cell carries the marker as text).
_KS_SYMBOL_SUFFIX_RE = re.compile(r"\s*\(([A-Za-z])\)\s*$")


def _clean_kss_symbol(raw: Any) -> tuple:
    """Split a KSS Streaming symbol cell into ``(symbol, marker)``.

    ``(S)`` = short-sell position, ``(B)`` = borrowed (SBL) lot, no suffix = ``None``
    (the caller keeps the JS-provided side, defaulting to LONG). ``marker`` ∈
    ``{None, 'S', 'B'}``.
    """
    s = str(raw or "").strip()
    m = _KS_SYMBOL_SUFFIX_RE.search(s)
    if not m:
        return s, None
    marker = m.group(1).upper()
    symbol = _KS_SYMBOL_SUFFIX_RE.sub("", s).strip()
    return symbol, marker if marker in ("S", "B") else None


# --------------------------------------------------------------------------- #
# DOM extraction (JS strings — run inside the live page)
# --------------------------------------------------------------------------- #
_KSS_SCRAPE_JS = """() => {
  const clean = s => (s == null ? '' : String(s).trim());
  const num = s => { if (s == null) return null; const v = parseFloat(String(s).replace(/,/g, '')); return isNaN(v) ? null : v; };

  // 1. active account no — the account-selector span shows e.g. "3024952 (Equity)".
  let accountNo = '';
  for (const s of document.querySelectorAll('span.outline-none')) {
    const m = clean(s.innerText).match(/\\b(\\d{7})\\b/);
    if (m) { accountNo = m[1]; break; }
  }

  // 2. balance header — label/value <p> pairs inside the centered header bar.
  const balances = { account_type: null, credit_limit: null, line_available: null,
                     cash_balance: null, excess_equity: null };
  const headers = document.querySelectorAll('div.display-flex.justify-content-center');
  for (const h of headers) {
    const ps = Array.from(h.querySelectorAll('p')).map(p => clean(p.innerText)).filter(Boolean);
    for (let i = 0; i + 1 < ps.length; i++) {
      const label = ps[i], val = ps[i + 1];
      if (label === 'A/C Type :') balances.account_type = val;
      else if (label === 'Credit Limit :') balances.credit_limit = num(val);
      else if (label === 'Line Available :') balances.line_available = num(val);
      else if (label === 'EE :') balances.excess_equity = num(val);
      else if (label === 'Cash Balance :') balances.cash_balance = num(val);
    }
  }

  // 3. holdings — the Portfolio ReactVirtualized grid (rows of <li> cells).
  const holdings = [];
  const container = document.querySelector('.ReactVirtualized__Grid__innerScrollContainer');
  if (container) {
    for (const ul of container.querySelectorAll('ul')) {
      const lis = Array.from(ul.querySelectorAll('li')).map(li => clean(li.innerText));
      if (lis.length >= 11) {
        const side = (lis[1] || '').toUpperCase();
        if (side === 'LONG' || side === 'SHORT') {
          holdings.push({ symbol: lis[0], position_type: side,
            volume: parseInt(lis[4].replace(/,/g, '')) || 0,
            available_volume: parseInt(lis[3].replace(/,/g, '')) || 0,
            avg_cost: parseFloat(lis[5].replace(/,/g, '')) || 0.0,
            current_price: parseFloat(lis[6].replace(/,/g, '')) || 0.0,
            market_value: parseFloat(lis[8].replace(/,/g, '')) || 0.0,
            unrealized_pnl: parseFloat(lis[10].replace(/,/g, '')) || 0.0 });
        } else if (!isNaN(parseInt(lis[1].replace(/,/g, '')))) {
          holdings.push({ symbol: lis[0], position_type: 'LONG',
            volume: parseInt(lis[3].replace(/,/g, '')) || 0,
            available_volume: parseInt(lis[2].replace(/,/g, '')) || 0,
            avg_cost: parseFloat(lis[4].replace(/,/g, '')) || 0.0,
            current_price: parseFloat(lis[5].replace(/,/g, '')) || 0.0,
            market_value: parseFloat(lis[7].replace(/,/g, '')) || 0.0,
            unrealized_pnl: parseFloat(lis[8].replace(/,/g, '')) || 0.0 });
        }
      }
    }
  }
  return { account_no: accountNo, balances, holdings };
}"""

_LIBERATOR_SCRAPE_JS = """() => {
  const clean = s => (s == null ? '' : String(s).trim());
  const num = s => { if (!s) return null; const v = parseFloat(String(s).replace(/,/g, '').replace(/–/g, '-').replace(/%/g, '').trim()); return isNaN(v) ? null : v; };

  let lineAvailable = null, cashBalance = null, creditLimit = null, accountType = '';
  const allTexts = Array.from(document.querySelectorAll('div, p, span, td'));
  for (const el of allTexts) {
    const t = el.innerText || '';
    let m;
    if (t.includes('Line Available:')) { m = t.match(/Line Available:\\s*([\\d,]+(?:\\.\\d+)?)/i); if (m) lineAvailable = num(m[1]); }
    if (t.includes('Cash Balance:')) { m = t.match(/Cash Balance:\\s*([\\d,]+(?:\\.\\d+)?)/i); if (m) cashBalance = num(m[1]); }
    if (t.includes('Credit Limit:')) { m = t.match(/Credit Limit:\\s*([\\d,]+(?:\\.\\d+)?)/i); if (m) creditLimit = num(m[1]); }
    if (t.includes('Account Type:')) { m = t.match(/Account Type:\\s*([A-Za-z ]+)/i); if (m) accountType = m[1].trim(); }
  }

  let holdingsTable = null;
  for (const t of document.querySelectorAll('table')) {
    const head = t.querySelector('thead');
    const headTxt = head ? head.innerText.toLowerCase() : '';
    if (headTxt.includes('symbol') && headTxt.includes('in port')) holdingsTable = t;
  }
  const holdings = [];
  if (holdingsTable) {
    for (const tr of holdingsTable.querySelectorAll('tbody tr')) {
      const parts = clean(tr.innerText).split(/\\s+/);
      if (parts.length >= 8 && /^[A-Z][A-Z0-9.\\-]{1,9}$/.test(parts[0]) && !/^\\d+$/.test(parts[0])) {
        holdings.push({
          symbol: parts[0],
          available_volume: Math.round(num(parts[1]) || 0),
          volume: Math.round(num(parts[2]) || 0),
          avg_cost: num(parts[3]),
          current_price: num(parts[4]),
          market_value: num(parts[6]),
          unrealized_pnl: num(parts[7]),
          unrealized_pnl_pct: parts.length > 8 ? num(parts[8]) : null,
        });
      }
    }
  }
  return { account_type: accountType, line_available: lineAvailable, cash_balance: cashBalance,
           credit_limit: creditLimit, holdings };
}"""


# --------------------------------------------------------------------------- #
# Scrape + normalise
# --------------------------------------------------------------------------- #
async def _ensure_kss_portfolio_tab(page: Any) -> None:
    """Switch the Streaming page to its Portfolio tab so the holdings grid renders.

    Best-effort: if the tab button isn't present the caller still returns balance with
    an empty holdings list (e.g. an empty Cash account renders no grid at all).
    """
    for sel in ["button:has-text('Portfolio')", "a:has-text('Portfolio')",
                "span:has-text('Portfolio')", "text=Portfolio"]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                await el.click()
                await page.wait_for_timeout(1200)
                return
        except Exception:
            continue


async def _scrape_kss(page: Any) -> Dict[str, Any]:
    raw = await page.evaluate(_KSS_SCRAPE_JS) or {}
    balances = raw.get("balances") or {}
    account_no = extract_account_no(raw.get("account_no"))
    if not account_no:
        # Anti-Mock (RCA-011): the balance header always carries an account selector; if it
        # can't be read we must not guess (a wrong guess would write Cash figures under the
        # margin account, or vice-versa). Fail-closed instead.
        raise RuntimeError("KSS Streaming: could not read active account_no from the header")
    account_type = map_kss_account_type(balances.get("account_type")) or "CASH_BALANCE"
    holdings = raw.get("holdings") or []
    clean_holdings = []
    for h in holdings:
        symbol, marker = _clean_kss_symbol(h.get("symbol"))
        if marker == "B":
            # A (B) row is an SBL borrow lot, not a position — SBLBorrowLot owns it.
            continue
        h["symbol"] = symbol
        h["position_type"] = "SHORT" if marker == "S" else (h.get("position_type") or "LONG")
        h.setdefault("volume", h.get("volume", 0))
        clean_holdings.append(h)
    return {
        "account_no": account_no,
        "account_type": account_type,
        "line_available": _to_float(balances.get("line_available")),
        "cash_balance": _to_float(balances.get("cash_balance")),
        "credit_limit": _to_float(balances.get("credit_limit")),
        "excess_equity": _to_float(balances.get("excess_equity")),
        "total_equity": None,  # KSS header exposes no total-equity cell
        "holdings": clean_holdings,
    }


async def _scrape_liberator(page: Any) -> Dict[str, Any]:
    raw = await page.evaluate(_LIBERATOR_SCRAPE_JS) or {}
    account_no = extract_account_no(getattr(settings, "LIBERATOR_ACCOUNT_NO", "")) or "7055938"
    account_type = map_liberator_account_type(raw.get("account_type")) or "CASH_BALANCE"
    cash_balance = _to_float(raw.get("cash_balance"))
    line_available = _to_float(raw.get("line_available"))
    total_equity: Optional[float] = None
    market_value_total = sum(_to_float(h.get("market_value")) or 0.0 for h in raw.get("holdings") or [])
    if cash_balance is not None:
        total_equity = cash_balance + market_value_total
    holdings = raw.get("holdings") or []
    for h in holdings:
        h.setdefault("position_type", "LONG")
        h["available_volume"] = h.get("available_volume") or h.get("volume", 0)
        if h.get("unrealized_pnl_pct") is None:
            h["unrealized_pnl_pct"] = None
    return {
        "account_no": account_no,
        "account_type": account_type,
        "line_available": line_available,
        "cash_balance": cash_balance,
        "credit_limit": _to_float(raw.get("credit_limit")),
        "excess_equity": None,  # Liberator WebTrade exposes no EE cell
        "total_equity": total_equity,
        "holdings": holdings,
    }


# --------------------------------------------------------------------------- #
# UPSERT
# --------------------------------------------------------------------------- #
def _account_upsert_stmt(**values: Any):
    ins = sqlite_insert(BrokerAccount).values(**values)
    return ins.on_conflict_do_update(
        index_elements=[BrokerAccount.account_no],
        set_={
            "broker": ins.excluded.broker,
            "account_type": ins.excluded.account_type,
            "line_available": ins.excluded.line_available,
            "cash_balance": ins.excluded.cash_balance,
            "credit_limit": ins.excluded.credit_limit,
            "total_equity": ins.excluded.total_equity,
            "excess_equity": ins.excluded.excess_equity,
            "purchasing_power": ins.excluded.purchasing_power,
        },
    )


def _position_upsert_stmt(**values: Any):
    ins = sqlite_insert(Position).values(**values)
    return ins.on_conflict_do_update(
        index_elements=["account_no", "symbol"],
        set_={
            "position_type": ins.excluded.position_type,
            "volume": ins.excluded.volume,
            "available_volume": ins.excluded.available_volume,
            "avg_cost": ins.excluded.avg_cost,
            "current_price": ins.excluded.current_price,
            "market_value": ins.excluded.market_value,
            "unrealized_pnl": ins.excluded.unrealized_pnl,
            "unrealized_pnl_pct": ins.excluded.unrealized_pnl_pct,
        },
    )


async def _upsert_account(db: AsyncSession, snap: Dict[str, Any]) -> None:
    await db.execute(_account_upsert_stmt(
        account_no=snap["account_no"],
        broker=snap["broker"],
        account_type=snap["account_type"],
        line_available=snap.get("line_available"),
        cash_balance=snap.get("cash_balance"),
        credit_limit=snap.get("credit_limit"),
        total_equity=snap.get("total_equity"),
        excess_equity=snap.get("excess_equity"),
        purchasing_power=snap.get("purchasing_power"),
    ))


async def _upsert_positions(db: AsyncSession, account_no: str, holdings: List[Dict[str, Any]]) -> int:
    scraped_symbols = set()
    for h in holdings:
        sym = str(h.get("symbol") or "").upper()
        if not sym:
            continue
        scraped_symbols.add(sym)
        await db.execute(_position_upsert_stmt(
            account_no=account_no,
            symbol=sym,
            position_type=str(h.get("position_type") or "LONG").upper(),
            volume=int(h.get("volume") or 0),
            available_volume=int(h.get("available_volume") or h.get("volume") or 0),
            avg_cost=float(h.get("avg_cost") or 0.0),
            current_price=_to_float(h.get("current_price")),
            market_value=_to_float(h.get("market_value")),
            unrealized_pnl=_to_float(h.get("unrealized_pnl")),
            unrealized_pnl_pct=_to_float(h.get("unrealized_pnl_pct")),
        ))

    # Positions closed externally (on the broker site/mobile) — zero them out so the
    # snapshot matches the frontend instead of lingering as stale holdings.
    stmt = select(Position).where(Position.account_no == account_no, Position.volume > 0)
    res = await db.execute(stmt)
    for pos in res.scalars().all():
        if pos.symbol.upper() not in scraped_symbols:
            if pos.position_type == "SHORT":
                pos.is_sbl_pending_return = True
            pos.volume = 0
    return len(scraped_symbols)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _resolve_broker_meta(broker: str) -> Dict[str, str]:
    slug = (broker or "").strip().lower()
    if slug not in _BROKER_META:
        raise ValueError(f"Unknown broker {broker!r} — expected kss, lib, or liberator")
    return _BROKER_META[slug]


async def scrape_portfolio_from_cdp(broker: str) -> Dict[str, Any]:
    """Connect to the broker's live CDP tab and scrape balance + holdings (read-only).

    Returns the normalised snapshot dict (``broker``, ``account_no``, ``account_type``,
    balance fields, ``holdings``) WITHOUT touching the database. This is the read-only
    half of the sync, exposed so a live probe can compare against the frontend without
    any DB write.
    """
    meta = _resolve_broker_meta(broker)
    cdp, target, db_broker = meta["cdp"], meta["target"], meta["broker"]

    async with get_tab(cdp, target) as page:
        if cdp == "kss":
            await _ensure_kss_portfolio_tab(page)
            snap = await _scrape_kss(page)
        else:
            snap = await _scrape_liberator(page)
    snap["broker"] = db_broker
    return snap


async def sync_portfolio_from_cdp(
    broker: str,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Scrape the broker's live tab over CDP and UPSERT ``broker_accounts`` + ``positions``.

    Returns a summary dict describing what was read and written. ``broker`` is the CLI
    slug (``kss`` / ``lib`` / ``liberator``). When ``db`` is omitted a fresh session from
    ``AsyncSessionLocal`` is used and committed; otherwise the caller owns the session
    (the webhook/draft handler passes its own so the write joins the same transaction).
    """
    snap = await scrape_portfolio_from_cdp(broker)

    owns_session = db is None
    if db is None:
        db = AsyncSessionLocal()

    try:
        await _upsert_account(db, snap)
        n_positions = await _upsert_positions(db, snap["account_no"], snap["holdings"])
        if owns_session:
            await db.commit()
    finally:
        if owns_session:
            await db.close()

    return {
        "broker": snap["broker"],
        "account_no": snap["account_no"],
        "account_type": snap["account_type"],
        "line_available": snap.get("line_available"),
        "cash_balance": snap.get("cash_balance"),
        "credit_limit": snap.get("credit_limit"),
        "excess_equity": snap.get("excess_equity"),
        "total_equity": snap.get("total_equity"),
        "positions": n_positions,
    }


# --------------------------------------------------------------------------- #
# Order ledger sync (B.7 — human co-existence)
# --------------------------------------------------------------------------- #
#: Side text -> canonical OrderSide. Unknown (unreadable) -> None so the caller
#: *skips* the row rather than fabricating a BUY (Anti-Mock).
_SIDE_ALIASES = {
    "B": "BUY", "BUY": "BUY",
    "S": "SELL", "SELL": "SELL",
    "H": "SHORT", "SHORT": "SHORT", "SS": "SHORT", "SHORTSELL": "SHORT",
    "C": "COVER", "COVER": "COVER",
    "LONG": "LONG",
}


def map_ledger_side(raw: Any) -> Optional[str]:
    """Map a broker order-ledger side cell to a canonical ``OrderSide`` value.

    Handles the Streaming full words (``Buy``/``Sell``/``Short``/``Cover``), the
    radio letters (``B``/``S``/``H``/``C``), and any parenthetical match marker
    (``Cover(M)``). Returns ``None`` when the side can't be read — never a guess.
    """
    s = re.sub(r"\s*\([^)]*\)\s*$", "", str(raw or "")).strip()
    s = re.sub(r"[^A-Za-z]", "", s).upper()
    return _SIDE_ALIASES.get(s)


def map_ledger_status(raw: Any) -> str:
    """Map a broker order-ledger status cell to a valid ``OrderStatus`` value.

    Terminal states (matched/filled/cancelled/rejected/expired) map to their
    canonical counterparts; a partial fill maps to ``OPEN``; anything else (a
    live row we saw in the ledger but couldn't classify) is ``QUEUED`` — the
    honest "live, not yet matched" state, never a fabricated terminal one.
    """
    s = str(raw or "").strip().lower()
    if "match" in s or "fill" in s:
        return "FILLED"
    if "cancel" in s or "void" in s:
        return "CANCELLED"
    if "reject" in s:
        return "REJECTED"
    if "expire" in s:
        return "EXPIRED_EOD"
    if "partial" in s:
        return "OPEN"
    return "QUEUED"


#: Streaming order-ledger grid row: [order_no, date, time, symbol, side, price,
#: volume, matched, balance, cancelled, status, (detail)] — 12 cells. The row is
#: identified by a 5+ digit numeric order_no in cell 0 (a portfolio row starts
#: with a symbol like "TISCO (S)", so the numeric check cleanly separates the two).
_KSS_ORDER_LEDGER_JS = """() => {
  const clean = s => (s == null ? '' : String(s).trim());
  let accountNo = '';
  for (const s of document.querySelectorAll('span.outline-none')) {
    const m = clean(s.innerText).match(/\\b(\\d{7})\\b/);
    if (m) { accountNo = m[1]; break; }
  }
  const rows = [];
  for (const grid of document.querySelectorAll('div[aria-label="grid"]')) {
    const container = grid.querySelector('.ReactVirtualized__Grid__innerScrollContainer');
    if (!container) continue;
    for (const ul of container.querySelectorAll('ul')) {
      let cells = Array.from(ul.querySelectorAll('li')).map(li => clean(li.innerText));
      // Order rows carry a leading checkbox cell (empty text) plus 3 trailing action cells
      // ("Change"/"Detail"/"Cancel"). Strip both so the cell contract stays
      // [order_no, date, time, symbol, side, price, volume, ...]. Live-verified 2026-10-21:
      // without this, a real bot-placed order was invisible to the scraper (0 rows read).
      while (cells.length && cells[0] === '') cells.shift();
      while (cells.length && /^(change|detail|cancel)$/i.test(cells[cells.length - 1])) cells.pop();
      if (cells.length >= 11 && /^\\d{5,}$/.test(cells[0])) rows.push(cells);
    }
  }
  return { account_no: accountNo, rows };
}"""


def _normalise_kss_order_cells(cells: List[Any]) -> List[str]:
    """Strip the order grid's leading checkbox cell and trailing action cells.

    A live Streaming order row reads as ``["", "11010191", "21/10", "10:18:36", "TU", "Cover",
    "12.60", "3,100", "0", "3,100", "0", "Queuing(O)", "Change", "Detail", "Cancel"]`` — the
    first cell is the row checkbox. Without this the cell contract shifts by one and real
    bot-placed orders are dropped (found live 2026-10-21 on order 11010191).
    """
    out = [("" if c is None else str(c).strip()) for c in (cells or [])]
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1].lower() in ("change", "detail", "cancel"):
        out.pop()
    return out


def _parse_kss_order_rows(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Normalise raw Streaming order-grid cell arrays into ledger dicts."""
    orders: List[Dict[str, Any]] = []
    for cells in rows:
        cells = _normalise_kss_order_cells(cells)
        if len(cells) < 11:                     # fail closed — never invent a partial order
            logger.warning("KSS order row skipped (only %s cells): %r", len(cells), cells)
            continue
        orders.append({
            "broker_order_no": str(cells[0]).strip(),
            "time": f"{cells[1]} {cells[2]}".strip(),
            "symbol": str(cells[3] or "").strip().upper(),
            "side": cells[4],
            "price": _to_float(cells[5]),
            "volume": int(_to_float(cells[6]) or 0),
            "matched_volume": int(_to_float(cells[7]) or 0),
            "balance": int(_to_float(cells[8]) or 0),
            "cancelled_volume": int(_to_float(cells[9]) or 0),
            "status": str(cells[10] or "").strip(),
        })
    return orders


_LIBERATOR_ORDER_LEDGER_JS = """() => {
  const clean = s => (s == null ? '' : String(s).trim());
  let ordersTable = null;
  for (const t of document.querySelectorAll('table')) {
    const head = t.querySelector('thead');
    const ht = head ? head.innerText.toLowerCase() : '';
    if (ht.includes('order') && ht.includes('side')) ordersTable = t;
  }
  const rows = [];
  if (ordersTable) {
    for (const tr of ordersTable.querySelectorAll('tbody tr')) {
      let cells = Array.from(tr.querySelectorAll('td')).map(td => clean(td.innerText));
      if (cells.length < 8) {
        cells = clean(tr.innerText).split(/[\\s\\t|]+/).filter(Boolean);
      }
      if (cells.length >= 8) rows.push(cells);
    }
  }
  return { rows };
}"""


def _parse_liberator_order_rows(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """Normalise raw WebTrade order-table cell arrays into ledger dicts.

    Column order (WebTrade Portfolio "Order #" table):
    order_no | time | symbol | side | price | volume | matched | balance | cancelled | status
    """
    orders: List[Dict[str, Any]] = []
    for cells in rows:
        orders.append({
            "broker_order_no": str(cells[0] or "").strip(),
            "time": str(cells[1] or "").strip(),
            "symbol": str(cells[2] or "").strip().upper(),
            "side": cells[3],
            "price": _to_float(cells[4]),
            "volume": int(_to_float(cells[5]) or 0),
            "matched_volume": int(_to_float(cells[6]) or 0),
            "balance": int(_to_float(cells[7]) or 0),
            "cancelled_volume": int(_to_float(cells[8]) or 0) if len(cells) > 8 else 0,
            "status": str(cells[9] or "").strip() if len(cells) > 9 else "",
        })
    return orders


async def scrape_orders_from_cdp(broker: str) -> Dict[str, Any]:
    """Connect to the broker's live CDP tab and scrape the order ledger (read-only).

    Returns ``{broker, account_no, orders: [...]}`` WITHOUT touching the database.
    This is the read-only half of the manual-order sync — a live probe can diff the
    ledger against the frontend with no DB write. It never clicks, submits, or
    switches account (the order panel is already rendered on the Streaming/Portfolio
    page).
    """
    meta = _resolve_broker_meta(broker)
    cdp, target, db_broker = meta["cdp"], meta["target"], meta["broker"]

    async with get_tab(cdp, target) as page:
        if cdp == "kss":
            raw = await page.evaluate(_KSS_ORDER_LEDGER_JS) or {}
            account_no = extract_account_no(raw.get("account_no"))
            orders = _parse_kss_order_rows(raw.get("rows") or [])
        else:
            raw = await page.evaluate(_LIBERATOR_ORDER_LEDGER_JS) or {}
            account_no = extract_account_no(getattr(settings, "LIBERATOR_ACCOUNT_NO", "")) or "7055938"
            orders = _parse_liberator_order_rows(raw.get("rows") or [])

    return {"broker": db_broker, "account_no": account_no, "orders": orders}


async def _existing_broker_order_nos(db: AsyncSession) -> set:
    """All non-null ``broker_order_no`` values already in ``orders`` (the diff set)."""
    res = await db.execute(select(Order.broker_order_no).where(Order.broker_order_no.isnot(None)))
    return {row[0] for row in res.all()}


async def sync_orders_from_cdp(
    broker: str,
    db: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Diff the broker's live order ledger against ``orders`` and record manual orders.

    Any ledger row whose ``broker_order_no`` is NOT already in ``orders`` is a trade the
    human placed directly on the frontend — it is inserted with ``source='manual_sync'``
    (fail-closed: rows with an unreadable side / symbol / price are skipped, never
    fabricated). Rows already in ``orders`` are left untouched (the bot's own execution
    path owns those lifecycle updates).

    Returns a summary dict. When ``db`` is omitted a fresh session is opened and committed.
    """
    snap = await scrape_orders_from_cdp(broker)

    owns_session = db is None
    session: AsyncSession = db if db is not None else AsyncSessionLocal()

    new_manual: List[str] = []
    skipped = 0
    try:
        existing = await _existing_broker_order_nos(session)
        for o in snap["orders"]:
            bno = str(o.get("broker_order_no") or "").strip()
            side = map_ledger_side(o.get("side"))
            sym = str(o.get("symbol") or "").strip()
            price = o.get("price")
            volume = int(o.get("volume") or 0)
            if not bno or bno in existing:
                continue
            if side is None or not sym or price is None or volume <= 0:
                skipped += 1
                continue
            session.add(Order(
                order_id=f"MAN-{snap['broker']}-{snap.get('account_no') or 'X'}-{bno}",
                broker_order_no=bno,
                symbol=sym,
                side=side,
                volume=volume,
                price=float(price),
                status=map_ledger_status(o.get("status")),
                source="manual_sync",
                account_no=snap.get("account_no"),
                broker=snap["broker"],
                matched_volume=int(o.get("matched_volume") or 0),
                cancel_volume=int(o.get("cancelled_volume") or 0),
            ))
            new_manual.append(bno)
        if owns_session:
            await session.commit()
    finally:
        if owns_session:
            await session.close()

    return {
        "broker": snap["broker"],
        "account_no": snap.get("account_no"),
        "scraped": len(snap["orders"]),
        "new_manual_count": len(new_manual),
        "new_manual_orders": new_manual,
        "skipped": skipped,
    }


__all__ = [
    "sync_portfolio_from_cdp",
    "scrape_portfolio_from_cdp",
    "sync_orders_from_cdp",
    "scrape_orders_from_cdp",
    "map_kss_account_type",
    "map_liberator_account_type",
    "map_ledger_side",
    "map_ledger_status",
    "extract_account_no",
]
