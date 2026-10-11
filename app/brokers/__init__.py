"""
Pluggable Broker Package Initialization.
Registers all isolated broker plugins into the central broker_registry.
"""

from app.brokers.base import BaseBrokerPlugin, BrokerMetadata, TransportType, BrokerStatus
from app.brokers.registry import broker_registry

from app.brokers.krungsri.plugin import krungsri_plugin
from app.brokers.settrade_openapi.plugin import settrade_openapi_plugin
from app.brokers.liberator.plugin import liberator_plugin
from app.brokers.click2win.plugin import click2win_plugin

# Auto-register all supported brokers into registry
broker_registry.register(krungsri_plugin)
broker_registry.register(settrade_openapi_plugin)
broker_registry.register(liberator_plugin)
broker_registry.register(click2win_plugin)

__all__ = [
    "broker_registry",
    "krungsri_plugin",
    "settrade_openapi_plugin",
    "liberator_plugin",
    "click2win_plugin",
    "BaseBrokerPlugin",
    "BrokerMetadata",
    "TransportType",
    "BrokerStatus"
]
