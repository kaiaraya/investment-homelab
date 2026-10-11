import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.schemas.order import OrderCreate
from app.services.order_service import order_service


@pytest.mark.asyncio
async def test_orders_query_and_lifecycle(client: AsyncClient, db_session):
    # 1. Create two orders via the order service (validated + persisted)
    o1 = OrderCreate(symbol="TRUE", side="BUY", volume=3800, price=13.20, source="api")
    order1, valid1 = await order_service.create_order(db_session, o1, source="api")
    assert valid1 is True
    order_id1 = order1.order_id

    o2 = OrderCreate(symbol="AP", side="SHORT", volume=5000, price=8.20, source="api")
    order2, valid2 = await order_service.create_order(db_session, o2, source="api")
    assert valid2 is True
    order_id2 = order2.order_id

    # 2. Query all orders
    orders_resp = await client.get("/api/v1/orders")
    assert orders_resp.status_code == 200
    orders_list = orders_resp.json()
    assert len(orders_list) >= 2

    # 3. Query queue status
    q_resp = await client.get("/api/v1/orders/queue/status")
    assert q_resp.status_code == 200
    q_data = q_resp.json()
    assert "pending_orders" in q_data

    # 4. Test Rollover Carry-over
    rollover_resp = await client.post(
        "/api/v1/orders/rollover",
        json={"order_ids": [order_id1]}
    )
    assert rollover_resp.status_code == 200
    assert rollover_resp.json()["carried_over_count"] == 1

    # Verify status changed to CARRY_OVER_PENDING
    ord1_detail = await client.get(f"/api/v1/orders/{order_id1}")
    assert ord1_detail.status_code == 200
    assert ord1_detail.json()["status"] == "CARRY_OVER_PENDING"

    # 5. Test EOD Expire (for remaining PENDING order)
    eod_resp = await client.post("/api/v1/orders/eod/expire")
    assert eod_resp.status_code == 200
    assert eod_resp.json()["expired_count"] >= 1

    ord2_detail = await client.get(f"/api/v1/orders/{order_id2}")
    assert ord2_detail.json()["status"] == "EXPIRED_EOD"


@pytest.mark.asyncio
async def test_signal_text_endpoint(client: AsyncClient, auth_headers):
    text = "BUY ADVANC @ 250.00 Vol: 200"
    payload = {
        "text": text,
        "auto_execute": True
    }
    resp = await client.post("/api/v1/webhook/signal-text", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["immediate_orders"]) == 1
    assert len(data["queued_order_ids"]) == 1
