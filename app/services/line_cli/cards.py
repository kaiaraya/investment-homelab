"""
LINE Flex card builders for the slash-command CLI.

Pure functions: ``dict`` in -> LINE message ``dict`` out. No I/O, no broker
calls — so the exact layout can be unit-tested. Layouts follow the approved
mockups in ``docs/handoff/TASK-line-cli-design.md`` §3 and reuse the dark
theme already used by ``line_service.build_trade_approval_card``.
"""

from typing import Any, Dict, List, Optional

HEADER_BG = "#0f172a"
BODY_BG = "#1e293b"
FG = "#f8fafc"
MUTED = "#94a3b8"
LIVE_COLOR = "#DC2626"
TEST_COLOR = "#2563EB"
KILL_COLOR = "#dc2626"
UP = "#4ade80"
DOWN = "#f87171"
WARN = "#facc15"


# --------------------------------------------------------------------------- #
# Small building blocks
# --------------------------------------------------------------------------- #
def quick_reply(labels: List[str]) -> Dict[str, Any]:
    """Message-action quick reply buttons (label == text == command)."""
    return {
        "items": [
            {"type": "action", "action": {"type": "message", "label": lbl, "text": lbl}}
            for lbl in labels
        ]
    }


def _badge(text: str, bg: str, color: str = "#ffffff") -> Dict[str, Any]:
    return {
        "type": "box", "layout": "vertical", "backgroundColor": bg,
        "cornerRadius": "4px", "paddingStart": "8px", "paddingEnd": "8px",
        "paddingTop": "2px", "paddingBottom": "2px",
        "contents": [{"type": "text", "text": text, "color": color, "weight": "bold", "size": "xxs", "align": "center"}],
    }


def _kv(label: str, value: str, value_color: str = FG, flex_label: int = 3, flex_value: int = 5) -> Dict[str, Any]:
    return {
        "type": "box", "layout": "horizontal", "margin": "xs",
        "contents": [
            {"type": "text", "text": label, "color": MUTED, "size": "sm", "flex": flex_label},
            {"type": "text", "text": value, "color": value_color, "size": "sm", "weight": "bold",
             "flex": flex_value, "align": "end", "wrap": True},
        ],
    }


def _row(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "box", "layout": "horizontal", "margin": "xs", "contents": cells}


def _cell(text: str, color: str = FG, flex: int = 1, align: str = "start", weight: str = "regular") -> Dict[str, Any]:
    return {"type": "text", "text": text, "color": color, "size": "xs", "flex": flex, "align": align, "weight": weight}


def _footer(buttons: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": buttons}


def _msg_button(label: str, text: str, color: str = "#334155") -> Dict[str, Any]:
    return {
        "type": "button", "style": "primary", "color": color, "height": "sm", "flex": 1,
        "action": {"type": "message", "label": label, "text": text},
    }


def _bubble(
    *,
    title: str,
    badge: Optional[str] = None,
    badge_bg: str = "#334155",
    body: List[Dict[str, Any]],
    footer: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    header_contents: List[Dict[str, Any]] = [
        {"type": "box", "layout": "horizontal", "justifyContent": "space-between", "alignItems": "center",
         "contents": [
             {"type": "text", "text": title, "color": FG, "weight": "bold", "size": "md", "wrap": True, "flex": 4},
             *( [_badge(badge, badge_bg)] if badge else [] ),
         ]},
    ]
    bubble: Dict[str, Any] = {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "backgroundColor": HEADER_BG, "paddingAll": "14px", "contents": header_contents},
        "body": {"type": "box", "layout": "vertical", "backgroundColor": BODY_BG, "paddingAll": "14px", "contents": body},
    }
    if footer:
        bubble["footer"] = {"type": "box", "layout": "horizontal", "spacing": "sm", "backgroundColor": BODY_BG,
                            "paddingAll": "10px", "contents": footer}
    return bubble


def _flex(alt: str, contents: Dict[str, Any], quick: Optional[List[str]] = None, size: Optional[str] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"type": "flex", "altText": alt, "contents": contents}
    if size:
        msg["size"] = size
    if quick:
        msg["quickReply"] = quick_reply(quick)
    return msg


# --------------------------------------------------------------------------- #
# /status
# --------------------------------------------------------------------------- #
def status_card(
    *,
    brokers: List[Dict[str, str]],
    relay_ready: bool,
    relay_label: str,
    mode_badge: str,
    kill_active: bool,
    updated: str,
) -> Dict[str, Any]:
    """
    ``brokers`` = [{"name": "KSS", "emoji": "🟢", "line1": "alive · heartbeat 10:41",
    "line2": "บัญชี MARGIN"}]
    """
    is_live = "LIVE" in mode_badge
    badge_bg = KILL_COLOR if kill_active else (LIVE_COLOR if is_live else TEST_COLOR)

    body: List[Dict[str, Any]] = []
    if kill_active:
        body.append({"type": "text", "text": "⛔ KILL-SWITCH ACTIVE — พิมพ์ RESET เพื่อปลด",
                     "color": "#ffffff", "weight": "bold", "size": "sm", "wrap": True,
                     "backgroundColor": KILL_COLOR, "paddingAll": "8px", "cornerRadius": "4px"})
    body.append(_kv("Kill-switch", "🟢 ปกติ" if not kill_active else "🔴 ACTIVE",
                    DOWN if kill_active else UP))
    body.append(_kv("OTP relay", f"{'🟢' if relay_ready else '🔴'} {relay_label}",
                    UP if relay_ready else DOWN))
    for b in brokers:
        body.append({"type": "separator", "margin": "md", "color": "#334155"})
        body.append(_row([
            _cell(f"{b.get('emoji', '⚪')} {b.get('name', '')}", FG, flex=2, weight="bold"),
            _cell(b.get("line1", ""), MUTED, flex=4, align="end"),
        ]))
        if b.get("line2"):
            body.append(_cell(b["line2"], MUTED))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_cell(f"อัปเดต {updated}", MUTED, align="end"))

    # footer: offer /login for any broker that is down
    buttons: List[Dict[str, Any]] = []
    for b in brokers:
        if b.get("emoji") in ("🔴", "⚪"):
            buttons.append(_msg_button(f"🔑 /login {b.get('key', '')}", f"/login {b.get('key', '')}", color="#b45309"))
    buttons.append(_msg_button("📊 /port", "/port", color="#0ea5e9"))

    alt_states = " ".join(f"{b.get('name', '')}{b.get('emoji', '')}" for b in brokers)
    alt = f"Homelab: {alt_states} · relay{'🟢' if relay_ready else '🔴'} · {'LIVE' if is_live else 'TEST'}"
    return _flex(alt, _bubble(title="🛰️ Homelab Status", badge=mode_badge.split(" ")[0], badge_bg=badge_bg,
                              body=body, footer=buttons[:3]), quick=["/port", "/orders", "/status"])


# --------------------------------------------------------------------------- #
# /port
# --------------------------------------------------------------------------- #
def port_card(
    *,
    broker: str,
    account: str,
    total_value: float,
    pnl_value: float,
    pnl_pct: float,
    rows: List[Dict[str, Any]],
    overflow: int,
    snapshot_label: str,
    stale: bool,
    live: bool,
    is_test: bool = False,
) -> Dict[str, Any]:
    pnl_color = UP if pnl_value >= 0 else DOWN
    body: List[Dict[str, Any]] = [
        _kv("มูลค่ารวม", f"{total_value:,.2f}"),
        _kv("P/L วันนี้", f"{pnl_value:+,.2f} ({pnl_pct:+.2f}%)", pnl_color),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _row([
            _cell("หุ้น", MUTED, flex=3, weight="bold"), _cell("จำนวน", MUTED, flex=3, align="end"),
            _cell("ทุน", MUTED, flex=2, align="end"), _cell("ล่าสุด", MUTED, flex=2, align="end"),
            _cell("%P/L", MUTED, flex=2, align="end"),
        ]),
    ]
    for r in rows:
        pc = float(r.get("pnl_pct", 0.0))
        body.append(_row([
            _cell(str(r.get("symbol", "")), FG, flex=3, weight="bold"),
            _cell(f"{int(r.get('volume', 0)):,}", FG, flex=3, align="end"),
            _cell(f"{float(r.get('cost', 0.0)):.2f}", FG, flex=2, align="end"),
            _cell(f"{float(r.get('last', 0.0)):.2f}", FG, flex=2, align="end"),
            _cell(f"{pc:+.2f}", UP if pc >= 0 else DOWN, flex=2, align="end"),
        ]))
    if overflow > 0:
        body.append(_cell(f"…และอีก {overflow} ตัว", MUTED))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    ts_color = WARN if stale else (UP if live else MUTED)
    prefix = "🟢 live " if live else "🕒 snapshot "
    body.append(_cell(f"{prefix}{snapshot_label}" + ("  ⚠️ ข้อมูลเก่า" if stale else ""), ts_color))

    badge = "TEST" if is_test else None
    footer = [_msg_button(f"🔄 /port {broker} sync", f"/port {broker} sync", color="#0ea5e9"),
              _msg_button(f"📋 /orders {broker}", f"/orders {broker}")]
    return _flex(f"📊 {broker} พอร์ต มูลค่า {total_value:,.2f}",
                 _bubble(title=f"📊 {broker.upper()} · {account}", badge=badge, badge_bg=TEST_COLOR,
                         body=body, footer=footer))


# --------------------------------------------------------------------------- #
# /cash
# --------------------------------------------------------------------------- #
def cash_card(*, broker: str, account: str, rows: List[Dict[str, str]], snapshot_label: str, live: bool) -> Dict[str, Any]:
    """``rows`` = [{"label": "เงินสด / Cash balance", "value": "250,000.00", "color": FG?}]"""
    body: List[Dict[str, Any]] = [_kv(r["label"], r["value"], r.get("color", FG)) for r in rows]
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_cell(("🟢 live " if live else "🕒 snapshot ") + snapshot_label, UP if live else MUTED))
    footer = [_msg_button(f"🔄 /cash {broker} sync", f"/cash {broker} sync", color="#0ea5e9")]
    return _flex(f"💰 {broker} เงินคงเหลือ",
                 _bubble(title=f"💰 {broker.upper()} · {account}", body=body, footer=footer))


# --------------------------------------------------------------------------- #
# /orders
# --------------------------------------------------------------------------- #
_STATUS_EMOJI = {
    "open": "⏳", "matched": "✅", "partial": "⏳", "cancelled": "✖", "rejected": "✖", "unknown": "❔",
}


def orders_card(
    *,
    broker: str,
    total: int,
    open_count: int,
    rows: List[Dict[str, Any]],
    snapshot_label: str,
    live: bool,
    show_nego: bool,
) -> Dict[str, Any]:
    """``rows`` = [{"kind": "open", "side": "BUY", "symbol": "PTT", "volume": 1000,
    "price": 34.0, "balance": 1000, "status": "…"}]"""
    body: List[Dict[str, Any]] = []
    if not rows:
        body.append(_cell("ℹ️ ยังไม่มีออเดอร์ในระบบ", MUTED))
    for r in rows:
        kind = str(r.get("kind", "unknown")).lower()
        emoji = _STATUS_EMOJI.get(kind, "❔")
        bal = int(r.get("balance", 0) or 0)
        tail = f"ค้าง {bal:,}" if kind in ("open", "partial") else str(r.get("status", emoji))
        body.append(_row([
            _cell(f"{emoji} {r.get('side', '')} {r.get('symbol', '')}", FG, flex=3, weight="bold"),
            _cell(f"{int(r.get('volume', 0)):,} @{float(r.get('price', 0.0)):.2f}", FG, flex=4, align="end"),
            _cell(tail, MUTED, flex=3, align="end"),
        ]))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_cell(("🟢 live " if live else "🕒 snapshot ") + snapshot_label, UP if live else MUTED))

    footer: List[Dict[str, Any]] = []
    if show_nego and open_count > 0:
        footer.append(_msg_button(f"⚡ /nego {broker}", f"/nego {broker}", color="#b45309"))
    footer.append(_msg_button(f"🔄 /orders {broker} sync", f"/orders {broker} sync", color="#0ea5e9"))
    title = f"📋 {broker.upper()} ออเดอร์วันนี้ ({open_count} ค้าง / {total} ทั้งหมด)"
    return _flex(f"📋 {broker} ออเดอร์ {total} รายการ",
                 _bubble(title=title, body=body, footer=footer))


# --------------------------------------------------------------------------- #
# /nego
# --------------------------------------------------------------------------- #
def nego_card(
    *,
    broker: str,
    results: List[Dict[str, Any]],
    ok: int,
    skipped: int,
    failed: int,
    ts: str,
    is_test: bool,
) -> Dict[str, Any]:
    """``results`` = [{"status": "ok|skip|fail", "order_no", "side", "symbol",
    "old_price", "new_price", "reason"}]"""
    body: List[Dict[str, Any]] = []
    for r in results:
        st = r.get("status")
        sym = r.get("symbol", "")
        side = r.get("side", "")
        no = r.get("order_no", "")
        if st == "ok":
            body.append(_row([
                _cell(f"✅ #{no} {side} {sym}", UP, flex=3, weight="bold"),
                _cell(f"{float(r.get('old_price', 0.0)):.2f} → {float(r.get('new_price', 0.0)):.2f}", UP, flex=4, align="end"),
            ]))
        else:
            emoji = "⏭️" if st == "skip" else "❌"
            body.append(_row([
                _cell(f"{emoji} #{no} {side} {sym}", WARN if st == "skip" else DOWN, flex=3, weight="bold"),
                _cell(str(r.get("reason", "")), MUTED, flex=4, align="end"),
            ]))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_kv("สำเร็จ / ข้าม / ล้มเหลว", f"{ok} · {skipped} · {failed}",
                    UP if failed == 0 else DOWN))
    body.append(_cell(f"🕒 {ts}", MUTED, align="end"))
    footer = [_msg_button(f"📋 /orders {broker} sync", f"/orders {broker} sync")]
    return _flex(f"⚡ ผลต่อราคา {broker}: สำเร็จ {ok} ข้าม {skipped} ล้มเหลว {failed}",
                 _bubble(title=f"⚡ ผลต่อราคา {broker.upper()}", badge="TEST" if is_test else None,
                         badge_bg=TEST_COLOR, body=body, footer=footer))


# --------------------------------------------------------------------------- #
# carousel
# --------------------------------------------------------------------------- #
def carousel(bubbles: List[Dict[str, Any]], alt: str) -> Dict[str, Any]:
    return {"type": "flex", "altText": alt, "contents": {"type": "carousel", "contents": bubbles}}


__all__ = [
    "quick_reply",
    "status_card",
    "port_card",
    "cash_card",
    "orders_card",
    "nego_card",
    "carousel",
]


