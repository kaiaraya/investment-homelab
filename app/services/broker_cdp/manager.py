# -*- coding: utf-8 -*-
"""CDP gateway tab manager — route ``(broker, target)`` to a live tab, serialized by per-key ``asyncio.Lock``.

The gateway connects to broker session daemons that run in *separate* OS processes
(Chrome launched with ``--remote-debugging-port`` and kept alive by
``scripts/broker_cdp/session_daemon.py``). This module is the gateway-side routing layer:

- ``get_tab(broker, target)`` resolves which live tab a logical ``(broker, target)`` request
  maps to, reusing ``resolve_target_tab`` from the shared CDP client; and
- a per-``(broker, target)`` ``asyncio.Lock`` serializes access so the bot never races a human
  (or another automation call) touching the same tab at the same time.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Tuple

from playwright.async_api import Page

from scripts.broker_cdp.client import cdp_url_for, connect_cdp, resolve_target_tab

logger = logging.getLogger("broker_cdp_manager")

#: (broker, target) -> asyncio.Lock. Lazily created on first use; one lock per logical tab so
#: concurrent callers targeting the *same* tab are serialized while different tabs run in parallel.
_tab_locks: Dict[Tuple[str, str], asyncio.Lock] = {}


def _lock_key(broker: str, target: str) -> Tuple[str, str]:
    return (broker or "").strip().lower(), (target or "").strip().lower()


def lock_for(broker: str, target: str) -> asyncio.Lock:
    """Return the per-``(broker, target)`` access lock, creating it on first use."""
    key = _lock_key(broker, target)
    lock = _tab_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _tab_locks[key] = lock
    return lock


@asynccontextmanager
async def get_tab(broker: str, target: str) -> AsyncIterator[Page]:
    """Resolve and lock the live tab for ``(broker, target)``.

    Acquires the per-key lock first, then connects to the broker's CDP daemon and resolves the
    requested target tab. The lock is held for the entire ``async with`` block, so the caller
    owns the tab exclusively until it exits; a concurrent bot/human call on the same
    ``(broker, target)`` blocks on the lock.

    Example::

        async with get_tab("kss", "streaming") as page:
            await page.click("#equity-place-order-buy-radio-button")
    """
    lock = lock_for(broker, target)
    async with lock:
        logger.debug("get_tab(%s, %s) — lock acquired", broker, target)
        pw = None
        try:
            pw, _browser, ctx = await connect_cdp(cdp_url_for(broker), broker=broker)
            page = await resolve_target_tab(ctx, target, broker)
            if page is None:
                raise RuntimeError(f"No tab found for broker={broker!r} target={target!r}")
            yield page
        finally:
            # Disconnect from CDP only — do NOT close the browser. The daemon process owns it
            # and must keep it alive for the human and subsequent calls.
            if pw is not None:
                await pw.stop()
