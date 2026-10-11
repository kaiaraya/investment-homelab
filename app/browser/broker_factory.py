import logging
from typing import Any, Union
from app.core.config import settings

from app.browser.auth_driver import auth_driver, KrungsriAuthDriver
from app.browser.trademan_driver import trademan_driver, TradeManDriver

from app.browser.click2win_auth_driver import click2win_auth_driver, Click2WinAuthDriver
from app.browser.click2win_driver import click2win_driver, Click2WinDriver

logger = logging.getLogger(__name__)


def get_broker_driver() -> Union[Click2WinDriver, TradeManDriver]:
    """
    Factory function returning the active broker driver based on settings.TRADING_PLATFORM.
    - 'CLICK2WIN': Returns Click2WinDriver (Sandbox for Equity & Derivatives)
    - 'TRADEMAN': Returns TradeManDriver (Krungsri Live Production)
    """
    platform = getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").upper().strip()
    if platform == "TRADEMAN":
        return trademan_driver
    return click2win_driver


def get_auth_driver() -> Union[Click2WinAuthDriver, KrungsriAuthDriver]:
    """
    Factory function returning the active authentication driver.
    - 'CLICK2WIN': Returns Click2WinAuthDriver
    - 'TRADEMAN': Returns KrungsriAuthDriver
    """
    platform = getattr(settings, "TRADING_PLATFORM", "CLICK2WIN").upper().strip()
    if platform == "TRADEMAN":
        return auth_driver
    return click2win_auth_driver
