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
PORT_ROWS_PER_BUBBLE = 12


def _port_header_row() -> Dict[str, Any]:
    """RCA-012: the symbol column keeps the largest share so ``DOHOME (S)`` is not clipped."""
    return _row([
        _cell("หุ้น", MUTED, flex=4, weight="bold"), _cell("จำนวน", MUTED, flex=2, align="end"),
        _cell("ทุน", MUTED, flex=2, align="end"), _cell("ล่าสุด", MUTED, flex=2, align="end"),
        _cell("%P/L", MUTED, flex=2, align="end"),
    ])


def _port_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """One holding line. Side tag ``(S)``/``(B)``; unreadable %P/L renders ``—``.

    RCA-012: the symbol cell wraps (``flex=4``) instead of being clipped, so a long
    name plus its side suffix such as ``DOHOME (S)`` stays readable in full.
    """
    ptype = str(r.get("position_type") or "LONG").upper()
    tag = " (S)" if ptype == "SHORT" else (" (B)" if ptype == "BORROWED" else "")
    pnl_pct = r.get("pnl_pct")
    if pnl_pct is None:
        pnl_cell = _cell("—", MUTED, flex=2, align="end")
    else:
        pc = float(pnl_pct)
        pnl_cell = _cell(f"{pc:+.2f}", UP if pc >= 0 else DOWN, flex=2, align="end")
    return _row([
        _cell(f"{r.get('symbol', '')}{tag}", FG, flex=4, weight="bold", wrap=True),
        _cell(f"{int(r.get('volume', 0)):,}", FG, flex=2, align="end"),
        _cell(f"{float(r.get('cost', 0.0)):.2f}", FG, flex=2, align="end"),
        _cell(f"{float(r.get('last', 0.0)):.2f}", FG, flex=2, align="end"),
        pnl_cell,
    ])


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
        summary.extend(_kv(b["symbol"], f"{int(b.get('volume', 0)):,} หุ้น") for b in loans)
    summary.append({"type": "separator", "margin": "md", "color": "#334155"})
    header = _port_header_row()
    badge = "TEST" if is_test else None
    footer = [_msg_button(f"🔄 /port {broker} sync", f"/port {broker} sync", color="#0ea5e9"),
              _msg_button(f"📋 /orders {broker}", f"/orders {broker}")]
    ts_color = WARN if stale else (UP if live else MUTED)
    prefix = "🟢 live " if live else "🕒 snapshot "
    status = _cell(f"{prefix}{snapshot_label}" + ("  ⚠️ ข้อมูลเก่า" if stale else ""), ts_color)

    pages = [rows[i:i + PORT_ROWS_PER_BUBBLE] for i in range(0, len(rows), PORT_ROWS_PER_BUBBLE)] or [[]]
    bubbles: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages):
        if idx == 0:
            body: List[Dict[str, Any]] = list(summary) + [header]
            if not rows:
                body.append(_cell("ℹ️ ยังไม่มีหุ้นในพอร์ต", MUTED))
            body.extend(_port_row(r) for r in page)
            body.append({"type": "separator", "margin": "md", "color": "#334155"})
            body.append(status)
            bubbles.append(_bubble(title=f"📊 {broker.upper()} · {account}", badge=badge,
                                   badge_bg=TEST_COLOR, body=body, footer=footer))
        else:
            body = [header] + [_port_row(r) for r in page]
            bubbles.append(_bubble(title=f"📊 {broker.upper()} · ต่อ {idx + 1}/{len(pages)}", body=body))

    alt = f"📊 {broker} พอร์ต Amount {_money(amount)} ({len(rows)} ตัว)"
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
    return _flex(f"⚡ ต่อราคา #{order_no}: {label}",
                 _bubble(title=f"⚡ Quick Trade #{order_no}",
                         badge="TEST" if is_test else None, badge_bg=TEST_COLOR,
                         body=body, footer=footer))


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
    "negotiate_card",
    "carousel",
]


