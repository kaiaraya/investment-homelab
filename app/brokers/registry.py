"""
Centralized Broker Registry for Pluggable Homelab Engines.
=========================================================
Dynamically discovers, registers, and routes calls to isolated broker plugins.
Supports hot-swapping and graceful degradation:
If a broker is missing credentials or fails, other brokers continue running 100%.
"""

import logging
from typing import Dict, List, Optional, Any
from app.brokers.base import BaseBrokerPlugin, BrokerStatus

logger = logging.getLogger("BrokerRegistry")


class BrokerRegistry:
    def __init__(self):
        self._plugins: Dict[str, BaseBrokerPlugin] = {}

    def register(self, plugin: BaseBrokerPlugin) -> None:
        """Registers a broker plugin into the registry."""
        name = plugin.metadata.name.lower().strip()
        self._plugins[name] = plugin
        configured = plugin.is_configured()
        logger.info(f"Registered broker plugin '{plugin.metadata.display_name}' [{name}] (Configured={configured})")

    def get(self, name: str) -> Optional[BaseBrokerPlugin]:
        """Retrieves a broker plugin by its unique name/slug."""
        return self._plugins.get(name.lower().strip())

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """Returns metadata and configuration status for all registered brokers."""
        result = {}
        for name, plugin in self._plugins.items():
            result[name] = {
                "name": plugin.metadata.name,
                "display_name": plugin.metadata.display_name,
                "transport": plugin.metadata.transport.value,
                "is_configured": plugin.is_configured(),
                "status": plugin.status.value,
                "supported_markets": plugin.metadata.supported_markets,
                "supported_accounts": plugin.metadata.supported_accounts,
                "supports_sbl": plugin.metadata.supports_sbl,
                "supports_direct_api": plugin.metadata.supports_direct_api,
                "capabilities": [c.value for c in plugin.capabilities]
            }
        return result

    async def get_all_health(self) -> Dict[str, Any]:
        """Gathers health status across all registered brokers."""
        statuses = {}
        for name, plugin in self._plugins.items():
            try:
                statuses[name] = await plugin.get_health()
            except Exception as e:
                statuses[name] = {
                    "status": BrokerStatus.FAILED.value,
                    "error": str(e)
                }
        return statuses

    def get_active(self, platform_slug: Optional[str] = None) -> Optional[BaseBrokerPlugin]:
        """Returns the primary active broker based on parameter or default config."""
        from app.core.config import settings
        target = (platform_slug or getattr(settings, "TRADING_PLATFORM", "KRUNGSRI")).lower().strip()
        if target in ["trademan", "krungsri"]:
            return self.get("krungsri")
        elif target in ["liberator"]:
            return self.get("liberator")
        elif target in ["settrade_openapi", "openapi"]:
            return self.get("settrade_openapi")
        elif target in ["click2win"]:
            return self.get("click2win")
        return self.get(target)


# Global Singleton Registry
broker_registry = BrokerRegistry()
