import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tpsl_overview_negotiate_endpoints(client: AsyncClient):
    # 1. Test Natural language TP/SL endpoint
    payload = {
        "message": "CPALL ตั้ง TP 68 SL 62 นะ ส่วนตัวที่ Short AP ไว้ ให้ TP 7.50 SL 8.10"
    }
    resp = await client.post("/api/v1/phase3/tpsl/natural-language", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["updated_count"] == 2

    # 2. Test Get positions endpoint
    pos_resp = await client.get("/api/v1/phase3/positions")
    assert pos_resp.status_code == 200
    positions = pos_resp.json()
    syms = [p["symbol"] for p in positions]
    assert "CPALL" in syms
    assert "AP" in syms

    # 3. Test Portfolio Overview trigger
    ov_resp = await client.post("/api/v1/phase3/overview")
    assert ov_resp.status_code == 200
    ov_data = ov_resp.json()
    assert ov_data["success"] is True

    # 4. Test Price Negotiation trigger
    nego_resp = await client.post("/api/v1/phase3/negotiate")
    assert nego_resp.status_code == 200
