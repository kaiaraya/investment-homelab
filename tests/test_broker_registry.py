"""
Unit tests for Pluggable BrokerRegistry and Plugin Architecture.
"""

import pytest
from app.brokers import broker_registry, krungsri_plugin, settrade_openapi_plugin, liberator_plugin, click2win_plugin
from app.brokers.base import TransportType


def test_registered_plugins_exist():
    plugins = broker_registry.list_all()
    assert "krungsri" in plugins
    assert "settrade_openapi" in plugins
    assert "liberator" in plugins
    assert "click2win" in plugins


def test_transport_types():
    assert krungsri_plugin.metadata.transport == TransportType.PLAYWRIGHT
    assert settrade_openapi_plugin.metadata.transport == TransportType.DIRECT_API
    assert liberator_plugin.metadata.transport == TransportType.PLAYWRIGHT
    assert click2win_plugin.metadata.transport == TransportType.PLAYWRIGHT


def test_get_broker_by_slug():
    k = broker_registry.get("krungsri")
    assert k == krungsri_plugin

    s = broker_registry.get("settrade_openapi")
    assert s == settrade_openapi_plugin

    l = broker_registry.get("liberator")
    assert l == liberator_plugin

    c = broker_registry.get("click2win")
    assert c == click2win_plugin


@pytest.mark.asyncio
async def test_get_all_health():
    health_data = await broker_registry.get_all_health()
    assert "krungsri" in health_data
    assert "settrade_openapi" in health_data
    assert "liberator" in health_data
    assert "click2win" in health_data
    assert health_data["settrade_openapi"]["transport"] == "DIRECT_API"


def test_broker_capabilities_matrix():
    from app.brokers.base import BrokerCapability

    # Krungsri: SBL + Equity + Browser
    assert krungsri_plugin.has_capability(BrokerCapability.SBL_SHORT)
    assert krungsri_plugin.has_capability(BrokerCapability.EQUITY_TRADE)
    assert krungsri_plugin.has_capability(BrokerCapability.MULTI_FACTOR_OTP)

    # Click2Win: Equity + TFEX, No SBL
    assert click2win_plugin.has_capability(BrokerCapability.EQUITY_TRADE)
    assert click2win_plugin.has_capability(BrokerCapability.DERIVATIVES_TRADE)
    assert not click2win_plugin.has_capability(BrokerCapability.SBL_SHORT)

    # Settrade Open API: Direct API + Realtime Stream
    assert settrade_openapi_plugin.has_capability(BrokerCapability.DIRECT_API)
    assert settrade_openapi_plugin.has_capability(BrokerCapability.REALTIME_STREAM)

    # Liberator: Equity + Browser
    assert liberator_plugin.has_capability(BrokerCapability.EQUITY_TRADE)
    assert not liberator_plugin.has_capability(BrokerCapability.SBL_SHORT)


@pytest.mark.asyncio
async def test_unsupported_capability_graceful_fallbacks():
    # Calling SBL on Click2Win or Liberator safely returns error dict without throwing exception
    sbl_res = await click2win_plugin.borrow_sbl("PTT", 100)
    assert sbl_res["success"] is False
    assert sbl_res["error_type"] == "UNSUPPORTED_CAPABILITY"

    lib_sbl = await liberator_plugin.borrow_sbl("CPALL", 100)
    assert lib_sbl["success"] is False
    assert lib_sbl["error_type"] == "UNSUPPORTED_CAPABILITY"

