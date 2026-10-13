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
    """Unmatched/open orders for ``broker`` only."""
    if broker == "kss":
        from app.browser.trademan_driver import trademan_driver
        orders = await trademan_driver.scrape_unmatched_orders()
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

    TEST -> shared virtual simulator (through the dispatcher); LIVE -> the
    broker's own driver (KSS cancel+replace per KSS-RCA-016; LIB native in-place
    ``Change`` per LIB-RCA-016/017). The dispatcher's LIVE route is bound to
    ``TRADING_PLATFORM`` and cannot address both brokers in one loop, so LIVE
    goes straight to the owning driver.
    """
    from app.services.trade_dispatcher import trade_dispatcher
    if not trade_dispatcher.is_live:
        return await trade_dispatcher.dispatch_price_modification(
            broker_order_no=order_no, new_price=new_price, symbol=symbol, side=side, volume=volume
        )
    if broker == "kss":
        from app.browser.trademan_driver import trademan_driver
        return await trademan_driver.modify_order_price(
            broker_order_no=order_no, symbol=symbol, side=side,
            new_price=new_price, remaining_volume=volume,
        )
    from app.brokers import liberator_plugin
    return await liberator_plugin.change_order(order_no=order_no, new_price=new_price)


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
    "ฉุกเฉิน: PANIC · RESET · MODE\n"
    "พิมพ์ /help nego เพื่อดูรายละเอียด"
)

_HELP_NEGO = (
    "⚡ /nego — ต่อราคาออเดอร์ค้าง (ทำทันที ไม่ต้องอนุมัติ)\n"
    "รูปแบบ: /nego kss|lib [SYMBOL|order_no]\n"
    "• ไม่ระบุเป้าหมาย = ทุกออเดอร์ค้างของโบรกเกอร์นั้น\n"
    "• ราคาเป้าหมาย: BUY/COVER→Bid1 · SELL→Offer1 · SHORT→Offer1 (ผ่าน uptick)\n"
    "Guardrails (ต่อออเดอร์):\n"
    "  G1 kill-switch ไม่ active\n"
    "  G2 ในเวลาที่อนุญาต (LINE_NEGO_WINDOWS)\n"
    "  G3 session alive (ไม่ login เอง)\n"
    "  G4 ผ่าน SET tick-size\n"
    "  G5 |ราคาใหม่−เดิม| ≤ LINE_NEGO_MAX_TICKS tick\n"
    "  G6 SHORT ต้องผ่านกฎ uptick"
)


async def _handle_help(parsed: CliCommand, service: Any, reply_token: Optional[str]) -> Dict[str, Any]:
    if parsed.target == "nego":
        await service._send_reply(reply_token, _text(_HELP_NEGO))
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
        pnl_pct = ((last - cost) / cost * 100.0) if cost else 0.0
        rows.append({"symbol": p.symbol, "volume": int(p.volume or 0), "cost": cost,
                     "last": last, "pnl_pct": pnl_pct})
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


def _normalise_holdings(holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for h in holdings or []:
        cost = float(h.get("avg_cost", 0.0) or 0.0)
        last = float(h.get("current_price") or h.get("market_price") or cost)
        pnl_pct = ((last - cost) / cost * 100.0) if cost else 0.0
        out.append({"symbol": str(h.get("symbol", "")).upper(), "volume": int(h.get("volume", 0) or 0),
                    "cost": cost, "last": last, "pnl_pct": pnl_pct})
    out.sort(key=lambda r: r["volume"] * r["last"], reverse=True)
    return out


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
        rows = _normalise_holdings(res.get("holdings", []))
        total = sum(r["volume"] * r["last"] for r in rows)
        pnl = sum(r["volume"] * (r["last"] - r["cost"]) for r in rows)
        cost_base = total - pnl
        pnl_pct = (pnl / cost_base * 100.0) if cost_base else 0.0
        return cards.port_card(broker=BROKER_LABEL[broker], account="LIVE", total_value=total, pnl_value=pnl,
                               pnl_pct=pnl_pct, rows=rows[:10], overflow=max(0, len(rows) - 10),
                               snapshot_label=now_label, stale=False, live=True, is_test=is_test)

    if kind == "orders":
        from app.mcp.pillars.pillar2_portfolio import current_orders
        res = await current_orders(platform=plat)
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
    acc = next((a for a in accounts if a.get("is_active")), accounts[0] if accounts else {})
    rows: List[Dict[str, str]] = []
    if acc.get("cash_balance") is not None:
        rows.append({"label": "เงินสด / Cash balance", "value": f"{float(acc['cash_balance']):,.2f}"})
    if acc.get("line_available") is not None:
        rows.append({"label": "กำลังซื้อ / Buying power", "value": f"{float(acc['line_available']):,.2f}"})
    if acc.get("excess_equity") is not None:
        rows.append({"label": "Excess equity", "value": f"{float(acc['excess_equity']):,.2f}"})
    if not rows:
        rows.append({"label": "ℹ️", "value": "ไม่พบข้อมูลวงเงินจากโบรกเกอร์"})
    return cards.cash_card(broker=BROKER_LABEL[broker], account=acc.get("account_type", "CASH"),
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
            total = sum(r["volume"] * r["last"] for r in rows)
            pnl = sum(r["volume"] * (r["last"] - r["cost"]) for r in rows)
            base = total - pnl
            card = cards.port_card(broker=label, account="DB snapshot", total_value=total, pnl_value=pnl,
                                   pnl_pct=(pnl / base * 100.0 if base else 0.0), rows=rows[:10],
                                   overflow=max(0, len(rows) - 10), snapshot_label=_fmt_hhmm(ts),
                                   stale=_is_stale(ts), live=False)
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
        finally:
            _STARTED.pop(key, None)
    return {"status": "CLI_SYNC", "brokers": brokers}


# --------------------------------------------------------------------------- #
# /nego
# --------------------------------------------------------------------------- #
def _tick_distance_exceeds(old: float, new: float, n: int) -> bool:
    """G5 — is ``new`` more than ``n`` SET ticks away from ``old``?"""
    from app.services.validator import validator
    if abs(new - old) < 1e-9:
        return False
    if new > old:
        return new > validator.get_next_tick(old, n) + 1e-6
    return new < validator.get_next_tick(old, -n) - 1e-6


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
    quote fails closed (skip), never a guessed price.
    """
    from app.services.validator import validator
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
    bid1, offer1, last = quote.get("bid_1"), quote.get("offer_1"), quote.get("last")
    new_price = bid1 if side in ("BUY", "COVER") else (offer1 if side in ("SELL", "SHORT") else None)
    if quote.get("source") == "unavailable" or not new_price:
        row.update(status="skip", reason="อ่านราคาตลาดไม่ได้ (fail-closed)")
        return row
    new_price = float(new_price)
    if abs(new_price - old) < 0.005:
        row.update(status="skip", reason="อยู่ที่เป้าหมายแล้ว")
        return row
    if not validator.validate_tick_size(new_price)[0]:                 # G4
        row.update(status="skip", reason="ไม่ผ่าน tick-size")
        return row
    if _tick_distance_exceeds(old, new_price, max_ticks):              # G5
        row.update(status="skip", reason=f"ห่างเกิน {max_ticks} tick")
        return row
    if side == "SHORT" and not validator.validate_short_uptick(new_price, last)[0]:  # G6
        row.update(status="skip", reason="ผิดกฎ uptick")
        return row
    row.update(status="planned", new_price=new_price)
    return row


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
                    if res.get("success"):
                        row["status"] = "ok"
                        ok += 1
                    else:
                        row["status"] = "fail"
                        row["reason"] = str(res.get("error") or res.get("message") or "ล้มเหลว")[:40]
                        failed += 1
                else:
                    skipped += 1
                results.append(row)
                await _audit_nego(db, broker, row)

            card = cards.nego_card(broker=BROKER_LABEL[broker], results=results, ok=ok, skipped=skipped,
                                   failed=failed, ts=_now_bkk().strftime("%H:%M:%S"),
                                   is_test=not trade_dispatcher.is_live)
            await service.push_message(card, to_user_id=push_target)
        finally:
            _STARTED.pop(key, None)
    return {"status": "CLI_NEGO", "broker": broker, "ok": ok, "skipped": skipped, "failed": failed}


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

    await service._send_reply(reply_token, _text("❓ ไม่รู้จักคำสั่ง · พิมพ์ /help"))
    return {"status": "CLI_UNKNOWN", "cmd": cmd}


__all__ = ["handle", "_LOCKS", "_STARTED", "_in_nego_window", "_tick_distance_exceeds", "_plan_nego"]
