"""
LINE slash-command parser (pure — no I/O).

Turns a raw LINE text message such as ``/port kss sync`` into a
:class:`CliCommand`, or a :class:`CliError` when the text is not a usable
command. Following the design spec (`docs/handoff/TASK-line-cli-design.md`):

* syntax: ``/<command> [broker] [target] [flag]``
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
from typing import Dict, List, Optional, Set, Union

#: error catalogue (design §4)
E_UNKNOWN_CMD = "E_UNKNOWN_CMD"
E_BAD_BROKER = "E_BAD_BROKER"
E_BROKER_REQUIRED = "E_BROKER_REQUIRED"
E_BAD_TARGET = "E_BAD_TARGET"


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


ParseResult = Union[CliCommand, CliError]


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
_ALL_BROKERS: Set[str] = {"help", "status", "login", "logout", "port", "cash", "orders"}

#: commands that must carry an explicit broker
_REQUIRE_BROKER: Set[str] = {"login", "logout", "nego"}

#: valid flags
_FLAGS: Set[str] = {"sync", "force"}

_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_ORDER_NO_RE = re.compile(r"^\d{1,12}$")


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


__all__ = [
    "CliCommand",
    "CliError",
    "ParseResult",
    "parse",
    "is_command",
    "suggest_command",
    "COMMAND_ALIASES",
    "BROKER_ALIASES",
    "SUPPORTED_BROKERS",
    "E_UNKNOWN_CMD",
    "E_BAD_BROKER",
    "E_BROKER_REQUIRED",
    "E_BAD_TARGET",
]
