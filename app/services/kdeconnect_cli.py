#!/usr/bin/env python3
"""
Standalone CLI & Test Harness for KDE Connect OTP Relay.
========================================================
Run independently to diagnose, test, and listen for broker SMS OTPs:

Usage:
    .venv/bin/python -m app.services.kdeconnect_cli ping
    .venv/bin/python -m app.services.kdeconnect_cli routes
    .venv/bin/python -m app.services.kdeconnect_cli listen-otp
    .venv/bin/python -m app.services.kdeconnect_cli status
"""

import sys
import os
import asyncio
import time
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, PROJECT_ROOT)

from app.services.kdeconnect_service import kdeconnect_service


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        print("\n" + "=" * 65)
        print(" 📱 KDE CONNECT ZERO-CLOUD RELAY STATUS")
        print("=" * 65)
        reachable = await kdeconnect_service.is_device_reachable()
        dev_id = await kdeconnect_service.get_reachable_device_id()
        routes = await kdeconnect_service.get_network_routes()

        print(f" • Device Reachable: {'✅ YES' if reachable else '❌ NO'}")
        print(f" • Active Device ID: {dev_id or 'None'}")
        print(f" • Active Route:     {routes.get('route_label', 'Unknown')}")
        print(f" • Remote IP:        {routes.get('remote_ip', '-')}")
        print(f" • Wi-Fi Channel:    {routes.get('wifi', 'OFFLINE')}")
        print(f" • Tailscale:        {routes.get('tailscale', 'OFFLINE')}")
        print("=" * 65 + "\n")

    elif cmd == "ping":
        print("\n🔔 Sending test ping notification to mobile phone...")
        success = await kdeconnect_service.send_critical_alert("ทดสอบสัญญาณ KDE Connect จาก Homelab (Ping OK!)")
        if success:
            print("✅ Ping sent successfully! Please check your mobile phone.")
        else:
            print("❌ Failed to send ping. Please check if KDE Connect is running.")

    elif cmd == "routes":
        print("\n🌐 Inspecting network routes...")
        routes = await kdeconnect_service.get_network_routes()
        for k, v in routes.items():
            print(f" • {k}: {v}")

    elif cmd == "listen-otp":
        print("\n" + "=" * 65)
        print(" 🔑 LIVE 2FA SMS OTP LISTENER (Press Ctrl+C to stop)")
        print(" Request an SMS OTP from your broker now...")
        print("=" * 65 + "\n")

        last_seen = None
        while True:
            try:
                item = await kdeconnect_service.poll_active_notifications()
                if item and item.otp_code and item.otp_code != last_seen:
                    last_seen = item.otp_code
                    now_str = datetime.now().strftime("%H:%M:%S")
                    print(f"[{now_str}] 🎉 CAPTURED OTP!")
                    print(f"  • Raw OTP Code:     {item.otp_code}")
                    print(f"  • Masked Code:       {item.masked_otp}")
                    print(f"  • Source App/Sender: {item.source_app or 'SMS'}")
                    print(f"  • Body Snippet:      {item.body[:80]}...\n")
                await asyncio.sleep(1.0)
            except KeyboardInterrupt:
                print("\n🛑 Stopped OTP listener.")
                break
            except Exception as e:
                print(f"⚠️ Error listening: {e}")
                await asyncio.sleep(2.0)

    else:
        print(f"Unknown command: '{cmd}'. Available: status, ping, routes, listen-otp")


if __name__ == "__main__":
    asyncio.run(main())
