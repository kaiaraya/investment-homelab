"""
Test script: Push real Negotiate Flex Card to LINE Group
========================================================
Pushes the exact Flex Card generated from order 11008198 (MTC Short @ 29.50 staged)
directly to the LINE Group ("a14s homelab").
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings
from app.services.line_service import line_service
from app.services.line_cli import cards

BKK = timezone(timedelta(hours=7))

async def main():
    print("=" * 60)
    print("📲 Pushing /negotiate Flex Card to LINE Group")
    print("=" * 60)

    now_ts = datetime.now(BKK).strftime("%H:%M:%S")

    # Generate the exact negotiate card
    card = cards.negotiate_card(
        order_no="11008198",
        symbol="MTC",
        side="SHORT",
        outcome="OK",
        current_price=29.25,
        target_price=29.50,
        volume=1700,
        reason="Staged via Live Headed DRY-RUN Probe (Settrade Angular Form)",
        submitted=False,  # DRY-RUN
        ts=now_ts,
        is_test=True,     # DRY-RUN / TEST mode badge
    )

    print(f"📍 Target Group: {settings.LINE_GROUP_ID}")
    success = await line_service.push_message(card)
    if success:
        print("✅ Flex Card successfully sent to LINE Group!")
        print("👉 กรุณาตรวจดูข้อความและ Flex Card บนมือถือของคุณใน LINE Group 'a14s homelab'")
    else:
        print("❌ Failed to push message to LINE. Check tokens / simulation mode.")

if __name__ == "__main__":
    asyncio.run(main())
