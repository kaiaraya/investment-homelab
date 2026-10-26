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

async def render_rich_menu_image(output_path: Path, quality: int = 85) -> Path:
    """
    Renders HTML template into a LINE-rich-menu image.

    LINE caps the upload at **1 MB**, while an unoptimised 2500x1686 PNG is ~1.7 MB
    (a live upload returns HTTP 413). JPEG at the same dimensions stays well under
    the cap, so the default output is JPEG; a .png suffix still renders PNG for
    inspection.
    """
    from playwright.async_api import async_playwright

    is_jpeg = output_path.suffix.lower() in (".jpg", ".jpeg")
    fmt = "jpeg" if is_jpeg else "png"
    print(f"🎨 Rendering Rich Menu HTML ({RICH_MENU_WIDTH}x{RICH_MENU_HEIGHT}, {fmt}) via Playwright...")
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
        shot_kwargs = {"path": str(output_path), "type": fmt,
                       "clip": {"x": 0, "y": 0, "width": RICH_MENU_WIDTH, "height": RICH_MENU_HEIGHT}}
        if is_jpeg:
            shot_kwargs["quality"] = quality
        await page.screenshot(**shot_kwargs)
        await browser.close()

    size = output_path.stat().st_size
    print(f"✅ Image rendered successfully: {output_path} ({size:,} bytes)")
    if size > 1_000_000:
        print("⚠️  Image exceeds LINE's 1 MB limit — rerun with --quality 75 or lower")
    return output_path


async def main():
    parser = argparse.ArgumentParser(description="Generate and upload InvestmentHomelab LINE Rich Menu")
    parser.add_argument("--render-only", action="store_true", help="Only render image, do not interact with LINE API")
    parser.add_argument("--dry-run", action="store_true", help="Simulate LINE API interactions")
    parser.add_argument("--list", action="store_true", help="List existing rich menus (read-only) and exit")
    parser.add_argument("--delete-id", type=str, default=None, help="Delete one rich menu by id and exit")
    parser.add_argument("--output", type=str, default="data/rich_menu_2500x1686.jpg", help="Path to save rendered image (.jpg = LINE-safe <=1MB)")
    parser.add_argument("--quality", type=int, default=85, help="JPEG quality (lower = smaller file; LINE cap is 1MB)")
    args = parser.parse_args()

    service = LineRichMenuService()
    if args.dry_run:
        service.is_simulation = True

    # Read-only / admin modes (no image render needed)
    if args.list:
        menus = await service.list_rich_menus()
        if not menus:
            print("📭 No rich menus on this OA (or simulation).")
        for m in menus:
            print(f"  {m.get('richMenuId')}  name={m.get('name')!r}  size={m.get('size')}")
        return 0

    if args.delete_id:
        ok = await service.delete_rich_menu(args.delete_id)
        print(("✅ deleted " if ok else "❌ delete failed ") + args.delete_id)
        return 0 if ok else 1

    out_file = ROOT_DIR / args.output
    await render_rich_menu_image(out_file, quality=args.quality)

    if args.render_only:
        print("🏁 Render-only flag set. Done.")
        return 0

    spec = get_homelab_rich_menu_spec()

    if args.dry_run:
        import json as _json
        print("🧪 DRY-RUN — rich menu payload (nothing sent to LINE):")
        print(_json.dumps(spec, ensure_ascii=False, indent=2)[:1200])

    print("🚀 Registering Rich Menu with LINE API...")

    # Idempotency: delete an existing menu with the same name before creating a new one,
    # so re-running never stacks duplicate menus on the OA.
    existing = await service.list_rich_menus()
    for m in existing:
        if m.get("name") == spec.get("name"):
            print(f"♻️  Removing previous menu {m.get('richMenuId')} (same name)")
            await service.delete_rich_menu(str(m.get("richMenuId")))

    menu_id = await service.create_rich_menu(spec)
    if not menu_id:
        print("❌ Failed to create rich menu resource")
        return 1

    print(f"📋 Rich Menu ID: {menu_id}")

    with open(out_file, "rb") as f:
        img_bytes = f.read()

    print(f"📤 Uploading {len(img_bytes):,} bytes image to {menu_id}...")
    content_type = "image/jpeg" if out_file.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    uploaded = await service.upload_rich_menu_image(menu_id, img_bytes, content_type=content_type)
    if not uploaded:
        print("❌ Failed to upload rich menu image")
        return 1

    print("🌟 Setting rich menu as default for all users...")
    set_def = await service.set_default_rich_menu(menu_id)
    if not set_def:
        print("❌ Failed to set default rich menu")
        return 1

    print("🎉 Rich Menu successfully installed and activated as default!")
    print(f"   rollback: .venv/bin/python scripts/setup_rich_menu.py --delete-id {menu_id}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
