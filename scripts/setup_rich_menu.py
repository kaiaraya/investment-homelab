#!/usr/bin/env python3
"""
scripts/setup_rich_menu.py — Rich Menu Generator & LINE Setup Script (Loop 2)

Features:
1. Renders pixel-perfect 2500x1686 PNG using headless Playwright from rich_menu.py HTML template.
2. Registers 2x2 Grid Rich Menu schema with LINE Messaging API.
3. Uploads the rendered PNG and sets the Rich Menu as default for all users.

Usage:
  .venv/bin/python scripts/setup_rich_menu.py --render-only
  .venv/bin/python scripts/setup_rich_menu.py --dry-run
  .venv/bin/python scripts/setup_rich_menu.py
"""

import sys
import os
import argparse
import asyncio
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.services.line_cli.rich_menu import (
    get_homelab_rich_menu_spec,
    get_rich_menu_html,
    LineRichMenuService,
    RICH_MENU_WIDTH,
    RICH_MENU_HEIGHT
)

async def render_rich_menu_image(output_path: Path) -> Path:
    """
    Renders HTML template into 2500x1686 PNG using headless Playwright.
    """
    from playwright.async_api import async_playwright

    print(f"🎨 Rendering Rich Menu HTML ({RICH_MENU_WIDTH}x{RICH_MENU_HEIGHT}) via Playwright...")
    html_content = get_rich_menu_html()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    launch_kwargs = {"headless": True}
    if os.path.exists("/usr/bin/google-chrome"):
        launch_kwargs["executable_path"] = "/usr/bin/google-chrome"

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            viewport={"width": RICH_MENU_WIDTH, "height": RICH_MENU_HEIGHT},
            device_scale_factor=1.0
        )
        page = await context.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        await page.screenshot(path=str(output_path), clip={"x": 0, "y": 0, "width": RICH_MENU_WIDTH, "height": RICH_MENU_HEIGHT})
        await browser.close()

    print(f"✅ Image rendered successfully: {output_path} ({output_path.stat().st_size:,} bytes)")
    return output_path


async def main():
    parser = argparse.ArgumentParser(description="Generate and upload InvestmentHomelab LINE Rich Menu")
    parser.add_argument("--render-only", action="store_true", help="Only render image, do not interact with LINE API")
    parser.add_argument("--dry-run", action="store_true", help="Simulate LINE API interactions")
    parser.add_argument("--output", type=str, default="data/rich_menu_2500x1686.png", help="Path to save rendered image")
    args = parser.parse_args()

    out_file = ROOT_DIR / args.output
    await render_rich_menu_image(out_file)

    if args.render_only:
        print("🏁 Render-only flag set. Done.")
        return 0

    print("🚀 Registering Rich Menu with LINE API...")
    service = LineRichMenuService()
    if args.dry_run:
        service.is_simulation = True

    spec = get_homelab_rich_menu_spec()
    menu_id = await service.create_rich_menu(spec)
    if not menu_id:
        print("❌ Failed to create rich menu resource")
        return 1

    print(f"📋 Rich Menu ID: {menu_id}")

    with open(out_file, "rb") as f:
        img_bytes = f.read()

    print(f"📤 Uploading {len(img_bytes):,} bytes image to {menu_id}...")
    uploaded = await service.upload_rich_menu_image(menu_id, img_bytes)
    if not uploaded:
        print("❌ Failed to upload rich menu image")
        return 1

    print("🌟 Setting rich menu as default for all users...")
    set_def = await service.set_default_rich_menu(menu_id)
    if not set_def:
        print("❌ Failed to set default rich menu")
        return 1

    print("🎉 Rich Menu successfully installed and activated as default!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
