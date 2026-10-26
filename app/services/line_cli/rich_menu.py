"""
LINE Rich Menu Definitions and Management for InvestmentHomelab (Loop 2).

Provides:
1. 2x2 Grid Rich Menu Specification (2500x1686)
   - Cell 1 (Top-Left):     📊 พอร์ต & เงินสด (/port all sync)
   - Cell 2 (Top-Right):    📋 คำสั่ง & สถานะ (/orders all sync)
   - Cell 3 (Bottom-Left):  🔐 สถานะระบบ (/status)
   - Cell 4 (Bottom-Right): ⚡ ต่อราคา (Postback: action=nego_menu)
2. API management: create, upload image, set default, list, delete.
3. Dark theme HTML generator for Playwright screenshot rendering.
"""

from typing import Dict, Any, List, Optional
import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

RICH_MENU_WIDTH = 2500
RICH_MENU_HEIGHT = 1686

def get_homelab_rich_menu_spec() -> Dict[str, Any]:
    """
    Returns the LINE Rich Menu JSON schema for 2x2 Grid (2500x1686).
    """
    half_w = RICH_MENU_WIDTH // 2   # 1250
    half_h = RICH_MENU_HEIGHT // 2  # 843

    return {
        "size": {
            "width": RICH_MENU_WIDTH,
            "height": RICH_MENU_HEIGHT
        },
        "selected": True,
        "name": "InvestmentHomelab Main Menu",
        "chatBarText": "เมนูหลัก Homelab",
        "areas": [
            {
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": half_w,
                    "height": half_h
                },
                "action": {
                    "type": "message",
                    "text": "/port all sync"
                }
            },
            {
                "bounds": {
                    "x": half_w,
                    "y": 0,
                    "width": half_w,
                    "height": half_h
                },
                "action": {
                    "type": "message",
                    "text": "/orders all sync"
                }
            },
            {
                "bounds": {
                    "x": 0,
                    "y": half_h,
                    "width": half_w,
                    "height": half_h
                },
                "action": {
                    "type": "message",
                    "text": "/status"
                }
            },
            {
                "bounds": {
                    "x": half_w,
                    "y": half_h,
                    "width": half_w,
                    "height": half_h
                },
                "action": {
                    "type": "postback",
                    "data": "action=nego_menu",
                    "displayText": "⚡ ต่อราคาออเดอร์ค้าง"
                }
            }
        ]
    }


def get_rich_menu_html() -> str:
    """
    Returns high-contrast, modern dark-themed HTML to render into 2500x1686 PNG.
    Uses glassmorphic cards, vibrant accent glows, clean icons, and Thai typography.
    """
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    body {{
      width: {RICH_MENU_WIDTH}px;
      height: {RICH_MENU_HEIGHT}px;
      background: radial-gradient(circle at 50% 50%, #0d131f 0%, #06090e 100%);
      color: #ffffff;
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: 1fr 1fr;
      gap: 16px;
      padding: 24px;
      overflow: hidden;
    }}

    .grid-cell {{
      position: relative;
      border-radius: 36px;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.01) 100%);
      border: 2px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 40px;
      box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.1), 0 20px 40px rgba(0, 0, 0, 0.4);
    }}

    /* Individual Tile Highlights */
    .cell-portfolio {{
      border-color: rgba(56, 189, 248, 0.3);
      background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.15) 0%, rgba(13, 19, 31, 0.6) 70%);
    }}
    .cell-orders {{
      border-color: rgba(245, 158, 11, 0.3);
      background: radial-gradient(circle at top right, rgba(245, 158, 11, 0.15) 0%, rgba(13, 19, 31, 0.6) 70%);
    }}
    .cell-status {{
      border-color: rgba(168, 85, 247, 0.3);
      background: radial-gradient(circle at bottom left, rgba(168, 85, 247, 0.15) 0%, rgba(13, 19, 31, 0.6) 70%);
    }}
    .cell-trade {{
      border-color: rgba(34, 197, 94, 0.4);
      background: radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.2) 0%, rgba(13, 19, 31, 0.6) 70%);
    }}

    .icon-container {{
      width: 180px;
      height: 180px;
      border-radius: 45px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 85px;
      margin-bottom: 32px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.3);
    }}

    .icon-portfolio {{ background: linear-gradient(135deg, #0284c7, #38bdf8); }}
    .icon-orders {{ background: linear-gradient(135deg, #d97706, #fbbf24); }}
    .icon-status {{ background: linear-gradient(135deg, #7e22ce, #c084fc); }}
    .icon-trade {{ background: linear-gradient(135deg, #15803d, #4ade80); }}

    .title {{
      font-size: 64px;
      font-weight: 800;
      letter-spacing: -1px;
      margin-bottom: 16px;
    }}
    .subtitle {{
      font-size: 36px;
      font-weight: 500;
      color: #94a3b8;
      letter-spacing: 0.5px;
    }}
    .badge {{
      display: inline-block;
      margin-top: 20px;
      padding: 10px 28px;
      border-radius: 9999px;
      font-size: 28px;
      font-weight: 700;
      background: rgba(255, 255, 255, 0.1);
      color: #e2e8f0;
      border: 1px solid rgba(255, 255, 255, 0.15);
    }}
  </style>
</head>
<body>
  <!-- Top Left: Portfolio & Cash -->
  <div class="grid-cell cell-portfolio">
    <div class="icon-container icon-portfolio">📊</div>
    <div class="title">พอร์ต & เงินสด</div>
    <div class="subtitle">Liberator + Krungsri Sync</div>
    <div class="badge">/port all sync</div>
  </div>

  <!-- Top Right: Orders & Pending -->
  <div class="grid-cell cell-orders">
    <div class="icon-container icon-orders">📋</div>
    <div class="title">คำสั่งซื้อขาย</div>
    <div class="subtitle">สถานะออร์เดอร์ & ต่อราคา</div>
    <div class="badge">/orders all sync</div>
  </div>

  <!-- Bottom Left: System Status -->
  <div class="grid-cell cell-status">
    <div class="icon-container icon-status">🔐</div>
    <div class="title">สถานะระบบ</div>
    <div class="subtitle">OTP Relay, Sessions & Daemons</div>
    <div class="badge">/status</div>
  </div>

  <!-- Bottom Right: Nego Menu (ต่อราคา) -->
  <div class="grid-cell cell-trade">
    <div class="icon-container icon-trade">⚡</div>
    <div class="title">ต่อราคา</div>
    <div class="subtitle">Match Spread • ล่อราคา (Lure)</div>
    <div class="badge">⚡ ต่อราคาออเดอร์ค้าง</div>
  </div>
</body>
</html>"""


class LineRichMenuService:
    """
    Manages creation, image uploading, and default assignment of LINE Rich Menu.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.LINE_CHANNEL_ACCESS_TOKEN
        self.is_simulation = settings.LINE_SIMULATION_MODE or not self.token or self.token == "mock_line_channel_token"

    async def list_rich_menus(self) -> List[Dict[str, Any]]:
        """Lists all active rich menus from LINE API."""
        if self.is_simulation:
            logger.info("[LINE RichMenu] Simulating list_rich_menus")
            return []

        url = "https://api.line.me/v2/bot/richmenu/list"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("richmenus", [])
            logger.error(f"[LINE RichMenu] List failed ({resp.status_code}): {resp.text}")
            return []

    async def create_rich_menu(self, spec: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Creates a rich menu resource in LINE and returns its richMenuId."""
        payload = spec or get_homelab_rich_menu_spec()

        if self.is_simulation:
            logger.info(f"[LINE RichMenu] Simulating create_rich_menu: {payload.get('name')}")
            return "richmenu-simulated-id-homelab"

        url = "https://api.line.me/v2/bot/richmenu"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                menu_id = resp.json().get("richMenuId")
                logger.info(f"[LINE RichMenu] Created richMenuId: {menu_id}")
                return menu_id
            logger.error(f"[LINE RichMenu] Creation failed ({resp.status_code}): {resp.text}")
            return None

    async def upload_rich_menu_image(self, rich_menu_id: str, image_bytes: bytes, content_type: str = "image/png") -> bool:
        """Uploads PNG/JPEG image data to a created richMenuId."""
        if self.is_simulation:
            logger.info(f"[LINE RichMenu] Simulating upload_rich_menu_image for {rich_menu_id} ({len(image_bytes)} bytes)")
            return True

        url = f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, content=image_bytes)
            if resp.status_code == 200:
                logger.info(f"[LINE RichMenu] Successfully uploaded image for {rich_menu_id}")
                return True
            logger.error(f"[LINE RichMenu] Image upload failed ({resp.status_code}): {resp.text}")
            return False

    async def set_default_rich_menu(self, rich_menu_id: str) -> bool:
        """Links the rich menu as default for all users."""
        if self.is_simulation:
            logger.info(f"[LINE RichMenu] Simulating set_default_rich_menu: {rich_menu_id}")
            return True

        url = f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 200:
                logger.info(f"[LINE RichMenu] Set default rich menu to {rich_menu_id}")
                return True
            logger.error(f"[LINE RichMenu] Set default failed ({resp.status_code}): {resp.text}")
            return False

    async def delete_rich_menu(self, rich_menu_id: str) -> bool:
        """Deletes a rich menu from LINE API."""
        if self.is_simulation:
            logger.info(f"[LINE RichMenu] Simulating delete_rich_menu: {rich_menu_id}")
            return True

        url = f"https://api.line.me/v2/bot/richmenu/{rich_menu_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(url, headers=headers)
            return resp.status_code == 200
