# -*- coding: utf-8 -*-
"""STEP 1.4 pre-witness dry-exec — fill the REAL order ticket, stop before Send.

Sets ``settings.DRY_RUN_MODE = True`` and calls
``trademan_driver.execute_order("BCPG", "COVER", 100, 6.75)`` **without**
``bypass_dry_run``. The driver will drive the live TradeMan DOM through the full
Tier 1 -> Tier 3 / Tier 2 -> Tier 3 symbol-selection chain, fill the volume and
price inputs, then stop right before clicking Send and return ``SIMULATED_SUCCESS``.

Requires a live logged-in TradeMan session (human OTP). If no authenticated page
can be restored, the driver fails closed (never fabricates a success on a dead
session). Prints the returned dict and nothing else.

DO NOT RUN THIS against a stale/decayed SSO session — it touches the real
order-ticket form (though it never submits).
"""
import asyncio
import json
import logging

from app.core.config import settings
from app.browser.trademan_driver import trademan_driver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


async def main():
    # 1.4 explicitly runs in dry-run mode (no bypass) — the ticket is filled for
    # real but Send is omitted, so the T1/T2/T3 chain is proven with zero risk.
    settings.DRY_RUN_MODE = True

    page = await trademan_driver.ensure_browser_ready()
    if page is None:
        print(json.dumps({
            "success": False,
            "status": "NO_SESSION",
            "error": (
                "No authenticated TradeMan page could be restored. "
                "Establish a live login first (human OTP), then re-run."
            ),
        }, ensure_ascii=False))
        return

    result = await trademan_driver.execute_order("BCPG", "COVER", 100, 6.75)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
