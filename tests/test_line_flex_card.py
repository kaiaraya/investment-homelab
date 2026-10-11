import pytest
from app.services.line_service import line_service

def test_build_batch_flex_message():
    sample_batch = {
        "batch_id": "B-TEST1234",
        "card": {
            "batch_id": "B-TEST1234",
            "title": "Batch Review",
            "immediate_orders": [
                {"symbol": "TRUE", "side": "SELL", "volume": 100, "price": 13.10},
                {"symbol": "TIDLOR", "side": "SELL", "volume": 2000, "price": 18.20},
                {"symbol": "AOT", "side": "SELL", "volume": 600, "price": 62.25},
                {"symbol": "TFM", "side": "SELL", "volume": 4500, "price": 6.15}
            ],
            "triggers_count": 4,
            "warnings": ["⚠️ Warning 1"]
        }
    }
    
    flex = line_service._build_batch_flex_message(sample_batch)
    assert flex["type"] == "flex"
    assert "altText" in flex
    bubble = flex["contents"]
    assert bubble["type"] == "bubble"
    assert bubble["header"]["type"] == "box"
    assert bubble["body"]["type"] == "box"
    assert bubble["footer"]["type"] == "box"
    
    # Check action buttons
    buttons = bubble["footer"]["contents"]
    assert len(buttons) == 2
    assert "action=batch_approve&batch_id=B-TEST1234" in buttons[0]["action"]["data"]
    assert "action=batch_cancel&batch_id=B-TEST1234" in buttons[1]["action"]["data"]
    
    # Check quick reply
    assert "quickReply" in flex
