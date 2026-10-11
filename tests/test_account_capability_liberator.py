"""
Unit tests for the Account Capability Guardrail — Liberator (single-account CASH) support.

Part of the Pillar 2 rename/refactor (Pillar 2 = Account & Portfolio). Verifies that
LIBERATOR normalizes to CASH (never EQUITY/MARGIN/DERIVATIVES) and routes to its OWN
matrix key (not CLICK2WIN), plus regression coverage for the other brokers.
"""
from app.schemas.account import (
    AccountType,
    AccountCapability,
    AccountCapabilityGuardrail,
)


def test_normalize_liberator_maps_to_cash():
    g = AccountCapabilityGuardrail
    assert g.normalize_account_type("LIBERATOR", "CASH") == AccountType.CASH
    assert g.normalize_account_type("LIBERATOR", "CASH_BALANCE") == AccountType.CASH


def test_normalize_liberator_clamps_margin_and_derivatives_to_cash():
    """Liberator is single-account: MARGIN / DERIVATIVES / TFEX must clamp to CASH."""
    g = AccountCapabilityGuardrail
    assert g.normalize_account_type("LIBERATOR", "MARGIN") == AccountType.CASH
    assert g.normalize_account_type("LIBERATOR", "SBL") == AccountType.CASH
    assert g.normalize_account_type("LIBERATOR", "DERIVATIVES") == AccountType.CASH
    assert g.normalize_account_type("LIBERATOR", "TFEX") == AccountType.CASH


def test_normalize_liberator_default_uses_active_context():
    g = AccountCapabilityGuardrail
    assert g.normalize_account_type("LIBERATOR", None) == AccountType.CASH


def test_normalize_regression_other_brokers():
    g = AccountCapabilityGuardrail
    assert g.normalize_account_type("KRUNGSRI", "MARGIN") == AccountType.MARGIN
    assert g.normalize_account_type("KRUNGSRI", "CASH") == AccountType.CASH
    assert g.normalize_account_type("CLICK2WIN", "EQUITY") == AccountType.EQUITY
    assert g.normalize_account_type("CLICK2WIN", "DERIVATIVES") == AccountType.DERIVATIVES
    assert g.normalize_account_type("SETTRADE_OPENAPI", "DERIVATIVES") == AccountType.DERIVATIVES


def test_liberator_platform_routes_to_liberator_matrix():
    """Regression: LIBERATOR must resolve against its OWN matrix key, not CLICK2WIN."""
    allowed, err, resolved = AccountCapabilityGuardrail.validate_capability(
        "LIBERATOR", "CASH", AccountCapability.PORTFOLIO_READ
    )
    assert allowed is True
    assert err is None
    assert resolved == AccountType.CASH


def test_liberator_sbl_rejected_with_switch_account_hint():
    allowed, err, resolved = AccountCapabilityGuardrail.validate_capability(
        "LIBERATOR", "CASH", AccountCapability.SBL_BORROW
    )
    assert allowed is False
    assert err is not None
    assert "switch_account" in err
    assert resolved == AccountType.CASH


def test_liberator_equity_trade_allowed():
    allowed, err, resolved = AccountCapabilityGuardrail.validate_capability(
        "LIBERATOR", "CASH", AccountCapability.EQUITY_TRADE
    )
    assert allowed is True
    assert err is None
    assert resolved == AccountType.CASH
