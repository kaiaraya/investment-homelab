#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PIN guard CLI — inspect or clear the PIN-attempt quarantine.

The guard is *fail-closed by design*: after one broker PIN rejection nothing else is sent
to that broker until a human confirms the PIN at the broker and clears it here. Run this
only after the PIN was verified (or reset) on the broker side.

Usage::

    .venv/bin/python scripts/pin_guard.py status
    .venv/bin/python scripts/pin_guard.py reset kss --reason "Krungsri 1.2 reset, .env PIN verified"
    .venv/bin/python scripts/pin_guard.py classify "Your pin is suspended"

Broker keys match the DB: ``KRUNGSRI`` (Settrade Streaming / QuickTrade) and
``LIBERATOR``; the short forms ``kss``/``lib`` are accepted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import pin_guard  # noqa: E402

_ALIASES = {
    "kss": "KRUNGSRI", "krungsri": "KRUNGSRI", "streaming": "KRUNGSRI", "quicktrade": "KRUNGSRI",
    "lib": "LIBERATOR", "liberator": "LIBERATOR",
}


def _broker(raw: str) -> str:
    return _ALIASES.get(str(raw or "").strip().lower(), str(raw or "").strip().upper())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PIN guard state / reset")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show the guard state for every broker")

    r = sub.add_parser("reset", help="clear a quarantine after the PIN was verified")
    r.add_argument("broker")
    r.add_argument("--reason", default="", help="why it is safe to submit again")
    r.add_argument("--actor", default="human", help="who cleared it (default: human)")

    c = sub.add_parser("classify", help="dry-check how a broker message would be classified")
    c.add_argument("text")

    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(pin_guard.status(), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "reset":
        out = pin_guard.reset(_broker(args.broker), reason=args.reason, actor=args.actor)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    code = pin_guard.classify_pin_error(args.text)
    print(json.dumps({"text": args.text, "classify": code,
                      "is_pin_error": code is not None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
