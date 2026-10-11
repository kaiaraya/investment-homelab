"""
Feature Matrix — Single Source of Truth (SSOT) for the /console Pillar × Broker view.
=====================================================================================
One machine-readable table that the Operations Cockpit renders and the admin API serves.
Edit ONLY this file to change what the matrix shows (no HTML edits needed).

Axes
----
* Rows  = Pillars (P1 Session … P7 Agentic)
* Cols  = Brokers (vertical-agnostic; each broker is independent — Broker Knowledge Isolation)

Status vocabulary (per cell)
----------------------------
  live      : 🟢 verified end-to-end against the LIVE broker / real path
  sandbox   : 🧪 verified only in simulator / sandbox
  pending   : ⏳ implemented but not yet live-verified
  disabled  : ⛔ feature intentionally OFF for now (e.g. P4/P6/P7 — "ปิดไว้ก่อน", 2026-10-10)
  na        : ➖ not applicable to this broker

Anti-Mock: a cell is "live" ONLY when a real live test was performed — never assume.
This file holds *declared* status; it is a documentation SSOT, not a live probe.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

# ─── Status vocabulary + presentation metadata (SSOT) ───────────────────────────
STATUS_LIVE = "live"
STATUS_SANDBOX = "sandbox"
STATUS_PENDING = "pending"
STATUS_DISABLED = "disabled"
STATUS_NA = "na"

STATUS_META: Dict[str, Dict[str, str]] = {
    STATUS_LIVE: {"label": "Live-tested", "icon": "🟢", "color": "#34d399"},
    STATUS_SANDBOX: {"label": "Sandbox", "icon": "🧪", "color": "#60a5fa"},
    STATUS_PENDING: {"label": "Pending", "icon": "⏳", "color": "#fbbf24"},
    STATUS_DISABLED: {"label": "Disabled", "icon": "⛔", "color": "#94a3b8"},
    STATUS_NA: {"label": "N/A", "icon": "➖", "color": "#475569"},
}

# ─── Horizontal axis: Brokers ───────────────────────────────────────────────────
BROKERS: List[Dict[str, Any]] = [
    {"key": "KRUNGSRI", "name": "Krungsri TradeMan", "in_use": True},
    {"key": "LIBERATOR", "name": "Liberator WebTrade", "in_use": True},
    {"key": "CLICK2WIN", "name": "Settrade Click2Win", "in_use": False},
    {"key": "SETTRADE_OPENAPI", "name": "Settrade Open API", "in_use": False},
]

# ─── Vertical axis: Pillars (rows) ──────────────────────────────────────────────
FEATURE_MATRIX: List[Dict[str, Any]] = [
    {
        "key": "P1_SESSION",
        "pillar": "P1",
        "name": "Session — Login + OTP",
        "notes": "Krungsri login + LINE OTP relay (requirement #1: ทำงานจริง)",
        "cells": {
            "KRUNGSRI": STATUS_LIVE,
            "LIBERATOR": STATUS_SANDBOX,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P2_PORTFOLIO",
        "pillar": "P2",
        "name": "Portfolio — Holdings & Equity",
        "notes": "Krungsri portfolio scrape + realtime account equity",
        "cells": {
            "KRUNGSRI": STATUS_LIVE,
            "LIBERATOR": STATUS_SANDBOX,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P3_TRADE",
        "pillar": "P3",
        "name": "Trade — Place / Amend / Cancel",
        "notes": "คำสั่งซื้อขาย + HITL gate (requirement #2: ต่อราคา + สั่งการผ่าน LINE)",
        "cells": {
            "KRUNGSRI": STATUS_LIVE,
            "LIBERATOR": STATUS_SANDBOX,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P5_ORDERS",
        "pillar": "P5",
        "name": "Orders — Ledger & HITL Queue",
        "notes": "SQLite order journal + pending HITL order queue",
        "cells": {
            "KRUNGSRI": STATUS_LIVE,
            "LIBERATOR": STATUS_SANDBOX,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P4_SBL",
        "pillar": "P4",
        "name": "SBL — Borrow / Return / XD Shield",
        "notes": "ปิดไว้ก่อน (2026-10-10) — Krungsri MARGIN เท่านั้น",
        "cells": {
            "KRUNGSRI": STATUS_DISABLED,
            "LIBERATOR": STATUS_NA,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P6_TACTICAL",
        "pillar": "P6",
        "name": "Tactical — Negotiate / Action-Exit / EOD",
        "notes": "ปิดไว้ก่อน (2026-10-10) — daemon default OFF",
        "cells": {
            "KRUNGSRI": STATUS_DISABLED,
            "LIBERATOR": STATUS_DISABLED,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
    {
        "key": "P7_AGENTIC",
        "pillar": "P7",
        "name": "Agentic — PT-MRO Orchestrator",
        "notes": "ปิดไว้ก่อน (2026-10-10) — background loop default OFF",
        "cells": {
            "KRUNGSRI": STATUS_DISABLED,
            "LIBERATOR": STATUS_NA,
            "CLICK2WIN": STATUS_NA,
            "SETTRADE_OPENAPI": STATUS_NA,
        },
    },
]


def build_matrix_payload() -> Dict[str, Any]:
    """Return the full serialisable matrix payload for the admin API / console."""
    return {
        "brokers": BROKERS,
        "pillars": FEATURE_MATRIX,
        "status_meta": STATUS_META,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
