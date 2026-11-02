"""
LINE slash-command parser (pure — no I/O).

Turns a raw LINE text message such as ``/port kss sync`` into a
:class:`CliCommand`, or a :class:`CliError` when the text is not a usable
command. Following the design spec (`docs/handoff/TASK-line-cli-design.md`):

* syntax: ``/<command> [broker] [target] [flag]``
* trade syntax (Phase B): ``/<side> [broker[:account]] <symbol> <vol> <price>``
* prefixes: always ``/`` (full-width ``／`` from mobile keyboards accepted)
* case-insensitive, repeated whitespace collapsed
* brokers in this loop: ``kss`` | ``lib`` (+ ``all`` for read/login commands)
* Thai aliases accepted
* unknown command -> nearest suggestion (Levenshtein <= 2)

Nothing here touches the network, DB, settings or the broker drivers — the
module is deliberately dependency-free so it can be unit-tested in isolation.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

#: error catalogue (design §4)
E_UNKNOWN_CMD = "E_UNKNOWN_CMD"
E_BAD_BROKER = "E_BAD_BROKER"
E_BROKER_REQUIRED = "E_BROKER_REQUIRED"
E_BAD_TARGET = "E_BAD_TARGET"
E_BAD_SYMBOL = "E_BAD_SYMBOL"
E_BAD_VOLUME = "E_BAD_VOLUME"
E_BAD_PRICE = "E_BAD_PRICE"
E_BAD_ACCOUNT = "E_BAD_ACCOUNT"
E_MISSING_ARG = "E_MISSING_ARG"


@dataclass(frozen=True)
class CliCommand:
    """A parsed, validated slash command."""

    cmd: str
    broker: Optional[str] = None          # 'kss' | 'lib' | 'all' | None
    target: Optional[str] = None          # SYMBOL or broker order no (nego only)
    flags: Set[str] = field(default_factory=set)

    def has(self, flag: str) -> bool:
        return flag in self.flags


@dataclass(frozen=True)
class CliError:
    """A command-shaped message that cannot be executed."""

    code: str
    message: str
    hint: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)
    quick_reply: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TradeOrder:
    """A parsed new-order command: ``/buy`` ``/sell`` ``/short`` ``/cover``.

    The parser resolves the *default* side→broker routing (master_directive_v2
    §1) and any ``broker[:account]`` override. Business rules — board-lot,
    line-available, side/broker/account compatibility — are the handler's job
    (Phase B guardrails), not the parser's.
    """

    cmd: str                 # canonical side: 'buy' | 'sell' | 'short' | 'cover'
    symbol: str              # upper-cased SET symbol
    volume: int              # positive integer shares (0 if amount_mode == "value")
    price: Optional[float]   # positive number or None (live market price)
    broker: str              # resolved broker: 'kss' | 'lib'
    account: str             # resolved account: 'cash' | 'margin'
    amount_mode: str = "volume"  # 'volume' | 'value'
    target_value: Optional[float] = None  # THB value if amount_mode == 'value'

    @property
    def side_letter(self) -> str:
        """B/S/H/C — matches the Settrade/QuickTrade order-ticket radio value."""
        return _SIDE_LETTER[self.cmd]


@dataclass(frozen=True)
class SblCommand:
    """An SBL inquiry command: ``/sbl [kss] [sync]`` or ``/sbl pool <symbol>``."""

    cmd: str = "sbl"
    subcmd: Optional[str] = None  # None (status/list) or 'pool'
    symbol: Optional[str] = None  # for pool query
    broker: str = "kss"           # SBL is strictly Krungsri MARGIN
    flags: Set[str] = field(default_factory=set)

    def has(self, flag: str) -> bool:
        return flag in self.flags


@dataclass(frozen=True)
class SblBorrowOrder:
    """An SBL stock borrow command: ``/borrow <symbol> <volume>``."""

    cmd: str = "borrow"
    symbol: str = ""
    volume: int = 0
    broker: str = "kss"
    amount_mode: str = "volume"  # 'volume' | 'value'
    target_value: Optional[float] = None


@dataclass(frozen=True)
class SblReturnOrder:
    """An SBL stock return command: ``/return <symbol> [volume|all]``."""

    cmd: str = "return"
    symbol: str = ""
    volume: Optional[int] = None  # None or 0 means 'all'
    broker: str = "kss"


@dataclass(frozen=True)
class SizeCommand:
    """A sizing/budget calculation command: ``/size <symbol>`` (alias /calc)."""

    symbol: str
    cmd: str = "size"


ParseResult = Union[CliCommand, TradeOrder, SblCommand, SblBorrowOrder, SblReturnOrder, SizeCommand, CliError]


# --------------------------------------------------------------------------- #
# Vocabularies
# --------------------------------------------------------------------------- #
#: canonical command -> accepted aliases (lower-cased)
COMMAND_ALIASES: Dict[str, str] = {
    "help": "help", "ช่วย": "help", "คำสั่ง": "help",
    "status": "status", "สถานะ": "status",
    "login": "login", "ล็อกอิน": "login", "เข้าระบบ": "login",
    "logout": "logout", "ออกระบบ": "logout",
    "port": "port", "พอร์ต": "port", "portfolio": "port",
    "cash": "cash", "เงิน": "cash", "วงเงิน": "cash",
    "orders": "orders", "order": "orders", "ออเดอร์": "orders", "คำสั่งค้าง": "orders",
    "nego": "nego", "ต่อราคา": "nego",
    "negotiate": "negotiate", "แก้ราคา": "negotiate",
    # Phase B — new order entry (side → broker routing, override optional)
    "buy": "buy", "ซื้อ": "buy",
    "sell": "sell", "ขาย": "sell",
    "short": "short", "ชอร์ต": "short",
    "cover": "cover", "คัฟเวอร์": "cover",
    # Loop 2 — SBL Intelligence & Command Suite
    "sbl": "sbl", "หุ้นยืม": "sbl",
    "borrow": "borrow", "ยืมหุ้น": "borrow", "ยืม": "borrow",
    "return": "return", "คืนหุ้น": "return", "คืน": "return",
    # Loop 2 — Rich Menu Quick Trade & Emergency Halt
    "quicktrade": "quicktrade", "trade": "quicktrade", "เมนูเทรด": "quicktrade",
    "halt": "halt", "หยุด": "halt",
    # Loop 2 — Sizing & Budget Calculation
    "size": "size", "calc": "size", "คำนวณ": "size",
}

#: canonical broker -> accepted aliases (lower-cased)
BROKER_ALIASES: Dict[str, str] = {
    "kss": "kss", "krungsri": "kss", "trademan": "kss", "กรุงศรี": "kss",
    "lib": "lib", "liberator": "lib", "ลิเบอเรเตอร์": "lib",
    "all": "all", "ทั้งหมด": "all",
}

#: brokers this loop actually supports
SUPPORTED_BROKERS: Set[str] = {"kss", "lib"}

#: commands allowed to target ``all``
_ALL_BROKERS: Set[str] = {"help", "status", "login", "logout", "port", "cash", "orders", "quicktrade", "halt"}

#: commands that must carry an explicit broker
_REQUIRE_BROKER: Set[str] = {"login", "logout", "nego"}

#: valid flags
_FLAGS: Set[str] = {"sync", "force"}

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_ORDER_NO_RE = re.compile(r"^\d{1,12}$")

#: canonical trade sides (Phase B order entry)
_TRADE_COMMANDS: Set[str] = {"buy", "sell", "short", "cover"}
_SBL_COMMANDS: Set[str] = {"sbl", "borrow", "return"}

#: side → (broker, account) default routing (master_directive_v2 §1):
#: ``short``/``cover`` → kss MARGIN · ``buy``/``sell`` → lib CASH.
_DEFAULT_ROUTING: Dict[str, tuple] = {
    "buy": ("lib", "cash"),
    "sell": ("lib", "cash"),
    "short": ("kss", "margin"),
    "cover": ("kss", "margin"),
}

#: canonical broker → default account when an override names only the broker.
_BROKER_DEFAULT_ACCOUNT: Dict[str, str] = {"kss": "margin", "lib": "cash"}

#: account aliases in a ``broker:account`` override.
ACCOUNT_ALIASES: Dict[str, str] = {
    "cash": "cash", "เงินสด": "cash", "เงิน": "cash",
    "margin": "margin", "เครดิต": "margin",
}

#: trade side → order-ticket radio letter (B/S/H/C — order-entry contract).
_SIDE_LETTER: Dict[str, str] = {"buy": "B", "sell": "S", "short": "H", "cover": "C"}

_VOLUME_RE = re.compile(r"^\d+$")
_PRICE_RE = re.compile(r"^\d+(?:\.\d+)?$")
_OTP_RE = re.compile(r"^\d{6}$")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _normalise(text: str) -> str:
    """Full-width slash -> '/', collapse runs of whitespace, strip."""
    normalised = (text or "").replace("\uFF0F", "/")
    return re.sub(r"\s+", " ", normalised).strip()


def is_command(text: str) -> bool:
    """True when the text should be routed to the slash CLI."""
    return _normalise(text).startswith("/")


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def suggest_command(token: str, max_distance: int = 2) -> List[str]:
    """Nearest canonical commands within ``max_distance`` (design §1)."""
    token = (token or "").lower()
    scored = []
    for alias, canonical in COMMAND_ALIASES.items():
        dist = _levenshtein(token, alias)
        if dist <= max_distance:
            scored.append((dist, canonical))
    seen: Set[str] = set()
    out: List[str] = []
    for _, canonical in sorted(scored, key=lambda x: x[0]):
        if canonical not in seen:
            seen.add(canonical)
            out.append(f"/{canonical}")
    return out


def _unknown_command(token: str) -> CliError:
    suggestions = suggest_command(token)
    hint = " · ".join(suggestions) if suggestions else "พิมพ์ /help"
    return CliError(
        code=E_UNKNOWN_CMD,
        message=f'❓ ไม่รู้จักคำสั่ง "/{token}"',
        hint=hint,
        suggestions=suggestions,
        quick_reply=["/help"],
    )


def _bad_broker(token: str) -> CliError:
    return CliError(
        code=E_BAD_BROKER,
        message=f'❓ ไม่รู้จักโบรกเกอร์ "{token}" — loop นี้รองรับ kss, lib',
        hint="kss · lib · all",
        quick_reply=["/status", "/port", "/help"],
    )


def _broker_required(cmd: str) -> CliError:
    return CliError(
        code=E_BROKER_REQUIRED,
        message=f"เลือกโบรกเกอร์สำหรับ /{cmd}:",
        hint="kss · lib",
        quick_reply=[f"/{cmd} kss", f"/{cmd} lib"],
    )


def _trade_missing(side: str) -> CliError:
    return CliError(
        code=E_MISSING_ARG,
        message=f"รูปแบบคำสั่ง /{side} ยังไม่ครบ: /{side} <symbol> <vol> <price>",
        hint=f"ตัวอย่าง: /{side} PTT 100 12.50 · broker override: /{side} kss:margin PTT 100 12.50",
        quick_reply=[f"/help {side}"],
    )


def _trade_extra(side: str, token: str) -> CliError:
    return CliError(
        code=E_UNKNOWN_CMD,
        message=f'❓ พารามิเตอร์เกินของ /{side}: "{token}"',
        hint=f"รูปแบบ: /{side} <symbol> <vol> <price>",
        quick_reply=[f"/help {side}"],
    )


def _bad_symbol(side: str, token: str) -> CliError:
    return CliError(
        code=E_BAD_SYMBOL,
        message=f'❓ สัญลักษณ์หุ้น "{token}" ของ /{side} ไม่ถูกต้อง',
        hint="ตัวอย่าง: PTT · KBANK · ADVANC",
        quick_reply=[f"/help {side}"],
    )


def _bad_volume(side: str, token: str) -> CliError:
    return CliError(
        code=E_BAD_VOLUME,
        message=f'❓ จำนวนหุ้น "{token}" ของ /{side} ไม่ถูกต้อง — ต้องเป็นจำนวนเต็มบวก',
        hint="ตัวอย่าง: /buy PTT 100 12.50",
        quick_reply=[f"/help {side}"],
    )


def _bad_price(side: str, token: str) -> CliError:
    return CliError(
        code=E_BAD_PRICE,
        message=f'❓ ราคา "{token}" ของ /{side} ไม่ถูกต้อง — ต้องเป็นเลขบวก',
        hint="ตัวอย่าง: /buy PTT 100 12.50",
        quick_reply=[f"/help {side}"],
    )


def _bad_account(side: str, token: str) -> CliError:
    return CliError(
        code=E_BAD_ACCOUNT,
        message=f'❓ บัญชี "{token}" ของ /{side} ไม่รู้จัก — ใช้ cash หรือ margin',
        hint="ตัวอย่าง: /buy kss:margin PTT 100 12.50",
        quick_reply=[f"/help {side}"],
    )


def _resolve_override(side: str, token: str):
    """Resolve a ``broker[:account]`` override to ``(broker, account)``.

    Only ``kss`` / ``lib`` are trading brokers (``all`` is read-only); an
    account-less override falls back to that broker's default account. Returns a
    :class:`CliError` on a bad broker or account.
    """
    if ":" in token:
        left, right = token.split(":", 1)
        broker = BROKER_ALIASES.get(left.lower())
        if broker is None or broker not in SUPPORTED_BROKERS:
            return CliError(
                code=E_BAD_BROKER,
                message=f'❓ โบรกเกอร์ "{left}" ไม่รู้จัก — override ใช้ kss หรือ lib',
                hint="ตัวอย่าง: /buy kss:margin PTT 100 12.50",
                quick_reply=[f"/help {side}"],
            )
        account = ACCOUNT_ALIASES.get(right.lower())
        if account is None:
            return _bad_account(side, right)
        return broker, account
    broker = BROKER_ALIASES.get(token.lower())
    if broker is None or broker not in SUPPORTED_BROKERS:
        return CliError(
            code=E_BAD_BROKER,
            message=f'❓ โบรกเกอร์ "{token}" ไม่รู้จัก — override ใช้ kss หรือ lib',
            hint="ตัวอย่าง: /buy kss:margin PTT 100 12.50",
            quick_reply=[f"/help {side}"],
        )
    return broker, _BROKER_DEFAULT_ACCOUNT[broker]


_VALUE_SUFFIX_RE = re.compile(
    r"^([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([kKmM])?\s*([bB฿]|baht|บาท)?$"
)


def _parse_amount(token: str) -> Optional[Tuple[str, float]]:
    """Parse amount token into (mode, value).

    Returns ("volume", int_shares) or ("value", float_thb), or None if invalid.
    """
    cleaned = token.replace(",", "").strip()
    if cleaned.startswith("฿"):
        rem = cleaned[1:].strip()
        cleaned = rem if re.search(r"[kKmMbB฿บาท]", rem) else rem + "฿"
    elif cleaned.startswith(("b", "B")) and len(cleaned) > 1 and cleaned[1].isdigit():
        rem = cleaned[1:].strip()
        cleaned = rem if re.search(r"[kKmMbB฿บาท]", rem) else rem + "b"
    # Pure digits without suffix = share volume
    if _VOLUME_RE.match(cleaned):
        vol = int(cleaned)
        return ("volume", float(vol)) if vol > 0 else None

    # Check for unit suffix: k, m, b, ฿, baht, บาท
    m = _VALUE_SUFFIX_RE.match(cleaned)
    if not m:
        return None
    num_str, mult, curr = m.group(1), (m.group(2) or "").lower(), (m.group(3) or "").lower()
    if not mult and not curr:
        return None
    try:
        base_num = float(num_str.replace(",", ""))
    except ValueError:
        return None
    if base_num <= 0:
        return None

    if mult == "k":
        base_num *= 1_000.0
    elif mult == "m":
        base_num *= 1_000_000.0

    return ("value", base_num)


def _normalize_trade_tokens(rest: List[str]) -> List[str]:
    """Combines detached currency units into the amount token.

    e.g. ['PTT', '50,000', 'บาท', '35.00'] -> ['PTT', '50,000บาท', '35.00']
    """
    if len(rest) < 2:
        return rest
    out = []
    i = 0
    while i < len(rest):
        if (
            i + 1 < len(rest)
            and rest[i + 1].lower() in ("baht", "บาท", "b", "฿")
            and re.match(r"^[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?:[kKmM])?$", rest[i])
        ):
            out.append(rest[i] + rest[i + 1])
            i += 2
        else:
            out.append(rest[i])
            i += 1
    return out


def _has_override(tok: str) -> bool:
    target = tok.split(":", 1)[0].lower()
    return target in SUPPORTED_BROKERS or target in BROKER_ALIASES


def _parse_trade(side: str, rest: List[str]) -> ParseResult:
    """Parse ``/<side> [broker[:account]] <symbol> <amount> [price]``.

    Amount can be shares (e.g. 100, 1000) or THB value (e.g. 50k, 50000b).
    Price is optional; if omitted, the system resolves from live market quote.
    """
    rest = _normalize_trade_tokens(rest)
    if len(rest) == 2:
        # /<side> <symbol> <amount>
        broker, account = _DEFAULT_ROUTING[side]
        symbol_tok, amount_tok = rest[0], rest[1]
        price_tok = None
    elif len(rest) == 3:
        if _has_override(rest[0]):
            # /<side> <override> <symbol> <amount>
            resolved = _resolve_override(side, rest[0])
            if isinstance(resolved, CliError):
                return resolved
            broker, account = resolved
            symbol_tok, amount_tok = rest[1], rest[2]
            price_tok = None
        else:
            # /<side> <symbol> <amount> <price>
            broker, account = _DEFAULT_ROUTING[side]
            symbol_tok, amount_tok, price_tok = rest[0], rest[1], rest[2]
    elif len(rest) == 4:
        # /<side> <override> <symbol> <amount> <price>
        resolved = _resolve_override(side, rest[0])
        if isinstance(resolved, CliError):
            return resolved
        broker, account = resolved
        symbol_tok, amount_tok, price_tok = rest[1], rest[2], rest[3]
    elif len(rest) < 2:
        return _trade_missing(side)
    else:
        return _trade_extra(side, rest[4])

    symbol = symbol_tok.upper()
    if not _SYMBOL_RE.match(symbol):
        return _bad_symbol(side, symbol_tok)

    amt_parsed = None
    if amount_tok.lower() == "all" and side in ("short", "cover"):
        mode, val = "all", 0.0
    else:
        amt_parsed = _parse_amount(amount_tok)
        if amt_parsed is None:
            return _bad_volume(side, amount_tok)
        mode, val = amt_parsed

    if price_tok is not None:
        if not _PRICE_RE.match(price_tok):
            return _bad_price(side, price_tok)
        price = float(price_tok)
        if price <= 0:
            return _bad_price(side, price_tok)
    else:
        # Price omitted: allowed for both value-based and share-count orders (calculated from live quote / nego pricer)
        price = None

    vol = int(val) if mode == "volume" else 0
    target_val = val if mode == "value" else None

    return TradeOrder(
        cmd=side,
        symbol=symbol,
        volume=vol,
        price=price,
        broker=broker,
        account=account,
        amount_mode=mode,
        target_value=target_val,
    )


def is_otp(text: str) -> bool:
    """True when the message is exactly 6 digits — the LINE OTP-relay contract."""
    return bool(_OTP_RE.match(_normalise(text)))


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse(text: str) -> Optional[ParseResult]:
    """
    Parse a LINE text message.

    Returns ``None`` when the text is not a slash command (so the caller leaves
    it for the legacy matchers), otherwise a :class:`CliCommand` or a
    :class:`CliError`.
    """
    if not is_command(text):
        return None

    body = _normalise(text)[1:].strip()
    if not body:
        return CliError(
            code=E_UNKNOWN_CMD, message="❓ คำสั่งว่างเปล่า",
            hint="พิมพ์ /help", quick_reply=["/help"],
        )

    tokens = body.split(" ")
    cmd_token = tokens[0].lower()
    canonical = COMMAND_ALIASES.get(cmd_token)
    if canonical is None:
        return _unknown_command(cmd_token)

    rest = tokens[1:]

    # /help takes an optional COMMAND name, never a broker.
    if canonical == "help":
        target = rest[0].lower() if rest else None
        return CliCommand(cmd="help", target=target)

    # Phase B new-order commands have a dedicated grammar (no broker/flags loop).
    if canonical in _TRADE_COMMANDS:
        return _parse_trade(canonical, rest)

    # Loop 2 SBL commands
    if canonical == "sbl":
        return _parse_sbl(rest)
    if canonical == "borrow":
        return _parse_borrow(rest)
    if canonical == "return":
        return _parse_return(rest)

    # Loop 2 Sizing command
    if canonical == "size":
        return _parse_size(rest)

    broker: Optional[str] = None
    target: Optional[str] = None
    flags: Set[str] = set()

    for token in rest:
        low = token.lower()
        if low in _FLAGS:
            flags.add(low)
            continue
        if low in BROKER_ALIASES and broker is None:
            broker = BROKER_ALIASES[low]
            continue
        if canonical in ("nego", "negotiate") and target is None:
            candidate = token.upper()
            if _ORDER_NO_RE.match(candidate) or _SYMBOL_RE.match(candidate):
                target = candidate
                continue
            return CliError(
                code=E_BAD_TARGET,
                message=f'❓ เป้าหมาย "{token}" ของ /{cmd_token} ไม่ถูกต้อง — ต้องเป็นชื่อหุ้นหรือเลขออเดอร์',
                hint=("ตัวอย่าง: /negotiate 11008198" if canonical == "negotiate"
                      else "ตัวอย่าง: /nego kss PTT · /nego lib 12345"),
                quick_reply=[f"/help {canonical}"],
            )
        # a bare token in the broker position of a broker-taking command
        if broker is None:
            return _bad_broker(token)
        return CliError(
            code=E_UNKNOWN_CMD,
            message=f'❓ ไม่รู้จักพารามิเตอร์ "{token}" ของ /{canonical}',
            hint="พิมพ์ /help",
            quick_reply=["/help"],
        )

    if broker and broker != "all" and broker not in SUPPORTED_BROKERS:
        return _bad_broker(broker)

    if canonical in _REQUIRE_BROKER and broker is None:
        return _broker_required(canonical)

    # read/default broker = 'all'
    if broker is None and canonical in _ALL_BROKERS:
        broker = "all"

    # 'force' is only meaningful for login; 'sync' only for reads.
    if canonical != "login":
        flags.discard("force")
    if canonical not in {"port", "cash", "orders"}:
        flags.discard("sync")

    return CliCommand(cmd=canonical, broker=broker, target=target, flags=flags)


def _parse_sbl(rest: List[str]) -> ParseResult:
    """Parse ``/sbl [kss] [sync]`` or ``/sbl pool <symbol>``."""
    flags: Set[str] = set()
    subcmd: Optional[str] = None
    symbol: Optional[str] = None
    for tok in rest:
        low = tok.lower()
        if low in ("sync",):
            flags.add("sync")
        elif low in ("--force-browser", "force-browser", "force"):
            flags.add("force_browser")
        elif low in ("pool", "คลัง", "สต็อก"):
            subcmd = "pool"
        elif low in ("status", "สถานะ"):
            pass
        elif low in BROKER_ALIASES:
            b = BROKER_ALIASES[low]
            if b == "lib":
                return CliError(
                    code=E_BAD_BROKER,
                    message="❌ บริการ SBL (ยืม/คืนหุ้น) รองรับเฉพาะโบรกเกอร์ Krungsri (บัญชี Credit Balance Margin 3024959) เท่านั้น",
                    hint="ตัวอย่าง: /sbl · /sbl pool PTT",
                    quick_reply=["/sbl", "/sbl pool PTT"],
                )
            # 'kss' or 'all' is accepted for SBL query
        elif _SYMBOL_RE.match(tok.upper()):
            symbol = tok.upper()
        else:
            return CliError(
                code=E_UNKNOWN_CMD,
                message=f'❓ พารามิเตอร์ "{tok}" ของ /sbl ไม่ถูกต้อง',
                hint="ตัวอย่าง: /sbl · /sbl sync · /sbl pool PTT",
                quick_reply=["/sbl", "/sbl sync"],
            )
    if symbol and subcmd is None and not flags:
        subcmd = "pool"
    if subcmd == "pool" and not symbol:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /sbl pool ต้องการระบุชื่อหุ้น",
            hint="ตัวอย่าง: /sbl pool PTT",
            quick_reply=["/sbl"],
        )
    return SblCommand(cmd="sbl", subcmd=subcmd, symbol=symbol, broker="kss", flags=flags)


def _parse_borrow(rest: List[str]) -> ParseResult:
    """Parse ``/borrow [broker] <symbol> <volume|amount>``."""
    if not rest:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /borrow ต้องการระบุ: ชื่อหุ้น และ จำนวนหุ้น/เงิน ที่ต้องการยืม",
            hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
            quick_reply=["/sbl"],
        )
    b = BROKER_ALIASES.get(rest[0].lower())
    if b == "lib":
        return CliError(
            code=E_BAD_BROKER,
            message="❌ บริการ SBL (ยืม/คืนหุ้น) รองรับเฉพาะโบรกเกอร์ Krungsri (บัญชี Credit Balance Margin 3024959) เท่านั้น",
            hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
            quick_reply=["/sbl"],
        )
    elif b == "kss":
        rest = rest[1:]

    rest = _normalize_trade_tokens(rest)
    if not rest:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /borrow ต้องการระบุ: ชื่อหุ้น และ จำนวนหุ้น/เงิน ที่ต้องการยืม",
            hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
            quick_reply=["/sbl"],
        )
    if len(rest) == 1:
        sym_tok = rest[0].upper()
        if not _SYMBOL_RE.match(sym_tok):
            return CliError(
                code=E_BAD_SYMBOL,
                message=f'❓ ชื่อหุ้น "{rest[0]}" ไม่ถูกต้อง',
                hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
                quick_reply=["/sbl"],
            )
        return SblBorrowOrder(
            cmd="borrow",
            symbol=sym_tok,
            volume=0,
            broker="kss",
            amount_mode="value",
            target_value=10000.0,
        )

    sym_tok, amount_tok = rest[0].upper(), rest[1].strip()
    if not _SYMBOL_RE.match(sym_tok):
        return CliError(
            code=E_BAD_SYMBOL,
            message=f'❓ ชื่อหุ้น "{rest[0]}" ไม่ถูกต้อง',
            hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
            quick_reply=["/sbl"],
        )
    amt_parsed = _parse_amount(amount_tok)
    if amt_parsed is None:
        return CliError(
            code=E_BAD_VOLUME,
            message=f'❓ จำนวนหุ้นหรือจำนวนเงิน "{rest[1]}" ไม่ถูกต้อง',
            hint="ตัวอย่าง: /borrow PTT 1000 หรือ /borrow PTT 10k",
            quick_reply=["/sbl"],
        )
    mode, val = amt_parsed
    vol = int(val) if mode == "volume" else 0
    target_val = val if mode == "value" else None
    return SblBorrowOrder(
        cmd="borrow",
        symbol=sym_tok,
        volume=vol,
        broker="kss",
        amount_mode=mode,
        target_value=target_val,
    )


def _parse_return(rest: List[str]) -> ParseResult:
    """Parse ``/return [broker] <symbol> [volume|all]``."""
    if len(rest) < 1:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /return ต้องการระบุ: ชื่อหุ้น และ จำนวนหุ้นที่ต้องการคืน (หรือ all)",
            hint="ตัวอย่าง: /return PTT 1000 หรือ /return PTT all",
            quick_reply=["/sbl"],
        )
    b = BROKER_ALIASES.get(rest[0].lower())
    if b == "lib":
        return CliError(
            code=E_BAD_BROKER,
            message="❌ บริการ SBL (ยืม/คืนหุ้น) รองรับเฉพาะโบรกเกอร์ Krungsri (บัญชี Credit Balance Margin 3024959) เท่านั้น",
            hint="ตัวอย่าง: /return PTT all",
            quick_reply=["/sbl"],
        )
    elif b == "kss":
        rest = rest[1:]

    if len(rest) < 1:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /return ต้องการระบุ: ชื่อหุ้น และ จำนวนหุ้นที่ต้องการคืน (หรือ all)",
            hint="ตัวอย่าง: /return PTT 1000 หรือ /return PTT all",
            quick_reply=["/sbl"],
        )
    sym_tok = rest[0].upper()
    if not _SYMBOL_RE.match(sym_tok):
        return CliError(
            code=E_BAD_SYMBOL,
            message=f'❓ ชื่อหุ้น "{rest[0]}" ไม่ถูกต้อง',
            hint="ตัวอย่าง: /return PTT all",
            quick_reply=["/sbl"],
        )
    vol = None
    if len(rest) >= 2:
        v_tok = rest[1].replace(",", "").strip().lower()
        if v_tok not in ("all", "ทั้งหมด"):
            if not _VOLUME_RE.match(v_tok) or int(v_tok) <= 0:
                return CliError(
                    code=E_BAD_VOLUME,
                    message=f'❓ จำนวนหุ้นคืน "{rest[1]}" ไม่ถูกต้อง — ใช้จำนวนเต็มบวก หรือ all',
                    hint="ตัวอย่าง: /return PTT 1000 หรือ /return PTT all",
                    quick_reply=["/sbl"],
                )
            vol = int(v_tok)
    return SblReturnOrder(cmd="return", symbol=sym_tok, volume=vol, broker="kss")


def _parse_size(rest: List[str]) -> ParseResult:
    """Parse ``/size <symbol>`` (alias /calc)."""
    if not rest:
        return CliError(
            code=E_MISSING_ARG,
            message="❓ คำสั่ง /size ต้องการระบุชื่อหุ้น",
            hint="ตัวอย่าง: /size PTT · /calc BCPG",
            quick_reply=["/help size", "/size PTT"],
        )
    sym_tok = rest[0].upper()
    if not _SYMBOL_RE.match(sym_tok):
        return _bad_symbol("size", rest[0])
    return SizeCommand(cmd="size", symbol=sym_tok)


__all__ = [
    "CliCommand",
    "CliError",
    "TradeOrder",
    "SblCommand",
    "SblBorrowOrder",
    "SblReturnOrder",
    "SizeCommand",
    "ParseResult",
    "parse",
    "is_command",
    "is_otp",
    "suggest_command",
    "COMMAND_ALIASES",
    "BROKER_ALIASES",
    "ACCOUNT_ALIASES",
    "SUPPORTED_BROKERS",
    "E_UNKNOWN_CMD",
    "E_BAD_BROKER",
    "E_BROKER_REQUIRED",
    "E_BAD_TARGET",
    "E_BAD_SYMBOL",
    "E_BAD_VOLUME",
    "E_BAD_PRICE",
    "E_BAD_ACCOUNT",
    "E_MISSING_ARG",
]

