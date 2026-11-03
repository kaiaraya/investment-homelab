# -*- coding: utf-8 -*-
"""CDP gateway services: tab routing/manager, daemon launcher, and portfolio auto-sync (B.2/B.3)."""
from app.services.broker_cdp.daemon_launcher import (
    daemon_state,
    ensure_daemon,
    restart_daemon,
)

__all__ = [
    "daemon_state",
    "ensure_daemon",
    "restart_daemon",
]
