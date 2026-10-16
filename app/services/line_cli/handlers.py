"""
LINE slash-command handlers (Pillar 1–3, KSS + LIB).

Thin adapters over the *existing* Pillar 1/2/6 services and broker drivers — see
``docs/handoff/TASK-line-cli.md``. Broker isolation is enforced by routing every
call through a per-broker context (never mixing KSS and LIB behaviour).

Long operations (login / ``sync`` / nego) acknowledge immediately with a reply
and push the result to the originating chat (groupId else userId). A
per-``(command, broker)`` lock turns duplicate submissions into ``E_BUSY``.

The service instance is injected by ``line_service`` (avoids a circular import).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.services.line_cli import cards
from app.services.line_cli.parser import CliCommand, CliError

logger = logging.getLogger(__name__)

#: per-``(command, broker)`` in-flight lock (design §1)
_LOCKS: Dict[Tuple[str, str], asyncio.Lock] = {}
#: human-readable start time of the in-flight op, for the E_BUSY message
_STARTED: Dict[Tuple[str, str], str] = {}

BROKER_LABEL = {"kss": "KSS", "lib": "LIB"}

#: display symbols for /status
_STATE_EMOJI = {"alive": "🟢", "pending": "🟡", "down": "🔴", "never": "⚪"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _text(text: str, quick: Optional[List[str]] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"type": "text", "text": text}
    if quick:
        msg["quickReply"] = cards.quick_reply(quick)
    return msg


def _lock_for(cmd: str, broker: str) -> asyncio.Lock:
    key = (cmd, broker or "-")
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def _now_bkk() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _in_nego_window(now: Optional[datetime] = None) -> bool:
    """G2 — is ``now`` (Bangkok) inside one of the configured windows?"""
    now = now or _now_bkk()
    raw = getattr(settings, "LINE_NEGO_WINDOWS", "") or ""
    for part in raw.split(","):
        part = part.strip()
        if "-" not in part:
            continue
        a, _, b = part.partition("-")
        try:
            start = datetime.strptime(a.strip(), "%H:%M").time()
            end = datetime.strptime(b.strip(), "%H:%M").time()
        except ValueError:
            continue
        if start <= now.time() <= end:
            return True
    return False


def _fmt_hhmm(iso: Optional[str]) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")
    except (ValueError, TypeError):
        return str(iso)[:5]


def _source_of(raw_event: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Returns ``(user_id, group_id, source_type, push_target)``."""
    src = (raw_event or {}).get("source") or {}
    user_id = src.get("userId")
    group_id = src.get("groupId")
    return user_id, group_id, src.get("type"), (group_id or user_id)


# --------------------------------------------------------------------------- #
# Broker contexts (Broker Isolation)
# --------------------------------------------------------------------------- #
def _broker_platform(broker: str) -> str:
    return "TRADEMAN" if broker == "kss" else "LIBERATOR"


async def _broker_session_alive(broker: str) -> bool:
    """Is there a live, already-authenticated session? (never auto-logins)"""
    if broker == "kss":
        from app.browser.auth_driver import auth_driver
        return bool(auth_driver.is_authenticated)
    from app.brokers import liberator_plugin
    health = await liberator_plugin.get_health()
    return bool(health.get("is_authenticated"))


async def _broker_health(broker: str) -> Dict[str, Any]:
    """Normalised health for /status — reads only, never logs in."""
    if broker == "kss":
        from app.browser.auth_driver import auth_driver
        return {
            "authenticated": bool(auth_driver.is_authenticated),
            "heartbeat": _fmt_hhmm(auth_driver.last_heartbeat.isoformat() if auth_driver.last_heartbeat else None),
            "account": "MARGIN",
        }
    from app.brokers import liberator_plugin
    h = await liberator_plugin.get_health()
    return {
        "authenticated": bool(h.get("is_authenticated")),
        "heartbeat": _fmt_hhmm(h.get("last_heartbeat")),
        "account": "CASH",
    }


async def _broker_quote(broker: str, symbol: str) -> Dict[str, Any]:
    """Live Bid1/Offer1/last for ``symbol`` from *this* broker only."""
    if broker == "kss":
        from app.browser.trademan_driver import trademan_driver
        return await trademan_driver.get_market_bid_offer(symbol)
    from app.brokers import liberator_plugin
    return await liberator_plugin.get_market_bid_offer(symbol)


async def _broker_open_orders(broker: str) -> List[Dict[str, Any]]:
    """Unmatched/open orders for ``broker`` only.

    ``kss`` reads the Settrade Quick Trade ledger (``#orderBodyEq``): ``/nego kss``
    amends in place on that platform, so both the order numbers and the remaining
    volumes must come from there (D1/D4 - TASK-loop1-2). Anti-Mock: a failed ledger
    read raises, so the command reports an error instead of "no pending orders".
    """
    if broker == "kss":
        from app.brokers.krungsri.quicktrade_driver import quicktrade_driver
        res = await quicktrade_driver.list_open_orders()
        if not res.get("success"):
            raise RuntimeError(str(res.get("error") or "อ่านตารางออเดอร์ QuickTrade ไม่ได้"))
        orders = list(res.get("orders") or [])
    else:
        from app.brokers import liberator_plugin
        orders = await liberator_plugin.get_open_orders()
    out = []
    for o in orders or []:
        balance = int(o.get("balance", 0) or 0)
        status = str(o.get("status", "")).upper()
        if balance > 0 and "CANCEL" not in status and "MATCH" not in status.split():
            out.append(o)
    return out


async def _broker_modify(broker: str, *, order_no: str, new_price: float, symbol: str, side: str, volume: int) -> Dict[str, Any]:
    """
    Amend an order in place, routed per broker (Broker Isolation).

    TEST -> shared virtual simulator (through the dispatcher); LIVE -> the broker's own
    driver. ``kss`` LIVE goes through the Quick Trade passive policy
    (``negotiate_order_price``): Settrade's *Change Price& Volume* keeps the order
    number and the volume, so no cancel+replace is reachable from ``/nego`` any more
    (D1 - TASK-loop1-2). ``lib`` LIVE keeps the native WebTrade ``Change``
    (LIB-RCA-016/017). The dispatcher's LIVE route is bound to ``TRADING_PLATFORM`` and
    cannot address both brokers in one loop, so LIVE goes straight to the owning driver.
    LIB also re-checks the board quote here (Loop 1 D3): the reading taken during planning may
    have died, and the price basis must still be provable — an unreadable / wrong-symbol /
    empty-side reading aborts the amend with ``QUOTE_UNAVAILABLE`` before the driver is called.
    """
    from app.services.trade_dispatcher import trade_dispatcher
    if not trade_dispatcher.is_live:
        return await trade_dispatcher.dispatch_price_modification(
            broker_order_no=order_no, new_price=new_price, symbol=symbol, side=side, volume=volume
        )
    if broker == "kss":
        from app.services.quicktrade_negotiation_service import negotiate_order_price
        # ``new_price`` is deliberately ignored: the service re-reads the live quote,
        # applies G4/G5/G6 itself and amends on the SAME order_no.
        res = await negotiate_order_price(
            order_no, symbol=symbol, side=side, balance=int(volume) or None)
        res["path"] = "QUICKTRADE_INPLACE"
        return res
    # ── LIB (LIVE) ───────────────────────────────────────────────────────────────
    # Fail-closed second gate (Loop 1 D3): the quote may have died between planning and the
    # amend, and the price basis must still be provable. If the board cannot be read, or the
    # reading is not for this symbol, or the side we need is empty → ABORT with
    # ``QUOTE_UNAVAILABLE`` and press nothing (the caller shows the honest "อ่านไม่ได้" card).
    from app.brokers import liberator_plugin
    quote = await _broker_quote(broker, symbol)
    if quote.get("success") is False or quote.get("source") == "unavailable":
        return {
            "success": False, "status": "QUOTE_UNAVAILABLE", "unavailable": True,
            "error": str(quote.get("error") or f"อ่านราคา {symbol} จาก {BROKER_LABEL[broker]} ไม่ได้"),
        }
    if str(quote.get("symbol") or "").upper() != str(symbol or "").upper():
        return {
            "success": False, "status": "QUOTE_UNAVAILABLE", "unavailable": True,
            "error": (f"ราคาที่อ่านได้เป็น {quote.get('symbol') or '-'} ไม่ใช่ {symbol}"
                      " — ไม่แก้ราคา (fail-closed)"),
        }
    needed = "bid_1" if str(side or "").upper() in ("BUY", "COVER") else "offer_1"
    if quote.get(needed) is None:
        return {
            "success": False, "status": "QUOTE_UNAVAILABLE", "unavailable": True,
            "error": f"อ่าน {needed} ของ {symbol} ไม่ได้ — ไม่แก้ราคา (fail-closed)",
        }
    # The driver re-reads the live order row and refuses when its symbol is not ``symbol``
    # (status SYMBOL_MISMATCH) — nothing is pressed in that case either.
    return await liberator_plugin.change_order(
        order_no=order_no, new_price=new_price, symbol=symbol)


# --------------------------------------------------------------------------- #
# /help
# --------------------------------------------------------------------------- #
_HELP_TEXT = (
    "📖 คำสั่ง Homelab (KSS / LIB)\n"
    "Pillar 1 · Session\n"
    "  /status [kss|lib]        สถานะระบบ\n"
    "  /login kss|lib|all [force]\n"
    "  /logout kss|lib|all\n"
    "Pillar 2 · Portfolio\n"
    "  /port [kss|lib] [sync]   หุ้นที่ถือ + P/L\n"
    "  /cash [kss|lib] [sync]   เงินสด / กำลังซื้อ\n"
    "  /orders [kss|lib] [sync] ออเดอร์วันนี้\n"
    "Pillar 3 · Trade\n"
    "  /nego kss|lib [SYM|เลขออเดอร์]  ต่อราคาไป Bid1/Offer1\n"
    "  /negotiate <order_no>    ต่อราคา Quick Trade แก้ในที่ (ไม่ยกเลิก)\n"
    "ฉุกเฉิน: PANIC · RESET · MODE\n"
    "พิมพ์ /help nego เพื่อดูรายละเอียด"
)

_HELP_NEGO = (
    "⚡ /nego — ต่อราคาออเดอร์ค้าง (ทำทันที ไม่ต้องอนุมัติ)\n"
    "รูปแบบ: /nego kss|lib [SYMBOL|order_no]\n"
    "• ไม่ระบุเป้าหมาย = ทุกออเดอร์ค้างของโบรกเกอร์นั้น\n"
    "• kss = แก้ราคาในที่บนออเดอร์เดิม (QuickTrade Change Price& Volume) ไม่ยกเลิก\n"
    "• ราคาเป้าหมาย: BUY/COVER→Bid1 · SELL→Offer1 · SHORT→Offer1 (สูงกว่าราคาล่าสุด)\n"
    "Guardrails (ต่อออเดอร์):\n"
    "  G1 kill-switch ไม่ active\n"
    "  G2 ในเวลาที่อนุญาต (LINE_NEGO_WINDOWS)\n"
    "  G3 session alive (ไม่ login เอง)\n"
    "  G4 ผ่าน SET tick-size\n"
    "  G5 |ราคาใหม่−เดิม| ≤ LINE_NEGO_MAX_TICKS tick\n"
    "  G6 SHORT ต้องผ่านกฎ uptick"
)

_HELP_NEGOTIATE = (
    "⚡ /negotiate — ต่อราคาออเดอร์ Quick Trade แบบแก้ในที่ (Settrade FastOrder)\n"
    "รูปแบบ: /negotiate <order_no>   เช่น /negotiate 11008198\n"
    "• ไม่ยกเลิก/สร้างออเดอร์ใหม่ — แก้ราคาที่ออเดอร์เดิม (จำนวนเดิมเสมอ)\n"
    "• BUY→Bid1 · SELL→Offer1 · SHORT→Offer1 (ต้องสูงกว่าราคาล่าสุด)\n"
    "• SHORT ที่ Offer1 ≤ LastPrice = ⛔ ผิดกฎ uptick → ไม่ส่ง (fail-closed)\n"
    "• ใช้ session เดิมเท่านั้น (Zero-OTP) · ไม่ login เอง\n"
    "Guardrails: G1 kill-switch · G2 LINE_NEGO_WINDOWS · G4 tick-size · G5 ≤ 3 tick · กันกดซ้ำต่อออเดอร์"
)


async def _handle_help(parsed: CliCommand, service: Any, reply_token: Optional[str]) -> Dict[str, Any]:
    if parsed.target == "nego":
        await service._send_reply(reply_token, _text(_HELP_NEGO))
    elif parsed.target == "negotiate":
        await service._send_reply(reply_token, _text(_HELP_NEGOTIATE))
    else:
        await service._send_reply(reply_token, _text(_HELP_TEXT, quick=["/status", "/port", "/orders"]))
    return {"status": "CLI_HELP"}


# --------------------------------------------------------------------------- #
# /status
# --------------------------------------------------------------------------- #
async def _handle_status(service: Any, reply_token: Optional[str]) -> Dict[str, Any]:
    from app.services.kill_switch_service import kill_switch_service
    from app.services.otp_relay_readiness import otp_relay_readiness
    from app.services.trade_dispatcher import trade_dispatcher

    kill_active = kill_switch_service.is_active()
    relay = await otp_relay_readiness.check()
    mode_badge = trade_dispatcher.get_mode_badge()

    brokers: List[Dict[str, str]] = []
    for key in ("kss", "lib"):
        h = await _broker_health(key)
        emoji = "🟢" if h["authenticated"] else "🔴"
        brokers.append({
            "key": key, "name": BROKER_LABEL[key], "emoji": emoji,
            "line1": f"heartbeat {h['heartbeat']}" if h["authenticated"] else "ไม่ได้เข้าระบบ",
            "line2": f"บัญชี {h['account']}",
        })

    if relay.ready:
        relay_label = "พร้อม" + (f" ({relay.channel})" if relay.channel else "")
    else:
        relay_label = (relay.reason or "ไม่พร้อม")[:40]

    card = cards.status_card(
        brokers=brokers, relay_ready=relay.ready, relay_label=relay_label,
        mode_badge=mode_badge, kill_active=kill_active,
        updated=_now_bkk().strftime("%H:%M:%S"),
    )
    await service._send_reply(reply_token, card)
    return {"status": "CLI_STATUS", "kill_active": kill_active, "relay_ready": relay.ready,
            "kss_alive": brokers[0]["emoji"] == "🟢", "lib_alive": brokers[1]["emoji"] == "🟢"}


# --------------------------------------------------------------------------- #
# /login
# --------------------------------------------------------------------------- #
async def _handle_login(
    parsed: CliCommand, service: Any, reply_token: Optional[str], push_target: Optional[str]
) -> Dict[str, Any]:
    from app.services.kill_switch_service import kill_switch_service
    from app.services.otp_relay_readiness import otp_relay_readiness
    from app.mcp.pillars.pillar1_session import session_login_broker

    if kill_switch_service.is_active():
        await service._send_reply(reply_token, _text("⛔ KILL-SWITCH ACTIVE — คำสั่งถูกระงับ · พิมพ์ RESET เพื่อปลด"))
        return {"status": "CLI_KILL_SWITCH"}

    brokers = ["kss", "lib"] if parsed.broker == "all" else [parsed.broker]
    force = parsed.has("force")

    # Invariant 9 — never fire SMS unless the relay gate is live.
    relay = await otp_relay_readiness.check()
    if not relay.ready:
        await service._send_reply(reply_token, _text(f"🚫 OTP relay ยังไม่พร้อม: {relay.reason} — ยังไม่ส่ง SMS"))
        return {"status": "CLI_RELAY_NOT_READY", "ready": False}

    key = ("login", parsed.broker or "-")
    lock = _lock_for(*key)
    if lock.locked():
        await service._send_reply(reply_token, _text(
            f"⏳ /login {parsed.broker} กำลังทำงานอยู่ (เริ่ม {_STARTED.get(key, '-')}) — รอผลสักครู่"))
        return {"status": "CLI_BUSY"}

    async with lock:
        _STARTED[key] = _now_bkk().strftime("%H:%M:%S")
        order_txt = " → ".join(BROKER_LABEL[b] for b in brokers)
        await service._send_reply(reply_token, _text(
            f"🔐 กำลังเข้าระบบ {order_txt}… เมื่อได้ SMS ให้พิมพ์ OTP 6 หลักในกลุ่มนี้ (หมดเวลาใน 3 นาที)"))
        results: List[Dict[str, Any]] = []
        try:
            for b in brokers:
                if await _broker_session_alive(b) and not force:
                    await service.push_message(
                        _text(f"🟢 {BROKER_LABEL[b]} เชื่อมต่ออยู่แล้ว — ใช้ /login {b} force เพื่อเข้าใหม่"),
                        to_user_id=push_target)
                    results.append({"broker": b, "status": "already_alive"})
                    continue
                res = await session_login_broker(platform=_broker_platform(b), force_fresh=force)
                if res.get("success"):
                    await service.push_message(
                        _text(f"✅ {BROKER_LABEL[b]} เข้าระบบสำเร็จ · {_now_bkk().strftime('%H:%M:%S')}",
                              quick=[f"/port {b}", f"/orders {b}"]),
                        to_user_id=push_target)
                    results.append({"broker": b, "status": "ok"})
                else:
                    err = res.get("message") or res.get("error") or "ไม่ทราบสาเหตุ"
                    await service.push_message(
                        _text(f"❌ {BROKER_LABEL[b]} เข้าระบบไม่สำเร็จ: {err}"), to_user_id=push_target)
                    results.append({"broker": b, "status": "failed", "detail": err})
        except Exception as e:
            logger.exception(f"LINE CLI /login {order_txt} failed")
            await service.push_message(
                _text(f"❌ {order_txt} เข้าระบบไม่สำเร็จ: {type(e).__name__}: {str(e)[:120]}"),
                to_user_id=push_target)
            results.append({"broker": parsed.broker, "status": "failed",
                            "detail": f"{type(e).__name__}: {str(e)[:120]}"})
        finally:
            _STARTED.pop(key, None)
    return {"status": "CLI_LOGIN", "results": results}


# --------------------------------------------------------------------------- #
# /logout
# --------------------------------------------------------------------------- #
async def _handle_logout(parsed: CliCommand, service: Any, reply_token: Optional[str]) -> Dict[str, Any]:
    brokers = ["kss", "lib"] if parsed.broker == "all" else [parsed.broker]
    lines: List[str] = []
    for b in brokers:
        if not await _broker_session_alive(b):
            lines.append(f"⚪ {BROKER_LABEL[b]} ไม่ได้เข้าระบบอยู่แล้ว")
            continue
        if b == "kss":
            from app.browser.auth_driver import auth_driver
            await auth_driver.close()
        else:
            from app.brokers import liberator_plugin
            await liberator_plugin.close()
        lines.append(f"👋 ออกจากระบบ {BROKER_LABEL[b]} แล้ว (ปิด browser session)")
    await service._send_reply(reply_token, _text("\n".join(lines)))
    return {"status": "CLI_LOGOUT", "brokers": brokers}


# --------------------------------------------------------------------------- #
# Pillar 2 reads — DB snapshot (default) + live sync
# --------------------------------------------------------------------------- #
async def _read_db_positions(db: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Local ``positions`` snapshot (broker-agnostic homelab ledger)."""
    from app.db.models import Position
    res = await db.execute(select(Position).where(Position.volume > 0))
    rows: List[Dict[str, Any]] = []
    latest = None
    for p in res.scalars().all():
        cost = float(p.avg_cost or 0.0)
        last = float(p.current_price if p.current_price is not None else cost)
        ptype = _position_type(getattr(p, "position_type", None))
        rows.append({"symbol": p.symbol, "position_type": ptype, "volume": int(p.volume or 0),
                     "cost": cost, "last": last, "pnl_pct": _holding_pnl_pct(ptype, cost, last),
                     "unrealized_pnl": None, "market_value": None})
        if p.updated_at and (latest is None or p.updated_at > latest):
            latest = p.updated_at
    rows.sort(key=lambda r: r["volume"] * r["last"], reverse=True)
    return rows, (latest.isoformat() if latest else None)


async def _read_db_orders(db: Any) -> Tuple[List[Dict[str, Any]], int, int, Optional[str]]:
    """Local ``orders`` ledger snapshot."""
    from app.db.models import Order
    res = await db.execute(select(Order).order_by(Order.created_at.desc()))
    rows: List[Dict[str, Any]] = []
    open_count = 0
    latest = None
    for o in res.scalars().all():
        st = str(o.status or "").upper()
        if any(k in st for k in ("MATCH", "FILL", "COMPLETE", "DONE")):
            kind = "matched"
        elif "CANCEL" in st:
            kind = "cancelled"
        elif any(k in st for k in ("REJECT", "FAIL", "ERROR")):
            kind = "rejected"
        elif "PARTIAL" in st:
            kind = "partial"
        elif any(k in st for k in ("OPEN", "QUEUE", "PENDING", "SENT", "NEW", "WORKING", "SUBMITTED")):
            kind = "open"
        else:
            kind = "unknown"
        if kind in ("open", "partial"):
            open_count += 1
        rows.append({"kind": kind, "side": str(o.side or "").upper(), "symbol": str(o.symbol or "").upper(),
                     "volume": int(o.volume or 0), "price": float(o.price or 0.0),
                     "balance": int(o.volume or 0) if kind in ("open", "partial") else 0, "status": st})
        if o.updated_at and (latest is None or o.updated_at > latest):
            latest = o.updated_at
    return rows, open_count, len(rows), (latest.isoformat() if latest else None)


_POSITION_TYPES = ("LONG", "SHORT", "BORROWED", "UNKNOWN")


def _position_type(value: Any) -> str:
    """Normalise a holding side.

    A **missing** side means a cash-only book (LIBERATOR ``PositionItem`` has no side
    field) -> LONG. An **explicit** unrecognised value -> UNKNOWN (never guess a sign).
    """
    if value is None or str(value).strip() == "":
        return "LONG"
    v = str(value).strip().upper()
    return v if v in _POSITION_TYPES else "UNKNOWN"


def _holding_pnl_pct(position_type: str, cost: float, last: float) -> Optional[float]:
    """RCA-002: %P/L must follow the side — a SHORT gains when the price *falls*.

    Returns ``None`` (= render ``—``) when the sign cannot be known honestly:
    BORROWED / UNKNOWN side, or no cost base to divide by. Never fabricates ``0.0``.
    """
    ptype = (position_type or "LONG").upper()
    if ptype in ("BORROWED", "UNKNOWN") or not cost:
        return None
    if ptype == "SHORT":
        return (cost - last) / cost * 100.0
    return (last - cost) / cost * 100.0


def _normalise_holdings(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Broker-agnostic holding row — keeps the side plus the page's own P/L columns."""
    out = []
    for h in holdings or []:
        cost = float(h.get("avg_cost", 0.0) or 0.0)
        last = float(h.get("current_price") or h.get("market_price") or cost)
        ptype = _position_type(h.get("position_type"))
        unreal = h.get("unrealized_pnl")
        mval = h.get("market_value")
        out.append({"symbol": str(h.get("symbol", "")).upper(), "position_type": ptype,
                    "volume": int(h.get("volume", 0) or 0), "cost": cost, "last": last,
                    "pnl_pct": _holding_pnl_pct(ptype, cost, last),
                    "unrealized_pnl": float(unreal) if unreal is not None else None,
                    "market_value": float(mval) if mval is not None else None})
    out.sort(key=lambda r: r["volume"] * r["last"], reverse=True)
    return out


def _portfolio_totals(rows: List[Dict[str, Any]]) -> Tuple[float, float]:
    """(market value, unrealized P/L) for normalised rows.

    Prefers the page's own ``Unreal``/``Market Value`` columns; falls back to a
    **side-aware** ``volume x (last - cost)`` (inverted for SHORT) only when the page
    did not expose them. BORROWED / UNKNOWN rows with no P/L column contribute 0.0 —
    never a fabricated figure (Anti-Mock).
    """
    total = 0.0
    pnl = 0.0
    for r in rows:
        mv = r.get("market_value")
        total += float(mv) if mv is not None else r["volume"] * r["last"]
        up = r.get("unrealized_pnl")
        if up is None:
            ptype = str(r.get("position_type") or "LONG").upper()
            if ptype in ("BORROWED", "UNKNOWN"):
                up = 0.0
            elif ptype == "SHORT":
                up = -r["volume"] * (r["last"] - r["cost"])
            else:
                up = r["volume"] * (r["last"] - r["cost"])
        pnl += float(up)
    return total, pnl


def _portfolio_amount(rows: List[Dict[str, Any]]) -> Optional[float]:
    """Σ(volume x avg cost) — the app's *Amount* (cost basis) column, RCA-013.

    ``BORROWED`` (``(B)``) rows are excluded: the page exposes no cost basis for them,
    so counting them would invent one. Rows without a cost base are skipped too —
    ``None`` (render ``—``) when nothing can be summed, never ``0.0`` (Anti-Mock).
    """
    parts = [
        r["volume"] * r["cost"] for r in rows
        if r.get("cost") and str(r.get("position_type") or "LONG").upper() != "BORROWED"
    ]
    return sum(parts) if parts else None


def _split_borrowed(rows: List[Dict[str, Any]]
                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(main holdings, borrowed lots) — RCA-013 final, decisions D2/D3.

    ``(B)`` (``BORROWED``) rows leave the main table: ``main`` keeps only SHORT / LONG /
    UNKNOWN, while ``borrowed`` is ``[{"symbol", "volume"}]`` for every ``BORROWED`` row
    with ``volume > 0``, sorted by symbol. A zero-volume loan (e.g. ``BCPG (B)``) is
    dropped (D3). Broker-agnostic and pure — LIB rows are never ``BORROWED``, so this is
    a no-op there; the caller decides whether to render the section at all.
    """
    src = rows or []

    def _is_borrowed(r: Dict[str, Any]) -> bool:
        return str(r.get("position_type") or "LONG").upper() == "BORROWED"

    main = [r for r in src if not _is_borrowed(r)]
    borrowed = sorted(
        ({"symbol": str(r.get("symbol", "")), "volume": int(r.get("volume", 0) or 0)}
         for r in src if _is_borrowed(r) and int(r.get("volume", 0) or 0) > 0),
        key=lambda b: b["symbol"],
    )
    return main, borrowed


#: Display-only labels for raw account-type codes (LIBERATOR reports ``CASH_BALANCE``).
#: Presentation only — never touches the per-broker balance-value mapping (RCA-011).
_ACCOUNT_TYPE_LABEL = {
    "CASH_BALANCE": "Cash Balance", "CASH": "Cash", "MARGIN": "Margin",
    "EQUITY": "Equity", "DERIVATIVES": "Derivatives",
}


def _account_type_label(value: Any) -> str:
    raw = str(value or "").strip()
    return _ACCOUNT_TYPE_LABEL.get(raw.upper(), raw or "CASH")


_CAT_KIND = {
    "MATCHED": "matched", "PARTIALLY_MATCHED": "partial", "UNMATCHED": "open",
    "CANCELLED": "cancelled", "REJECTED": "rejected", "UNKNOWN": "unknown",
}


def _is_stale(iso_ts: Optional[str], minutes: int = 60) -> bool:
    if not iso_ts:
        return False
    try:
        return (_now_bkk() - datetime.fromisoformat(iso_ts).astimezone()) > timedelta(minutes=minutes)
    except (ValueError, TypeError):
        return False


def _broker_label(broker: Optional[str]) -> str:
    return "ALL" if broker in (None, "all") else BROKER_LABEL.get(broker, str(broker).upper())


async def _live_card(kind: str, broker: str) -> Dict[str, Any]:
    """Build a live card for one broker from its own Pillar-2 read function."""
    is_test = False
    try:
        from app.services.trade_dispatcher import trade_dispatcher
        is_test = not trade_dispatcher.is_live
    except Exception:
        pass
    plat = _broker_platform(broker)
    now_label = _now_bkk().strftime("%H:%M")

    if kind == "port":
        from app.mcp.pillars.pillar2_portfolio import portfolio_holdings
        res = await portfolio_holdings(platform=plat)
        # RCA-006b: a TradeMan scrape only counts as live when it ran on an authenticated
        # page AND a verified account — otherwise the card must say "อ่านไม่ได้".
        account_label = "LIVE"
        # RCA-013: the on-page summary row is TradeMan-only — never reuse another
        # broker's DOM for it (broker isolation). Empty for LIB / unknown platforms.
        summary: Dict[str, Any] = {}
        if plat in ("KRUNGSRI", "TRADEMAN"):
            from app.browser.trademan_driver import trademan_driver
            if not getattr(trademan_driver, "portfolio_scrape_authenticated", False):
                return cards.unavailable_card(broker=BROKER_LABEL[broker], login_cmd=f"/login {broker}")
            account_label = getattr(trademan_driver, "active_account_no", None) or "LIVE"
            summary = getattr(trademan_driver, "portfolio_totals", None) or {}
        elif plat == "LIBERATOR":
            # C2 (TASK-loop1-1): the Liberator account number read off the screen replaces the
            # generic "LIVE" placeholder in the `/port lib sync` card header.
            account_label = str(res.get("account_no") or "LIVE")
        rows = _normalise_holdings(res.get("holdings", []))
        # D2/D3: (B) rows leave the main table and render as their own
        # "หุ้นยืมคงเหลือ (B)" section. Market Value is no longer shown (D1) — the page's
        # totals row still feeds Amount, and Unrealized/%P/L keep the P1 formula
        # (BORROWED rows never contributed to it).
        main_rows, borrowed = _split_borrowed(rows)
        total, pnl = _portfolio_totals(rows)
        amount = _portfolio_amount(rows)
        if summary.get("amount") is not None:
            amount = summary["amount"]
        cost_base = total - pnl
        pnl_pct = (pnl / cost_base * 100.0) if cost_base else 0.0
        return cards.port_card(broker=BROKER_LABEL[broker], account=account_label,
                               amount=amount, pnl_value=pnl, pnl_pct=pnl_pct,
                               rows=main_rows,
                               # Broker isolation: only KSS/TradeMan has (B) loans.
                               borrowed=borrowed if plat in ("KRUNGSRI", "TRADEMAN") else [],
                               snapshot_label=now_label, stale=False, live=True,
                               is_test=is_test)

    if kind == "orders":
        from app.mcp.pillars.pillar2_portfolio import current_orders
        res = await current_orders(platform=plat)
        # TASK-loop1-1 (Anti-Mock): a broker that reports `authenticated is False` did not
        # really read its ledger — say "อ่านไม่ได้" instead of rendering an empty order list
        # under a 🟢 live badge.
        if res.get("authenticated") is False:
            return cards.unavailable_card(broker=BROKER_LABEL[broker], login_cmd=f"/login {broker}")
        ledger = res.get("orders", []) or []
        rows = [{"kind": _CAT_KIND.get(str(o.get("status_category", "")).upper(), "unknown"),
                 "side": o.get("side", ""), "symbol": o.get("symbol", ""), "volume": o.get("volume", 0),
                 "price": o.get("price", 0.0), "balance": o.get("balance", 0),
                 "status": str(o.get("status_raw", ""))} for o in ledger]
        return cards.orders_card(broker=BROKER_LABEL[broker], total=res.get("total", len(rows)),
                                 open_count=res.get("unmatched_count", 0), rows=rows[:10],
                                 snapshot_label=now_label, live=True, show_nego=True)

    # cash
    from app.mcp.pillars.pillar2_portfolio import portfolio_get_balances
    res = await portfolio_get_balances(platform=plat)
    accounts = res.get("accounts", []) or []

    if plat in ("KRUNGSRI", "TRADEMAN"):
        # CLI-RCA-011 (P2a): render ONLY the account whose values were bound to the account
        # number read off the dropdown — a figure must never sit under another account's
        # header (money-movement safety). "—" alone never counts as readable (RCA-009).
        acc = next((a for a in accounts if a.get("values_bound") is True), None)
        if res.get("authenticated") is False or acc is None or acc.get("line_available") is None:
            return cards.unavailable_card(broker=BROKER_LABEL[broker], login_cmd=f"/login {broker}")
        rows: List[Dict[str, str]] = [
            {"label": "Line Available", "value": f"{float(acc['line_available']):,.2f}"},
        ]
        if str(acc.get("account_type") or "").upper() == "MARGIN":
            ee = acc.get("excess_equity")
            rows.append({"label": "Excess Equity",
                         "value": f"{float(ee):,.2f}" if ee is not None else "—"})
        # CLI-RCA-011 (P2b): the honest Account Info "Cash Balance" row — rendered only when
        # the driver actually read it (Anti-Mock: never a fabricated 0.00). The CASH account
        # exposes no such row, so it legitimately stays hidden there.
        cash_balance = acc.get("cash_balance")
        if cash_balance is not None:
            rows.append({"label": "Cash balance", "value": f"{float(cash_balance):,.2f}"})
        return cards.cash_card(broker=BROKER_LABEL[broker],
                               account=_account_type_label(acc.get("account_type")),
                               rows=rows, snapshot_label=now_label, live=True)

    # LIB / other platforms: legacy behaviour kept verbatim (broker isolation, RCA-007).
    acc = next((a for a in accounts if a.get("is_active")), accounts[0] if accounts else {})
    rows = []
    if acc.get("cash_balance") is not None:
        rows.append({"label": "เงินสด / Cash balance", "value": f"{float(acc['cash_balance']):,.2f}"})
    if acc.get("line_available") is not None:
        rows.append({"label": "กำลังซื้อ / Buying power", "value": f"{float(acc['line_available']):,.2f}"})
    if acc.get("excess_equity") is not None:
        rows.append({"label": "Excess equity", "value": f"{float(acc['excess_equity']):,.2f}"})
    if res.get("authenticated") is False or not rows:
        # RCA-009: unauthenticated or every field unreadable -> never render 🟢 live
        # and never show a fabricated 0.00.
        return cards.unavailable_card(broker=BROKER_LABEL[broker], login_cmd=f"/login {broker}")
    return cards.cash_card(broker=BROKER_LABEL[broker],
                           account=_account_type_label(acc.get("account_type")),
                           rows=rows, snapshot_label=now_label, live=True)


async def _handle_read(
    parsed: CliCommand, service: Any, reply_token: Optional[str], push_target: Optional[str], db: Any
) -> Dict[str, Any]:
    """``/port`` / ``/cash`` / ``/orders`` — DB snapshot by default, ``sync`` = live."""
    kind = parsed.cmd
    brokers = ["kss", "lib"] if parsed.broker == "all" else [parsed.broker]
    label = _broker_label(parsed.broker)

    if not parsed.has("sync"):
        if kind == "port":
            rows, ts = await _read_db_positions(db)
            if not rows:
                await service._send_reply(reply_token, _text(f"ℹ️ ยังไม่มี snapshot — ใช้ /port {parsed.broker} sync"))
                return {"status": "CLI_NO_DATA"}
            total, pnl = _portfolio_totals(rows)
            base = total - pnl
            main_rows, borrowed = _split_borrowed(rows)
            if _broker_platform(parsed.broker) not in ("KRUNGSRI", "TRADEMAN"):
                borrowed = []          # broker isolation: LIB has no (B) section
            card = cards.port_card(broker=label, account="DB snapshot",
                                   amount=_portfolio_amount(rows), pnl_value=pnl,
                                   pnl_pct=(pnl / base * 100.0 if base else 0.0), rows=main_rows,
                                   borrowed=borrowed,
                                   snapshot_label=_fmt_hhmm(ts), stale=_is_stale(ts), live=False)
            await service._send_reply(reply_token, card)
            return {"status": "CLI_PORT", "count": len(rows)}
        if kind == "orders":
            rows, open_count, total, ts = await _read_db_orders(db)
            if not rows:
                await service._send_reply(reply_token, _text(f"ℹ️ ยังไม่มีออเดอร์ในระบบ — ใช้ /orders {parsed.broker} sync"))
                return {"status": "CLI_NO_DATA"}
            card = cards.orders_card(broker=label, total=total, open_count=open_count, rows=rows[:10],
                                     snapshot_label=_fmt_hhmm(ts), live=False, show_nego=True)
            await service._send_reply(reply_token, card)
            return {"status": "CLI_ORDERS", "count": total}
        # cash has no local snapshot table
        await service._send_reply(reply_token, _text(f"ℹ️ ยังไม่มี snapshot เงินสด — ใช้ /cash {parsed.broker} sync"))
        return {"status": "CLI_NO_DATA"}

    # sync = live scrape; session must already be alive (Invariant 7 — never auto-login)
    key = (kind, parsed.broker or "-")
    lock = _lock_for(*key)
    if lock.locked():
        await service._send_reply(reply_token, _text(
            f"⏳ /{kind} {parsed.broker} กำลังทำงานอยู่ (เริ่ม {_STARTED.get(key, '-')}) — รอผลสักครู่"))
        return {"status": "CLI_BUSY"}
    async with lock:
        _STARTED[key] = _now_bkk().strftime("%H:%M:%S")
        try:
            for b in brokers:
                if not await _broker_session_alive(b):
                    await service._send_reply(reply_token, _text(
                        f"🔴 {BROKER_LABEL[b]} session หลุด — /login {b} ก่อน แล้วค่อย sync"))
                    return {"status": "CLI_SESSION_DOWN", "broker": b}
            await service._send_reply(reply_token, _text(f"🔄 กำลังดึงข้อมูลสด {label}…"))
            for b in brokers:
                await service.push_message(await _live_card(kind, b), to_user_id=push_target)
        except Exception as e:
            logger.exception(f"LINE CLI /{kind} {parsed.broker} sync failed")
            await service.push_message(
                _text(f"❌ {label} ดึงข้อมูลสดไม่สำเร็จ: {type(e).__name__}: {str(e)[:120]}"),
                to_user_id=push_target)
        finally:
            _STARTED.pop(key, None)
    return {"status": "CLI_SYNC", "brokers": brokers}


# --------------------------------------------------------------------------- #
# /nego
# --------------------------------------------------------------------------- #
#: Amend outcomes that must HALT the /nego batch (fail-closed, Loop 1 D3): the price basis
#: could not be read, or the order's identity could not be proven. Those are pushed as the
#: honest "อ่านไม่ได้" card — a normal ``skip``/``fail`` row would look like a routine policy
#: decision and would hide a broker/session problem.
_NEGO_HALT_STATUSES = ("QUOTE_UNAVAILABLE", "SYMBOL_MISMATCH")


async def _audit_nego(db: Any, broker: str, row: Dict[str, Any]) -> None:
    try:
        from app.db.models import SessionLog
        db.add(SessionLog(
            event_type="LINE_CLI_NEGO",
            details=(f"{broker} #{row.get('order_no')} {row.get('side')} {row.get('symbol')} "
                     f"{row.get('status')} {row.get('reason', '')}").strip(),
        ))
        await db.commit()
    except Exception as e:  # pragma: no cover - audit must never break the command
        logger.warning("LINE_CLI_NEGO audit failed: %s", e)


async def _plan_nego(broker: str, o: Dict[str, Any], max_ticks: int) -> Dict[str, Any]:
    """
    Evaluate one order against the market and the G4–G6 guardrails.

    Never mutates anything — returns a row with ``status`` in
    ``{"planned", "skip"}`` and a human ``reason``. Anti-Mock: any unavailable
    quote fails closed (skip), never a guessed price — both the legacy
    ``source="unavailable"`` marker and the explicit ``success=False``
    ``QUOTE_UNAVAILABLE`` envelope (Loop 1 D1) mean "no price basis".
    """
    from app.services.quicktrade_negotiation_service import OrderSnapshot, Quote, plan_negotiation

    order_no = str(o.get("broker_order_no") or o.get("order_no") or "")
    symbol = str(o.get("symbol", "")).upper()
    side = str(o.get("side", "")).upper()
    old = float(o.get("price", 0.0) or 0.0)
    vol = int(o.get("balance") or o.get("volume") or 0)
    row: Dict[str, Any] = {"order_no": order_no, "symbol": symbol, "side": side, "old_price": old, "volume": vol}

    if vol <= 0:
        row.update(status="skip", reason="ไม่เหลือจำนวนให้ต่อ")
        return row

    quote = await _broker_quote(broker, symbol)
    if quote.get("success") is False or quote.get("source") == "unavailable":
        row.update(status="skip", reason="อ่านราคาตลาดไม่ได้ (fail-closed)")
        return row

    q_obj = Quote(symbol=symbol, best_bid=quote.get("bid_1"), best_offer=quote.get("offer_1"), last=quote.get("last"))
    order_snap = OrderSnapshot(order_no=order_no, symbol=symbol, side=side, price=old, balance=vol)

    decision = plan_negotiation(order_snap, q_obj, max_ticks=max_ticks)

    if decision.outcome.value == "OK":
        row.update(status="planned", new_price=decision.target_price)
    elif decision.outcome.value == "NO_CHANGE":
        row.update(status="skip", reason="อยู่ที่เป้าหมายแล้ว")
    elif decision.outcome.value == "UPTICK_VIOLATION":
        row.update(status="skip", reason="ผิดกฎ uptick")
    elif decision.outcome.value == "NO_QUOTE":
        row.update(status="skip", reason="อ่านราคาตลาดไม่ได้ (fail-closed)")
    else:
        row.update(status="skip", reason=decision.reason)

    return row


# Quick Trade outcome -> the wording the /nego card shows for a skipped order.
_QUICKTRADE_SKIP_REASON = {
    "NO_CHANGE": "อยู่ที่เป้าหมายแล้ว",
    "UPTICK_VIOLATION": "ผิดกฎ uptick (SHORT ต้องสูงกว่าราคาล่าสุด)",
    "TICK_SIZE_VIOLATION": "ไม่ผ่าน tick-size",
    "MAX_TICKS_EXCEEDED": "ห่างเกินจำนวน tick ที่อนุญาต",
    "NO_QUOTE": "อ่านราคาตลาดไม่ได้ (fail-closed)",
}


def _apply_quicktrade_result(row: Dict[str, Any], res: Dict[str, Any]) -> None:
    """Fold a Quick Trade in-place result into a ``/nego`` card row (Anti-Mock).

    The service re-reads the ledger + quote and applies G4/G5/G6 itself, so its
    ``current_price``/``target_price``/``outcome`` are what the card must report: a
    refusal or ``NO_CHANGE`` is a *skip*, never an ``ok``.
    """
    if res.get("current_price") is not None:
        row["old_price"] = res["current_price"]
    if res.get("target_price") is not None:
        row["new_price"] = res["target_price"]
    outcome = str(res.get("outcome") or "")
    row["outcome"] = outcome or None
    row["submitted"] = res.get("submitted")      # the one-order card reads this (Anti-Mock)
    if outcome in _QUICKTRADE_SKIP_REASON:
        row["status"] = "skip"
        row["reason"] = _QUICKTRADE_SKIP_REASON[outcome]
    elif res.get("success"):
        row["status"] = "ok"
        if res.get("submitted") is False and res.get("dry_run"):
            row["reason"] = "DRY-RUN — ยังไม่กดส่ง"       # honest: staged, not sent
    else:
        row["status"] = "fail"
        row["reason"] = str(res.get("error") or res.get("reason") or "ล้มเหลว")[:40]


async def _handle_nego(
    parsed: CliCommand, service: Any, reply_token: Optional[str], push_target: Optional[str], db: Any
) -> Dict[str, Any]:
    from app.services.kill_switch_service import kill_switch_service
    from app.services.trade_dispatcher import trade_dispatcher

    broker = parsed.broker
    if kill_switch_service.is_active():                       # G1
        await service._send_reply(reply_token, _text("⛔ KILL-SWITCH ACTIVE — คำสั่งถูกระงับ · พิมพ์ RESET เพื่อปลด"))
        return {"status": "CLI_KILL_SWITCH"}
    if not _in_nego_window():                                 # G2
        await service._send_reply(reply_token, _text(f"🌙 นอกเวลาที่อนุญาต ({settings.LINE_NEGO_WINDOWS})"))
        return {"status": "CLI_OUT_OF_HOURS"}
    if not await _broker_session_alive(broker):               # G3
        await service._send_reply(reply_token, _text(f"🔴 {BROKER_LABEL[broker]} session หลุด — /login {broker} ก่อน"))
        return {"status": "CLI_SESSION_DOWN", "broker": broker}

    key = ("nego", broker)
    lock = _lock_for(*key)
    if lock.locked():
        await service._send_reply(reply_token, _text(
            f"⏳ /nego {broker} กำลังทำงานอยู่ (เริ่ม {_STARTED.get(key, '-')}) — รอผลสักครู่"))
        return {"status": "CLI_BUSY"}

    max_ticks = int(getattr(settings, "LINE_NEGO_MAX_TICKS", 3))
    ok = skipped = failed = 0
    results: List[Dict[str, Any]] = []
    #: Fail-closed stop signal: set when an amend reports "no price basis / identity unproven"
    #: (``_NEGO_HALT_STATUSES``) — the batch then breaks and the honest card is pushed.
    halted = False
    halt_status = ""
    async with lock:
        _STARTED[key] = _now_bkk().strftime("%H:%M:%S")
        try:
            orders = await _broker_open_orders(broker)
            if parsed.target:
                if parsed.target.isdigit():
                    orders = [o for o in orders
                              if str(o.get("broker_order_no") or o.get("order_no") or "") == parsed.target]
                else:
                    orders = [o for o in orders if str(o.get("symbol", "")).upper() == parsed.target]
            if not orders:
                msg = (f"❓ ไม่พบออเดอร์ค้างของ {parsed.target} ใน {BROKER_LABEL[broker]}" if parsed.target
                       else f"ℹ️ {BROKER_LABEL[broker]} ไม่มีออเดอร์ค้างให้ต่อราคา")
                await service._send_reply(reply_token, _text(msg))
                return {"status": "CLI_NEGO_EMPTY", "broker": broker}

            mode = "LIVE" if trade_dispatcher.is_live else "TEST"
            await service._send_reply(reply_token, _text(
                f"⚡ [{mode}] กำลังต่อราคา {BROKER_LABEL[broker]} · {len(orders)} ออเดอร์ค้าง…"))

            for o in orders:
                row = await _plan_nego(broker, o, max_ticks)
                if row["status"] == "planned":
                    res = await _broker_modify(broker, order_no=row["order_no"], new_price=row["new_price"],
                                               symbol=row["symbol"], side=row["side"], volume=row["volume"])
                    if res.get("path") == "QUICKTRADE_INPLACE":
                        # kss LIVE: report what Quick Trade actually did (its own quote +
                        # guardrails decide), not the handler's preview.
                        _apply_quicktrade_result(row, res)
                    elif res.get("success"):
                        row["status"] = "ok"
                    else:
                        row["status"] = "fail"
                        row["reason"] = str(res.get("error") or res.get("message") or "ล้มเหลว")[:40]
                        if str(res.get("status") or "") in _NEGO_HALT_STATUSES:
                            halted, halt_status = True, str(res["status"])   # fail-closed
                    row.setdefault("submitted", res.get("submitted"))
                if row["status"] == "ok":
                    ok += 1
                elif row["status"] == "skip":
                    skipped += 1
                else:
                    failed += 1
                results.append(row)
                await _audit_nego(db, broker, row)
                if halted:
                    # Stop the batch: the board (or the order's identity) could not be proven,
                    # so nothing else may be pressed. The honest "อ่านไม่ได้" card is pushed
                    # below instead of a per-order table.
                    logger.warning(
                        "LINE CLI /nego %s halted (%s) on #%s: %s",
                        broker, halt_status, row.get("order_no"), row.get("reason"),
                    )
                    break

            ts = _now_bkk().strftime("%H:%M:%S")
            is_test = not trade_dispatcher.is_live
            dry_run = getattr(settings, "DRY_RUN_MODE", False)
            single = results[0] if len(results) == 1 else None
            if halted:
                # Fail-closed: no price basis (or an unproven order identity) ⇒ the honest
                # read-failure card, never a "normal" per-order summary.
                card = cards.unavailable_card(
                    broker=BROKER_LABEL[broker], login_cmd=f"/login {broker}")
            elif single is not None and str(parsed.target or "").isdigit():
                # One explicit order_no -> the focused one-order card (D2), filled from
                # the row that mirrors what the broker actually did.
                card = cards.negotiate_card(
                    order_no=str(single.get("order_no") or parsed.target),
                    symbol=str(single.get("symbol") or "-"),
                    side=str(single.get("side") or "-"),
                    outcome=str(single.get("outcome") or single.get("status") or ""),
                    current_price=single.get("old_price"),
                    target_price=single.get("new_price"),
                    volume=single.get("volume"),
                    reason=str(single.get("reason") or ""),
                    submitted=single.get("submitted"),
                    ts=ts,
                    is_test=is_test,
                    dry_run=dry_run,
                )
            else:
                card = cards.nego_card(broker=BROKER_LABEL[broker], results=results, ok=ok, skipped=skipped,
                                       failed=failed, ts=ts, is_test=is_test, dry_run=dry_run)
            await service.push_message(card, to_user_id=push_target)
        except Exception as e:
            logger.exception(f"LINE CLI /nego {broker} failed")
            await service.push_message(
                _text(f"❌ {BROKER_LABEL[broker]} ต่อราคาไม่สำเร็จ: {type(e).__name__}: {str(e)[:120]}"),
                to_user_id=push_target)
        finally:
            _STARTED.pop(key, None)
    return {"status": "CLI_NEGO", "broker": broker, "ok": ok, "skipped": skipped, "failed": failed,
            "halted": halted, "halt_status": halt_status}


# --------------------------------------------------------------------------- #
# /negotiate (Quick Trade in-place price amendment, Pillar 6)
# --------------------------------------------------------------------------- #
async def _handle_negotiate(
    parsed: CliCommand, service: Any, reply_token: Optional[str], push_target: Optional[str], db: Any
) -> Dict[str, Any]:
    """``/negotiate <order_no>`` — alias of ``/nego kss <order_no>`` (ONE path).

    Kept for muscle memory / older cards: the command is rewritten into the unified
    ``/nego kss`` flow, so the duplicate G1/G2/lock implementation is gone and the
    guardrails live in exactly one place (D1/D2 — TASK-loop1-2).
    """
    order_no = str(parsed.target or "").strip()
    if not order_no.isdigit():
        await service._send_reply(reply_token, _text(
            "❓ รูปแบบ: /negotiate <order_no> เช่น /negotiate 11008198",
            quick=["/orders kss"]))
        return {"status": "CLI_NEGOTIATE_BAD_ARGS"}

    res = await _handle_nego(CliCommand(cmd="nego", broker="kss", target=order_no),
                             service, reply_token, push_target, db)
    res["order_no"] = order_no
    return res


# --------------------------------------------------------------------------- #
# Entrypoint (called by line_service)
# --------------------------------------------------------------------------- #
async def handle(parsed: Any, *, db: Any, raw_event: Dict[str, Any], service: Any) -> Dict[str, Any]:
    """
    Auth-gate, clear any pending conversation flow, then dispatch one parsed command.

    ``service`` is the ``LineMessagingService`` instance (injected to avoid a
    circular import); ``db`` is the webhook's AsyncSession.
    """
    from app.services.conversation_state import conversation_state

    user_id, group_id, source_type, push_target = _source_of(raw_event)
    reply_token = (raw_event or {}).get("replyToken")

    if not conversation_state.is_authorized(user_id, source_type=source_type, group_id=group_id):
        await service._send_reply(reply_token, _text("⛔ ไม่มีสิทธิ์ใช้คำสั่งนี้จากห้องนี้"))
        return {"status": "CLI_UNAUTHORIZED"}

    if user_id:
        conversation_state.clear(user_id)   # a `/` command abandons any pending flow

    if isinstance(parsed, CliError):
        msg = parsed.message + (f"\n{parsed.hint}" if parsed.hint else "")
        await service._send_reply(reply_token, _text(msg, quick=parsed.quick_reply or None))
        return {"status": "CLI_ERROR", "code": parsed.code}

    cmd = parsed.cmd
    if cmd == "help":
        return await _handle_help(parsed, service, reply_token)
    if cmd == "status":
        return await _handle_status(service, reply_token)
    if cmd == "login":
        return await _handle_login(parsed, service, reply_token, push_target)
    if cmd == "logout":
        return await _handle_logout(parsed, service, reply_token)
    if cmd in ("port", "cash", "orders"):
        return await _handle_read(parsed, service, reply_token, push_target, db)
    if cmd == "nego":
        return await _handle_nego(parsed, service, reply_token, push_target, db)
    if cmd == "negotiate":
        return await _handle_negotiate(parsed, service, reply_token, push_target, db)

    await service._send_reply(reply_token, _text("❓ ไม่รู้จักคำสั่ง · พิมพ์ /help"))
    return {"status": "CLI_UNKNOWN", "cmd": cmd}


__all__ = ["handle", "_LOCKS", "_STARTED", "_in_nego_window", "_plan_nego"]
