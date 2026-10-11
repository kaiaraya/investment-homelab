import pytest
from app.services.sbl_intelligence_service import sbl_intelligence_service


@pytest.mark.asyncio
async def test_sbl_deterministic_analysis():
    sample_sbl = {
        "set50_inventory": [
            {"symbol": "CPALL", "borrow_fee_pct": 3.5, "available_qty": 2_660_300, "initial_margin_pct": 50.0},
            {"symbol": "AOT", "borrow_fee_pct": 3.5, "available_qty": 4_194_400, "initial_margin_pct": 50.0},
            {"symbol": "BANPU", "borrow_fee_pct": 3.5, "available_qty": 0, "initial_margin_pct": 50.0},
        ],
        "xd_xr_inventory": [
            {"symbol": "AP", "borrow_fee_pct": 3.5, "available_qty": 500_000, "initial_margin_pct": 50.0, "sign": "XD"},
            {"symbol": "BCH", "borrow_fee_pct": 3.5, "available_qty": 300_000, "initial_margin_pct": 50.0, "sign": "XD"},
        ],
        "sbl_portfolio_lots": []
    }

    holdings = [
        {"symbol": "AP", "position_type": "SHORT", "volume": 5000},
        {"symbol": "CPALL", "position_type": "LONG", "volume": 800},
    ]

    analysis = sbl_intelligence_service._generate_deterministic_analysis(
        set50_list=sample_sbl["set50_inventory"],
        xd_xr_list=sample_sbl["xd_xr_inventory"],
        user_short_symbols=["AP"],
        portfolio_xd_conflicts=["AP"]
    )

    assert analysis["portfolio_safety_status"] == "DANGER"
    assert "AP" in analysis["conflicted_positions"]
    assert len(analysis["top_borrow_opportunities"]) >= 1
    assert analysis["top_borrow_opportunities"][0]["symbol"] in ["AOT", "CPALL"]


@pytest.mark.asyncio
async def test_sbl_audit_candidates_with_krungsri_realtime():
    sample_pool = {
        "success": True,
        "purchasing_power": 96885.94,
        "set50_inventory": [
            {"symbol": "BDMS", "borrow_fee_pct": 3.5, "available_qty": 5014000, "initial_margin_pct": 50.0},
            {"symbol": "CPALL", "borrow_fee_pct": 3.5, "available_qty": 2834800, "initial_margin_pct": 50.0},
        ],
        "set100_inventory": [],
        "newsec_inventory": [],
        "xd_xr_inventory": [
            {"symbol": "SAWAD", "book_date": "06/10/2026", "type": "XD", "sign": "XD"},
            {"symbol": "LH", "book_date": "14/10/2026", "type": "XD", "sign": "XD"},
        ]
    }

    res = await sbl_intelligence_service.audit_sbl_candidates(
        symbols=["SAWAD", "BDMS", "NONEXISTENT"],
        sbl_data=sample_pool
    )

    assert res["success"] is True
    candidates = res["candidates"]

    # 1. Verify SAWAD is HARD BLOCKED due to XD
    sawad = candidates["SAWAD"]
    assert sawad["has_xd_risk"] is True
    assert sawad["action_allowed"] is False
    assert sawad["verdict"] == "HARD_BLOCKED_XD_XR"
    assert "06/10/2026" in sawad["badge"]

    # 2. Verify BDMS is ALLOWED
    bdms = candidates["BDMS"]
    assert bdms["has_xd_risk"] is False
    assert bdms["action_allowed"] is True
    assert bdms["verdict"] == "BORROW_ALLOWED"
    assert bdms["available_qty"] == 5014000

    # 3. Verify Nonexistent is OUT OF STOCK
    non = candidates["NONEXISTENT"]
    assert non["action_allowed"] is False
    assert non["verdict"] == "OUT_OF_STOCK"

