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


def _cell(text: str, color: str = FG, flex: int = 1, align: str = "start",
          weight: str = "regular", wrap: bool = False, size: str = "xs") -> Dict[str, Any]:
    cell: Dict[str, Any] = {"type": "text", "text": text, "color": color, "size": size,
                            "flex": flex, "align": align, "weight": weight}
    if wrap:
        cell["wrap"] = True          # RCA-012: let a long symbol wrap instead of clip
    return cell


def _money(value: Optional[float]) -> str:
    """Format a THB amount — ``None`` renders ``—`` (Anti-Mock, RCA-013).

    A totals cell the page did not expose is never printed as a fabricated ``0.00``.
    """
    return "—" if value is None else f"{value:,.2f}"


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
            _cell(f"{b.get('emoji', '⚪')} {b.get('name', '')}", FG, flex=3, weight="bold"),
            _cell(b.get("line1", ""), MUTED, flex=3, align="end"),
        ]))
        if b.get("line2"):
            body.append(_cell(b["line2"], MUTED))
        if b.get("line3"):
            body.append(_cell(b["line3"], MUTED))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_cell(f"อัปเดต {updated}", MUTED, align="end"))

    # footer: offer /login for any broker that is down
    buttons: List[Dict[str, Any]] = []
    for b in brokers:
        if b.get("emoji") in ("🔴", "⚪", "🟡"):
            buttons.append(_msg_button(f"🔑 /login {b.get('key', '')}", f"/login {b.get('key', '')}", color="#b45309"))
    buttons.append(_msg_button("📊 /port", "/port", color="#0ea5e9"))

    alt_states = " ".join(f"{b.get('name', '')}{b.get('emoji', '')}" for b in brokers)
    alt = f"Homelab: {alt_states} · relay{'🟢' if relay_ready else '🔴'} · {'LIVE' if is_live else 'TEST'}"
    return _flex(alt, _bubble(title="🛰️ Homelab Status", badge=mode_badge.split(" ")[0], badge_bg=badge_bg,
                              body=body, footer=buttons[:3]), quick=["/port", "/orders", "/status"])


# --------------------------------------------------------------------------- #
# /port
# --------------------------------------------------------------------------- #
PORT_ROWS_PER_BUBBLE = 12
_BROKER_LABEL = {"kss": "KSS", "lib": "LIB"}


def _port_header_row() -> Dict[str, Any]:
    """RCA-012: the symbol column keeps the largest share so ``DOHOME (S)`` is not clipped."""
    return _row([
        _cell("หุ้น", MUTED, flex=4, weight="bold"), _cell("จำนวน", MUTED, flex=2, align="end"),
        _cell("ทุน", MUTED, flex=2, align="end"), _cell("ล่าสุด", MUTED, flex=2, align="end"),
        _cell("%P/L", MUTED, flex=2, align="end"),
    ])


def _port_row(r: Dict[str, Any], broker: Optional[str] = None, actionable: bool = True) -> Dict[str, Any]:
    """One holding line with optional broker badge and optional actionable negotiation buttons."""
    ptype = str(r.get("position_type") or "LONG").upper()
    tag = " (S)" if ptype == "SHORT" else (" (B)" if ptype == "BORROWED" else "")
    pnl_pct = r.get("pnl_pct")
    if pnl_pct is None:
        pnl_cell = _cell("—", MUTED, flex=2, align="end")
    else:
        pc = float(pnl_pct)
        pnl_cell = _cell(f"{pc:+.2f}%", UP if pc >= 0 else DOWN, flex=2, align="end")

    sym = str(r.get("symbol", "")).upper()
    vol = int(r.get("volume", 0) or 0)
    has_explicit_broker = bool(r.get("broker"))
    b_code = str(r.get("broker") or broker or ("kss" if ptype in ("SHORT", "BORROWED") else "lib")).lower()
    broker_badge = _BROKER_LABEL.get(b_code, b_code.upper())
    sym_label = f"[{broker_badge}] {sym}{tag}" if has_explicit_broker else f"{sym}{tag}"

    row_box = _row([
        _cell(sym_label, FG, flex=4, weight="bold", wrap=True),
        _cell(f"{vol:,}", FG, flex=2, align="end"),
        _cell(f"{float(r.get('cost', 0.0)):.2f}", FG, flex=2, align="end"),
        _cell(f"{float(r.get('last', 0.0)):.2f}", FG, flex=2, align="end"),
        pnl_cell,
    ])
    if not actionable:
        return row_box

    buttons: List[Dict[str, Any]] = []
    if ptype == "SHORT":
        buttons.append(_msg_button("🔵 Cover (ต่อราคา)", f"/cover {b_code} {sym} {vol}", color="#1e40af"))
    elif ptype == "BORROWED":
        buttons.append(_msg_button("🟣 Short (ต่อราคา)", f"/short {b_code} {sym} {vol}", color="#581c87"))
        buttons.append(_msg_button("🔄 คืนหุ้น", f"/return {sym} all", color="#334155"))
    else:
        buttons.append(_msg_button("🔴 ขาย (ต่อราคา)", f"/sell {b_code} {sym} {vol}", color="#991b1b"))

    return {
        "type": "box",
        "layout": "vertical",
        "margin": "md",
        "spacing": "xs",
        "contents": [
            row_box,
            {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "margin": "xs",
                "contents": buttons,
            },
        ],
    }


def _borrowed_row(b: Dict[str, Any], broker: Optional[str] = None, actionable: bool = True) -> Dict[str, Any]:
    """One borrowed SBL lot with broker badge and Short + Return buttons."""
    sym = str(b.get("symbol", "")).upper()
    vol = int(b.get("volume", 0) or 0)
    has_explicit_broker = bool(b.get("broker"))
    b_code = str(b.get("broker") or broker or "kss").lower()
    broker_badge = _BROKER_LABEL.get(b_code, b_code.upper())
    sym_label = f"[{broker_badge}] {sym}" if has_explicit_broker else sym

    if not actionable:
        return _kv(sym_label, f"{vol:,} หุ้น")

    buttons = [
        _msg_button("🟣 Short (ต่อราคา)", f"/short {b_code} {sym} {vol}", color="#581c87"),
        _msg_button("🔄 คืนหุ้น", f"/return {sym} all", color="#334155"),
    ]
    return {
        "type": "box",
        "layout": "vertical",
        "margin": "sm",
        "spacing": "xs",
        "contents": [
            _kv(sym_label, f"{vol:,} หุ้น"),
            {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "margin": "xs",
                "contents": buttons,
            },
        ],
    }


def port_card(
    *,
    broker: str,
    account: str,
    amount: Optional[float],
    pnl_value: float,
    pnl_pct: float,
    rows: List[Dict[str, Any]],
    snapshot_label: str,
    stale: bool,
    live: bool,
    borrowed: Optional[List[Dict[str, Any]]] = None,
    is_test: bool = False,
    rows_per_bubble: int = PORT_ROWS_PER_BUBBLE,
    actionable: bool = True,
) -> Dict[str, Any]:
    """``rows`` = normalised holdings **minus the (B) loans** (``handlers._split_borrowed``).

    RCA-013 final: the header mirrors the app's own labels — ``Amount`` (cost basis) then
    ``Unrealized P/L``. ``Market Value`` is gone (D1): the app counts (B) in it while the
    page's totals row does not, and the loan is returned at its own volume anyway.
    ``borrowed`` (``[{"symbol", "volume"}]``) renders as a ``หุ้นยืมคงเหลือ (B)`` section
    under the P/L line — omitted entirely when empty (D2/D3). A figure the page/data did
    not provide renders ``—``, never a fabricated ``0.00``.

    A long book is paginated ``PORT_ROWS_PER_BUBBLE`` rows per bubble into a LINE
    carousel (RCA-002 follow-up) — every row is shown, no "และอีก N ตัว" teaser.
    """
    pnl_color = UP if pnl_value >= 0 else DOWN
    rows = rows or []
    loans = borrowed or []
    summary: List[Dict[str, Any]] = [
        _kv("Amount", _money(amount)),
        _kv("Unrealized P/L", f"{pnl_value:+,.2f} ({pnl_pct:+.2f}%)", pnl_color),
    ]
    if loans:
        summary.append(_cell("หุ้นยืมคงเหลือ (B)", MUTED, weight="bold"))
        for b in loans:
            sym = str(b.get("symbol", "")).upper()
            vol = int(b.get("volume", 0) or 0)
            has_explicit_broker = bool(b.get("broker"))
            b_code = str(b.get("broker") or broker or "kss").lower()
            broker_badge = _BROKER_LABEL.get(b_code, b_code.upper())
            sym_label = f"[{broker_badge}] {sym}" if has_explicit_broker else sym
            summary.append(_kv(sym_label, f"{vol:,} หุ้น"))
            if actionable:
                buttons = [
                    _msg_button("🟣 Short (ต่อราคา)", f"/short {b_code} {sym} {vol}", color="#581c87"),
                    _msg_button("🔄 คืนหุ้น", f"/return {sym} all", color="#334155"),
                ]
                summary.append({
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xs",
                    "contents": [{
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "contents": buttons,
                    }],
                })
    summary.append({"type": "separator", "margin": "md", "color": "#334155"})
    header = _port_header_row()
    badge = "TEST" if is_test else None
    footer = [_msg_button(f"🔄 /port {broker} sync", f"/port {broker} sync", color="#0ea5e9"),
              _msg_button(f"📋 /orders {broker}", f"/orders {broker}")]
    ts_color = WARN if stale else (UP if live else MUTED)
    prefix = "🟢 live " if live else "🕒 snapshot "
    status = _cell(f"{prefix}{snapshot_label}" + ("  ⚠️ ข้อมูลเก่า" if stale else ""), ts_color)

    pages = [rows[i:i + rows_per_bubble] for i in range(0, len(rows), rows_per_bubble)] or [[]]
    bubbles: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages):
        if idx == 0:
            body: List[Dict[str, Any]] = list(summary) + [header]
            if not rows:
                body.append(_cell("ℹ️ ยังไม่มีหุ้นในพอร์ต", MUTED))
            for r in page:
                pbox = _port_row(r, broker=r.get("broker") or broker, actionable=actionable)
                body.append(pbox)
            body.append({"type": "separator", "margin": "md", "color": "#334155"})
            body.append(status)
            bubbles.append(_bubble(title=f"📊 {broker.upper()} · {account}", badge=badge,
                                   badge_bg=TEST_COLOR, body=body, footer=footer))
        else:
            body = [header]
            for r in page:
                pbox = _port_row(r, broker=r.get("broker") or broker, actionable=actionable)
                body.append(pbox)
            bubbles.append(_bubble(title=f"📊 {broker.upper()} · ต่อ {idx + 1}/{len(pages)}", body=body))

    alt = f"📊 {broker} พอร์ต Amount {_money(amount)} ({len(rows)} ตัว)"
    if len(bubbles) == 1:
        return _flex(alt, bubbles[0])
    return carousel(bubbles, alt)


def portfolio_multi_broker_card(
    *,
    brokers_data: Optional[List[Dict[str, Any]]] = None,
    rows: Optional[List[Dict[str, Any]]] = None,
    borrowed: Optional[List[Dict[str, Any]]] = None,
    amount: Optional[float] = None,
    pnl_value: float = 0.0,
    pnl_pct: float = 0.0,
    snapshot_label: str = "",
    stale: bool = False,
    live: bool = False,
    is_test: bool = False,
    rows_per_bubble: int = PORT_ROWS_PER_BUBBLE,
) -> Dict[str, Any]:
    """Interactive multi-broker portfolio card (LIB Cash vs KSS Margin).

    Sends context `broker` down to `_port_row` and `_borrowed_row`.
    """
    badge = "TEST" if is_test else None
    ts_color = WARN if stale else (UP if live else MUTED)
    prefix = "🟢 live " if live else "🕒 snapshot "
    status = _cell(f"{prefix}{snapshot_label}" + ("  ⚠️ ข้อมูลเก่า" if stale else ""), ts_color)

    if brokers_data:
        bubbles: List[Dict[str, Any]] = []
        for bdata in brokers_data:
            b_name = str(bdata.get("broker", "kss")).lower()
            b_label = _BROKER_LABEL.get(b_name, b_name.upper())
            b_acct = bdata.get("account", "MARGIN" if b_name == "kss" else "CASH")
            b_amount = bdata.get("amount")
            b_pnl_val = float(bdata.get("pnl_value", 0.0) or 0.0)
            b_pnl_pct = float(bdata.get("pnl_pct", 0.0) or 0.0)
            b_rows = bdata.get("rows", [])
            b_borrowed = bdata.get("borrowed", [])
            b_actionable = bool(bdata.get("actionable", True) and b_name in ("kss", "lib"))
            if b_actionable:
                b_footer = [_msg_button(f"🔄 /port {b_name} sync", f"/port {b_name} sync", color="#0ea5e9"),
                            _msg_button(f"📋 /orders {b_name}", f"/orders {b_name}")]
            else:
                b_footer = None

            pnl_col = UP if b_pnl_val >= 0 else DOWN
            b_summary: List[Dict[str, Any]] = [
                _kv("Amount", _money(b_amount)),
                _kv("Unrealized P/L", f"{b_pnl_val:+,.2f} ({b_pnl_pct:+.2f}%)", pnl_col),
            ]
            if b_borrowed:
                b_summary.append(_cell("หุ้นยืมคงเหลือ (B)", MUTED, weight="bold"))
                b_summary.extend(_borrowed_row(b, broker=b.get("broker") or b_name, actionable=b_actionable) for b in b_borrowed)
            b_summary.append({"type": "separator", "margin": "md", "color": "#334155"})
            header = _port_header_row()

            pages = [b_rows[i:i + rows_per_bubble] for i in range(0, len(b_rows), rows_per_bubble)] or [[]]
            for idx, page in enumerate(pages):
                if idx == 0:
                    body: List[Dict[str, Any]] = list(b_summary) + [header]
                    if not b_rows:
                        body.append(_cell("ℹ️ ยังไม่มีหุ้นในพอร์ต", MUTED))
                    body.extend(_port_row(r, broker=r.get("broker") or b_name, actionable=b_actionable) for r in page)
                    body.append({"type": "separator", "margin": "md", "color": "#334155"})
                    body.append(status)
                    bubbles.append(_bubble(title=f"📊 {b_label} · {b_acct}", badge=badge,
                                           badge_bg=TEST_COLOR, body=body, footer=b_footer))
                else:
                    body = [header] + [_port_row(r, broker=r.get("broker") or b_name, actionable=b_actionable) for r in page]
                    bubbles.append(_bubble(title=f"📊 {b_label} · ต่อ {idx + 1}/{len(pages)}", body=body))

        alt = f"📊 Multi-Broker Portfolio ({len(brokers_data)} โบรกเกอร์)"
        if len(bubbles) == 1:
            return _flex(alt, bubbles[0])
        return carousel(bubbles, alt)

    # Combined rows representation
    rows = rows or []
    loans = borrowed or []
    pnl_color = UP if pnl_value >= 0 else DOWN
    summary: List[Dict[str, Any]] = [
        _kv("Amount", _money(amount)),
        _kv("Unrealized P/L", f"{pnl_value:+,.2f} ({pnl_pct:+.2f}%)", pnl_color),
    ]
    if loans:
        summary.append(_cell("หุ้นยืมคงเหลือ (B)", MUTED, weight="bold"))
        summary.extend(_borrowed_row(b, broker=b.get("broker") or "kss") for b in loans)
    summary.append({"type": "separator", "margin": "md", "color": "#334155"})
    header = _port_header_row()
    footer = [_msg_button("🔄 /port all sync", "/port all sync", color="#0ea5e9"),
              _msg_button("📋 /orders all", "/orders all")]

    pages = [rows[i:i + rows_per_bubble] for i in range(0, len(rows), rows_per_bubble)] or [[]]
    bubbles = []
    for idx, page in enumerate(pages):
        if idx == 0:
            body = list(summary) + [header]
            if not rows:
                body.append(_cell("ℹ️ ยังไม่มีหุ้นในพอร์ต", MUTED))
            body.extend(_port_row(r, broker=r.get("broker")) for r in page)
            body.append({"type": "separator", "margin": "md", "color": "#334155"})
            body.append(status)
            bubbles.append(_bubble(title="📊 MULTI-BROKER PORTFOLIO", badge=badge,
                                   badge_bg=TEST_COLOR, body=body, footer=footer))
        else:
            body = [header] + [_port_row(r, broker=r.get("broker")) for r in page]
            bubbles.append(_bubble(title=f"📊 MULTI-BROKER · ต่อ {idx + 1}/{len(pages)}", body=body))

    alt = f"📊 พอร์ต Multi-Broker Amount {_money(amount)} ({len(rows)} ตัว)"
    if len(bubbles) == 1:
        return _flex(alt, bubbles[0])
    return carousel(bubbles, alt)


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
# "อ่านไม่ได้" / session expired (RCA-009, RCA-006b)
# --------------------------------------------------------------------------- #
UNAVAILABLE_HINT = "อ่านไม่ได้ / session หมดอายุ"


def unavailable_card(*, broker: str, login_cmd: str) -> Dict[str, Any]:
    """Honest read-failure card — never claims 🟢 live and never shows fabricated numbers."""
    line = f"⚠️ {UNAVAILABLE_HINT} — {login_cmd}"
    body: List[Dict[str, Any]] = [
        _cell(line, WARN, weight="bold"),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell("ตัวเลขจะกลับมาแสดงหลังเข้าสู่ระบบใหม่", MUTED),
    ]
    footer = [_msg_button(f"🔐 {login_cmd}", login_cmd, color="#0ea5e9")]
    return _flex(f"⚠️ {broker} อ่านข้อมูลไม่ได้",
                 _bubble(title=f"⚠️ {broker.upper()} · อ่านไม่ได้", body=body, footer=footer))


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
        # CLI-RCA-004: two lines per order — the symbol gets its own line in bold `md` so a long
        # ticker is never clipped on a phone screen; volume/price + status sit on line two.
        body.append({
            "type": "box", "layout": "vertical", "margin": "sm", "spacing": "xs",
            "contents": [
                _cell(f"{emoji} {r.get('side', '')} {r.get('symbol', '')}", FG,
                      weight="bold", size="md", wrap=True),
                _row([
                    _cell(f"{int(r.get('volume', 0)):,} @{float(r.get('price', 0.0)):.2f}", FG, flex=3),
                    _cell(tail, MUTED, flex=2, align="end"),
                ]),
            ],
        })
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
    dry_run: bool = False,
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

    badge = "DRY-RUN" if dry_run else ("TEST" if is_test else None)
    badge_bg = WARN if dry_run else TEST_COLOR

    return _flex(f"⚡ ผลต่อราคา {broker}: สำเร็จ {ok} ข้าม {skipped} ล้มเหลว {failed}",
                 _bubble(title=f"⚡ ผลต่อราคา {broker.upper()}", badge=badge,
                         badge_bg=badge_bg, body=body, footer=footer))


# --------------------------------------------------------------------------- #
# /negotiate (Quick Trade in-place price amendment)
# --------------------------------------------------------------------------- #
#: outcome -> (emoji, label, colour)
_NEGOTIATE_OUTCOME: Dict[str, tuple] = {
    "OK": ("✅", "ต่อราคาสำเร็จ", UP),
    "NO_CHANGE": ("⏭️", "อยู่ที่เป้าหมายแล้ว", WARN),
    "UPTICK_VIOLATION": ("⛔", "ผิดกฎ Uptick (SHORT)", DOWN),
    "NO_QUOTE": ("🚫", "อ่านราคาตลาดไม่ได้", DOWN),
    "UNSUPPORTED_SIDE": ("❓", "ไม่รู้จักประเภทคำสั่ง", DOWN),
}


def _px(value: Optional[float]) -> str:
    """Price cell — ``None`` renders ``—`` (Anti-Mock: never a fabricated price)."""
    return "—" if value is None else f"{float(value):.2f}"


def negotiate_card(
    *,
    order_no: str,
    symbol: str,
    side: str,
    outcome: str,
    current_price: Optional[float],
    target_price: Optional[float],
    volume: Optional[int],
    reason: str,
    submitted: Optional[bool],
    ts: str,
    is_test: bool,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """One-order result card for ``/negotiate`` (Quick Trade in-place amendment).

    ``submitted`` — ``True`` the broker accepted the amendment, ``False`` it was
    staged only (TEST / DRY-RUN), ``None`` nothing was sent (Anti-Mock: never imply
    a submission that did not happen).
    """
    emoji, label, colour = _NEGOTIATE_OUTCOME.get(outcome, ("ℹ️", outcome or "ไม่ทราบผล", MUTED))
    if submitted is True:
        send_text, send_colour = "ส่งเข้าตลาดแล้ว", UP
    elif submitted is False:
        send_text, send_colour = "จัดเตรียมไว้ (TEST/DRY-RUN)", WARN
    else:
        send_text, send_colour = "—", MUTED

    body: List[Dict[str, Any]] = [
        _kv("ออเดอร์", f"#{order_no} {side} {symbol}"),
        _kv("ราคาเดิม → เป้าหมาย", f"{_px(current_price)} → {_px(target_price)}"),
        _kv("จำนวน", f"{int(volume):,}" if volume is not None else "—"),
        _kv("สถานะการส่ง", send_text, send_colour),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell(f"{emoji} {label}", colour, weight="bold", wrap=True),
    ]
    if reason:
        body.append(_cell(reason[:160], MUTED, wrap=True))
    body.append(_cell(f"🕒 {ts}", MUTED, align="end"))
    footer = [
        _msg_button(f"⚡ /negotiate {order_no}", f"/negotiate {order_no}", color="#b45309"),
        _msg_button("📋 /orders kss sync", "/orders kss sync"),
    ]

    badge = "DRY-RUN" if dry_run else ("TEST" if is_test else None)
    badge_bg = WARN if dry_run else TEST_COLOR

    return _flex(f"⚡ ต่อราคา #{order_no}: {label}",
                 _bubble(title=f"⚡ Quick Trade #{order_no}",
                         badge=badge, badge_bg=badge_bg,
                         body=body, footer=footer))


# --------------------------------------------------------------------------- #
# Phase B — order confirmation + receipt cards (B.5)
# --------------------------------------------------------------------------- #
_BROKER_LABEL = {"kss": "KSS", "lib": "LIB"}
_SIDE_LABEL = {"buy": "BUY", "sell": "SELL", "short": "SHORT", "cover": "COVER"}
#: side → colour (buy/cover = green, sell/short = red).
_SIDE_COLOR = {"buy": UP, "sell": DOWN, "short": DOWN, "cover": UP}


def _postback_button(label: str, data: str, display_text: str, color: str = "#334155") -> Dict[str, Any]:
    return {
        "type": "button", "style": "primary", "color": color, "height": "sm", "flex": 1,
        "action": {"type": "postback", "label": label, "data": data, "displayText": display_text},
    }


def trade_confirmation_card(
    *,
    draft_id: str,
    cmd: str,
    symbol: str,
    volume: int,
    price: float,
    broker: str,
    account: str,
    account_no: Optional[str],
    total_thb: float,
    ttl_seconds: int,
    budget_thb: Optional[float] = None,
    ref_market_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Human-in-the-loop confirm card for a drafted Phase-B order (nothing submitted).

    The two footer buttons carry the opaque ``draft_id`` in their postback payload;
    the colour of the title badge follows the side (green BUY/COVER, red SELL/SHORT).
    """
    side_label = _SIDE_LABEL.get((cmd or "").lower(), (cmd or "").upper())
    side_color = _SIDE_COLOR.get((cmd or "").lower(), FG)
    broker_label = _BROKER_LABEL.get((broker or "").lower(), (broker or "").upper())
    account_label = "MARGIN" if (account or "").lower() == "margin" else "CASH"

    body: List[Dict[str, Any]] = [
        _kv("หุ้น", symbol),
        _kv("คำสั่ง", side_label, side_color),
    ]
    if budget_thb is not None:
        body.append(_kv("งบประมาณที่ตั้ง", f"฿{float(budget_thb):,.2f}"))
        body.append(_kv("ราคาอ้างอิงตลาด", f"฿{float(ref_market_price or price):.2f}"))
        body.append(_kv("จำนวนคำนวณ", f"{int(volume):,} หุ้น (Board Lot)"))
        body.append(_kv("มูลค่ารวม", f"฿{float(total_thb):,.2f}"))
    else:
        body.append(_kv("จำนวน", f"{int(volume):,} หุ้น"))
        body.append(_kv("ราคา", f"฿{float(price):.2f}"))
        body.append(_kv("มูลค่า", f"฿{float(total_thb):,.2f}"))

    body.extend([
        _kv("บัญชี", f"{broker_label} · {account_label}" + (f" {account_no}" if account_no else "")),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell(f"⏱️ การ์ดหมดอายุใน {int(ttl_seconds) // 60} นาที — ราคา/วงเงินอาจเปลี่ยน", MUTED, wrap=True),
    ])

    confirm_data = f"action=trade_draft_confirm&draft_id={draft_id}"
    cancel_data = f"action=trade_draft_cancel&draft_id={draft_id}"
    footer = [
        _postback_button("✅ ยืนยัน", confirm_data,
                         f"✅ ยืนยันคำสั่ง {side_label} {symbol} {int(volume):,} @ ฿{float(price):.2f}", UP),
        _postback_button("❌ ยกเลิก", cancel_data, f"❌ ยกเลิกคำสั่ง {side_label} {symbol}", DOWN),
    ]

    return _flex(
        f"ยืนยันคำสั่ง {side_label} {symbol} {int(volume):,} @ ฿{float(price):.2f}",
        _bubble(title=f"🧾 ยืนยันคำสั่ง {side_label} {symbol}", badge=side_label,
                badge_bg=side_color, body=body, footer=footer),
    )


def trade_receipt_card(
    *,
    draft_id: str,
    outcome: str,
    cmd: Optional[str] = None,
    symbol: Optional[str] = None,
    volume: Optional[int] = None,
    price: Optional[float] = None,
    broker: Optional[str] = None,
    account: Optional[str] = None,
    account_no: Optional[str] = None,
) -> Dict[str, Any]:
    """Receipt after a draft postback — confirm hands off to the executor, cancel drops it."""
    confirmed = outcome == "confirmed"
    side_label = _SIDE_LABEL.get((cmd or "").lower(), (cmd or "").upper()) if cmd else None
    broker_label = _BROKER_LABEL.get((broker or "").lower(), (broker or "").upper()) if broker else None

    if confirmed:
        head, head_color = "✅ ยืนยันคำสั่งแล้ว", UP
        detail = "ส่งต่อให้ executor ดำเนินการ — กำลังส่งคำสั่งไปยังโบรกเกอร์"
        badge = "CONFIRMED"
    else:
        head, head_color = "❌ ยกเลิกคำสั่งแล้ว", DOWN
        detail = "draft ถูกลบออกแล้ว — ไม่มีการส่งคำสั่ง"
        badge = "CANCELLED"

    body: List[Dict[str, Any]] = [
        _cell(head, head_color, weight="bold"),
        _kv("draft_id", draft_id),
    ]
    if symbol:
        body.append(_kv("หุ้น", symbol))
    if side_label:
        body.append(_kv("คำสั่ง", side_label, _SIDE_COLOR.get((cmd or "").lower(), FG)))
    if volume is not None:
        body.append(_kv("จำนวน", f"{int(volume):,} หุ้น"))
    if price is not None:
        body.append(_kv("ราคา", f"฿{float(price):.2f}"))
    if broker_label:
        account_label = "MARGIN" if (account or "").lower() == "margin" else "CASH"
        body.append(_kv("บัญชี", f"{broker_label} · {account_label}" + (f" {account_no}" if account_no else "")))
    body.append({"type": "separator", "margin": "md", "color": "#334155"})
    body.append(_cell(detail, MUTED, wrap=True))

    return _flex(
        f"{head} (draft {draft_id})",
        _bubble(title=f"🧾 ใบรับคำสั่ง {draft_id}", badge=badge, badge_bg=head_color, body=body),
    )


# --------------------------------------------------------------------------- #
# SBL Cards (Loop 2)
# --------------------------------------------------------------------------- #
def sbl_status_card(lots: List[Dict[str, Any]], asof_time: str) -> Dict[str, Any]:
    """Displays active borrowed lots on Krungsri MARGIN 3024959."""
    if not lots:
        body = [
            _cell("ไม่มีรายการหุ้นยืม SBL คงค้าง", MUTED),
            _cell("บัญชี Krungsri MARGIN (3024959) พร้อมใช้งาน", UP),
            {"type": "separator", "margin": "md", "color": "#334155"},
            _cell(f"อัปเดตเมื่อ {asof_time}", MUTED),
        ]
        return _flex(
            "สถานะหุ้นยืม SBL: ไม่มีหุ้นยืมค้าง",
            _bubble(title="📦 หุ้นยืม SBL คงค้าง (KSS)", badge="SBL", badge_bg="#6366f1", body=body),
            quick=["/sbl pool PTT", "/sbl sync", "/port kss"],
        )

    rows: List[Dict[str, Any]] = [
        _row([
            _cell("หุ้น", MUTED, flex=2, weight="bold"),
            _cell("คงเหลือ", MUTED, flex=2, align="end", weight="bold"),
            _cell("ดอกเบี้ย", MUTED, flex=2, align="end", weight="bold"),
        ]),
        {"type": "separator", "margin": "xs", "color": "#334155"},
    ]
    for lot in lots:
        sym = str(lot.get("symbol", "-"))
        qty = int(lot.get("remaining_qty", 0) or 0)
        fee = float(lot.get("borrow_fee_rate", 3.5) or 3.5)
        xd = lot.get("ex_dividend_date")
        row_cells = [
            _cell(sym, FG, flex=2, weight="bold"),
            _cell(f"{qty:,}", FG, flex=2, align="end"),
            _cell(f"{fee:.2f}%", WARN, flex=2, align="end"),
        ]
        rows.append(_row(row_cells))
        if xd:
            rows.append(_cell(f"⚠️ เตือน XD: {xd}", DOWN, size="xxs"))

    rows.append({"type": "separator", "margin": "md", "color": "#334155"})
    rows.append(_cell(f"อัปเดตเมื่อ {asof_time} · บัญชี MARGIN 3024959", MUTED))

    return _flex(
        f"สถานะหุ้นยืม SBL ({len(lots)} รายการ)",
        _bubble(title=f"📦 หุ้นยืม SBL คงค้าง ({len(lots)} รายการ)", badge="SBL", badge_bg="#6366f1", body=rows),
        quick=["/sbl sync", "/port kss", "/help return"],
    )


def sbl_pool_card(
    symbol: str,
    available_qty: int,
    fee_rate: float = 3.50,
    status_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Displays available inventory for a symbol in Krungsri TradeMan SBL pool."""
    if available_qty > 0:
        avail_text = f"{available_qty:,} หุ้น"
        avail_color = UP
    elif status_message:
        avail_text = "ยังไม่มีข้อมูล — /sbl sync ก่อน"
        avail_color = MUTED
    else:
        avail_text = "ไม่มีในคลัง"
        avail_color = DOWN
    body = [
        _kv("หุ้น", symbol),
        _kv("จำนวนในคลัง", avail_text, avail_color),
        _kv("อัตราดอกเบี้ยยืม", f"{fee_rate:.2f}% ต่อปี", WARN),
        _kv("โบรกเกอร์", "Krungsri TradeMan (MARGIN)"),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell("💡 สั่งยืมด้วยคำสั่ง /borrow หรือกดปุ่มด้านล่าง", MUTED, wrap=True),
    ]
    quick = [f"/borrow {symbol} 100", f"/borrow {symbol} 1000"] if available_qty > 0 else (
        ["/sbl sync", f"/sbl pool {symbol}"] if status_message else ["/sbl"]
    )
    return _flex(
        f"คลังหุ้นยืม SBL: {symbol} มี {avail_text}",
        _bubble(title=f"🔍 คลังหุ้นยืม SBL ({symbol})", badge="POOL", badge_bg="#6366f1", body=body),
        quick=quick,
    )


def sbl_borrow_confirm_card(
    *,
    draft_id: str,
    symbol: str,
    volume: int,
    fee_rate: float = 3.50,
    xd_warning: Optional[str] = None,
    budget_thb: Optional[float] = None,
    last_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Confirmation card for SBL stock borrow."""
    body = [
        _kv("หุ้น", symbol),
        _kv("จำนวนขอยืม", f"{volume:,} หุ้น"),
    ]
    if budget_thb is not None:
        body.append(_kv("งบประมาณ", f"฿{float(budget_thb):,.2f}"))
    if last_price is not None:
        try:
            last_price = float(last_price)
        except (ValueError, TypeError):
            last_price = None
    if last_price is not None and last_price > 0:
        est_val = volume * last_price
        est_fee_day = (est_val * (fee_rate / 100.0)) / 365.0
        body.append(_kv("มูลค่าหุ้นที่ยืม", f"฿{est_val:,.2f} (@{last_price:.2f})"))
        body.append(_kv("อัตราดอกเบี้ย", f"{fee_rate:.2f}% ต่อปี (~฿{est_fee_day:.2f}/วัน)", WARN))
    else:
        body.append(_kv("อัตราดอกเบี้ย", f"{fee_rate:.2f}% ต่อปี", WARN))
    body.append(_kv("บัญชี", "Krungsri MARGIN 3024959"))
    if xd_warning:
        body.append(_cell(f"⚠️ {xd_warning}", DOWN, wrap=True))
    body.append({"type": "separator", "margin": "md", "color": "#334155"},)
    body.append(_cell("⏱️ คำขอยืมผ่านระบบ SBL Krungsri — กรุณากดยืนยัน", MUTED, wrap=True))

    confirm_data = f"action=sbl_borrow_confirm&draft_id={draft_id}"
    cancel_data = f"action=sbl_borrow_cancel&draft_id={draft_id}"
    footer = [
        _postback_button("✅ ยืนยันยืม", confirm_data, f"✅ ยืนยันขอยืมหุ้น {symbol} {volume:,} หุ้น", UP),
        _postback_button("❌ ยกเลิก", cancel_data, f"❌ ยกเลิกขอยืมหุ้น {symbol}", DOWN),
    ]
    return _flex(
        f"ยืนยันขอยืมหุ้น SBL {symbol} {volume:,} หุ้น",
        _bubble(title=f"📦 ยืนยันขอยืมหุ้น SBL ({symbol})", badge="BORROW", badge_bg="#6366f1", body=body, footer=footer),
    )


def sbl_return_confirm_card(
    *, draft_id: str, symbol: str, volume: int, days_held: int = 0, accrued_fee: float = 0.0
) -> Dict[str, Any]:
    """Confirmation card for SBL stock return."""
    body = [
        _kv("หุ้น", symbol),
        _kv("จำนวนที่คืน", f"{volume:,} หุ้น"),
        _kv("ระยะเวลาที่ยืม", f"{days_held} วัน"),
        _kv("ดอกเบี้ยสะสมโดยประมาณ", f"฿{accrued_fee:,.2f}"),
        _kv("บัญชี", "Krungsri MARGIN 3024959"),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell("💡 คืนหุ้นเพื่อหยุดการคิดดอกเบี้ยยืมรายวัน", MUTED, wrap=True),
    ]
    confirm_data = f"action=sbl_return_confirm&draft_id={draft_id}"
    cancel_data = f"action=sbl_return_cancel&draft_id={draft_id}"
    footer = [
        _postback_button("✅ ยืนยันคืน", confirm_data, f"✅ ยืนยันคืนหุ้น {symbol} {volume:,} หุ้น", UP),
        _postback_button("❌ ยกเลิก", cancel_data, f"❌ ยกเลิกคืนหุ้น {symbol}", DOWN),
    ]
    return _flex(
        f"ยืนยันคืนหุ้น SBL {symbol} {volume:,} หุ้น",
        _bubble(title=f"📦 ยืนยันคืนหุ้น SBL ({symbol})", badge="RETURN", badge_bg="#6366f1", body=body, footer=footer),
    )


def quick_trade_selector_card() -> Dict[str, Any]:
    """Interactive trade side selector card for Rich Menu Quick Trade button."""
    body = [
        _cell("เลือกประเภทคำสั่งซื้อขายที่ต้องการส่ง:", FG, weight="bold"),
        _cell("• ฝั่งซื้อ/ขายปกติ ส่งผ่าน Liberator (CASH)", MUTED, size="xxs"),
        _cell("• ฝั่งชอร์ต/คัฟเวอร์ ส่งผ่าน Krungsri (MARGIN)", MUTED, size="xxs"),
        {"type": "separator", "margin": "md", "color": "#334155"},
        {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                _msg_button("🟢 ซื้อหุ้น (BUY · LIB CASH)", "/buy PTT 50k", color="#166534"),
                _msg_button("🔴 ขายหุ้น (SELL · LIB CASH)", "/sell PTT 1000 35.0", color="#991b1b"),
                # SHORT/COVER require a price argument; a bare ``/short PTT 1000``
                # returns E_MISSING_ARG and the tap does nothing. Value mode (``50k``)
                # is the one form that parses without a hand-typed price.
                _msg_button("🟣 ชอร์ตหุ้น (SHORT · KSS MARGIN)", "/short PTT 50k", color="#581c87"),
                _msg_button("🔵 ปิดชอร์ต (COVER · KSS MARGIN)", "/cover PTT 50k", color="#1e40af"),
            ],
        },
    ]
    return _flex(
        "⚡ เลือกประเภทคำสั่ง Quick Trade",
        _bubble(title="⚡ Quick Trade Studio", badge="TRADE", badge_bg="#3b82f6", body=body),
        quick=["/buy PTT 50k", "/sell PTT 1000", "/sbl", "/port all sync"],
    )


# --------------------------------------------------------------------------- #
# carousel
# --------------------------------------------------------------------------- #
def carousel(bubbles: List[Dict[str, Any]], alt: str) -> Dict[str, Any]:
    return {"type": "flex", "altText": alt, "contents": {"type": "carousel", "contents": bubbles}}


# --------------------------------------------------------------------------- #
# /nego menu (ต่อราคา — N3 postback flow)
# --------------------------------------------------------------------------- #
def nego_menu_card(*, orders: List[Dict[str, Any]], title: Optional[str] = None) -> Dict[str, Any]:
    """Carousel of unmatched open orders across both brokers; each bubble carries
    the 🎯 match / 🪤 lure mode buttons whose postback payloads identify the order."""
    bubbles: List[Dict[str, Any]] = []
    for o in orders:
        broker = str(o.get("broker", "")).lower()
        broker_label = _BROKER_LABEL.get(broker, broker.upper())
        side = str(o.get("side", "")).upper()
        side_color = _SIDE_COLOR.get(side.lower(), FG)
        order_no = str(o.get("order_no", ""))
        mode_match = f"action=nego_mode&broker={broker}&order_no={order_no}&mode=match"
        mode_lure = f"action=nego_mode&broker={broker}&order_no={order_no}&mode=lure"

        body: List[Dict[str, Any]] = [
            _kv("ออเดอร์", f"#{order_no}"),
            _kv("ราคาเดิม", f"฿{float(o.get('price', 0.0) or 0.0):.2f}"),
            _kv("ค้าง", f"{int(o.get('balance', 0) or 0):,} / {int(o.get('volume', 0) or 0):,} หุ้น"),
        ]
        if side == "SHORT":
            body.append(_cell("🪤 lure — ต่อท้ายคิวที่ราคาฝั่งตัวเอง (Short ต่อราคาแบบล่อเท่านั้น)", MUTED, size="xxs", wrap=True))
            footer = [
                _postback_button("🪤 ล่อ", mode_lure, f"🪤 ต่อราคา {side} {o.get('symbol','')} แบบ lure", WARN),
            ]
        else:
            body.extend([
                _cell("🎯 match — ข้าม spread ชน best offer/bid ทันที", MUTED, size="xxs", wrap=True),
                _cell("🪤 lure — ต่อท้ายคิวที่ราคาฝั่งตัวเอง (ไม่ match)", MUTED, size="xxs", wrap=True),
            ])
            footer = [
                _postback_button("🎯 Match", mode_match, f"🎯 ต่อราคา {side} {o.get('symbol','')} แบบ match", UP),
                _postback_button("🪤 ล่อ", mode_lure, f"🪤 ต่อราคา {side} {o.get('symbol','')} แบบ lure", WARN),
            ]
        bubbles.append(_bubble(
            title=f"{side} {o.get('symbol','')}",
            badge=f"{broker_label}",
            badge_bg=side_color,
            body=body, footer=footer,
        ))

    alt = title or f"⚡ ต่อราคา — {len(orders)} ออเดอร์ค้าง"
    return carousel(bubbles, alt)


def nego_empty_card(*, broker: str) -> Dict[str, Any]:
    """Single bubble indicating no open orders for a specific broker."""
    broker_label = _BROKER_LABEL.get(broker.lower(), broker.upper())
    bubble = _bubble(
        title=f"⚡ ต่อราคา {broker_label}",
        badge=broker_label,
        badge_bg="#64748b",
        body=[
            _cell(f"ไม่มีออเดอร์ค้างใน {broker_label} ขณะนี้", MUTED, align="center", size="sm"),
            _cell("คำสั่งจับคู่ครบแล้ว หรือไม่มีคำสั่งเปิดรออยู่", MUTED, align="center", size="xxs"),
        ],
    )
    return _flex(f"⚡ ต่อราคา {broker_label} — ไม่มีออเดอร์ค้าง", bubble)


def nego_draft_card(
    *,
    draft_id: str,
    symbol: str,
    side: str,
    order_no: str,
    broker_label: str,
    old_price: float,
    new_price: float,
    mode_label: str,
    ttl_seconds: int,
) -> Dict[str, Any]:
    """Draft confirm card for one price amendment (nothing submitted yet)."""
    side_color = _SIDE_COLOR.get(side.lower(), FG)
    body: List[Dict[str, Any]] = [
        _kv("หุ้น", symbol),
        _kv("คำสั่ง", side, side_color),
        _kv("ออเดอร์", f"#{order_no}"),
        _kv("โหมด", mode_label),
        _kv("ราคาเดิม", f"฿{float(old_price):.2f}"),
        _kv("ราคาใหม่", f"฿{float(new_price):.2f}", UP),
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell(f"⏱️ การ์ดหมดอายุใน {int(ttl_seconds) // 60} นาที — ราคาอาจเปลี่ยน", MUTED, wrap=True),
    ]
    confirm_data = f"action=nego_confirm&draft_id={draft_id}"
    cancel_data = f"action=nego_cancel&draft_id={draft_id}"
    footer = [
        _postback_button("✅ ยืนยัน", confirm_data,
                         f"✅ ยืนยันต่อราคา {side} {symbol} → ฿{float(new_price):.2f}", UP),
        _postback_button("❌ ยกเลิก", cancel_data, f"❌ ยกเลิกต่อราคา {side} {symbol}", DOWN),
    ]
    return _flex(
        f"ยืนยันต่อราคา {side} {symbol} ฿{float(old_price):.2f} → ฿{float(new_price):.2f}",
        _bubble(title=f"🧾 ต่อราคา {symbol}", badge=f"{broker_label} · {mode_label}",
                badge_bg=side_color, body=body, footer=footer),
    )


def size_calc_card(
    *,
    symbol: str,
    price: float,
    price_source: str = "quote",
    tiers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Flex Card for /size <sym> calculation results.

    tiers = [
        {"budget_label": "50k", "budget": 50000.0, "shares": 1400, "actual_cost": 48300.0},
        ...
    ]
    """
    body: List[Dict[str, Any]] = [
        _kv("หุ้น", symbol),
        _kv("ราคาอ้างอิง", f"฿{float(price):.2f}", UP),
        _kv("แหล่งราคา", price_source),
        {"type": "separator", "margin": "md", "color": "#334155"},
    ]
    quick_replies: List[str] = []
    for t in tiers:
        b_lbl = t.get("budget_label", "")
        shares = int(t.get("shares", 0))
        cost = float(t.get("actual_cost", 0.0))
        body.append(
            _kv(f"งบ {b_lbl}", f"{shares:,} หุ้น (฿{cost:,.2f})")
        )
        quick_replies.append(f"/buy {symbol} {b_lbl}")

    body.extend([
        {"type": "separator", "margin": "md", "color": "#334155"},
        _cell("💡 ปัดเศษลงตาม Board Lot (100 หุ้น) · กดปุ่มด้านล่างเพื่อส่งคำสั่งซื้อ", MUTED, wrap=True),
    ])

    footer_buttons = [
        _msg_button(f"ซื้อ {t.get('budget_label')}", f"/buy {symbol} {t.get('budget_label')}")
        for t in tiers
    ]
    footer = _footer(footer_buttons) if footer_buttons else None

    return _flex(
        f"คำนวณขนาดซื้อ {symbol} @ ฿{float(price):.2f}",
        _bubble(
            title=f"🧮 คำนวณขนาด {symbol}",
            badge=f"฿{float(price):.2f}",
            badge_bg="#2563EB",
            body=body,
            footer=footer.get("contents") if footer else None,
        ),
        quick=quick_replies,
    )


__all__ = [
    "quick_reply",
    "status_card",
    "port_card",
    "cash_card",
    "orders_card",
    "nego_card",
    "negotiate_card",
    "trade_confirmation_card",
    "trade_receipt_card",
    "sbl_status_card",
    "sbl_pool_card",
    "sbl_borrow_confirm_card",
    "sbl_return_confirm_card",
    "quick_trade_selector_card",
    "nego_menu_card",
    "nego_draft_card",
    "size_calc_card",
    "carousel",
]


