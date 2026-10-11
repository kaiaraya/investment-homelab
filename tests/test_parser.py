import pytest
from app.services.parser import SignalIntelligenceParser
from app.schemas.order import OrderSide

SAMPLE_STRATEGY_TEXT = """
🚨 5.1 Hard Exit & Cut Loss Triggers (3 ไม้ + เศษหุ้น 1 ไม้):
TLI: [SELL 2,000 หุ้น] | ถือมา 16 วันทำการ (-1.77%, ทุน ฿11.30 ➡️ ตลาด ฿11.10) ➡️ SELL ปิดสถานะทั้งหมด 2,000 หุ้น: V3S Hard Time-Exit ปิดเมื่อครบ 10 วันทำการ เพื่อคืนเงินสด ฿22,200 หมุนรอบใหม่
MCOT: [SELL 3,400 หุ้น] | ติดลบ -3.51% (ทุน ฿5.70 ➡️ ตลาด ฿5.50) ➡️ SELL Cut Loss ทั้งหมด 3,400 หุ้น: V3S Stop Loss ทันทีตามวินัยจำกัดความเสี่ยง 2.0%
GLOBAL: [SELL 5,500 หุ้น] | ติดลบ -2.86% (ทุน ฿7.00 ➡️ ตลาด ฿6.80) ➡️ SELL Cut Loss ทั้งหมด 5,500 หุ้น: V3S Stop Loss ทันทีตามวินัยจำกัดความเสี่ยง 2.0%
TRUE (เศษหุ้น): [SELL 100 หุ้น] | ติดลบ -0.76% (ถือ 8 วันทำการ, ทุน ฿13.20 ➡️ ตลาด ฿13.10) ➡️ SELL ปิดเศษหุ้น 100 หุ้น: Weed-Out เคลียร์หน้าพอร์ต
🟢 5.2 Climax TP & Strong Runners (4 ไม้):
DELTA: [มีทั้งหมด 200 หุ้น] | กำไร +12.65% (ทุน ฿245.00 ➡️ ตลาด ฿276.00) ➡️ 🎯 Climax TP Zone:แผนแบ่งล็อกกำไร: SELL ครึ่งนึง 100 หุ้น (ล็อกกำไรเข้าพอร์ต +฿3,100) และ HOLD อีก 100 หุ้น โดยยก Trailing Stop ล็อกที่ ฿265.00
แผนรันต่อทั้งก้อน: HOLD ทั้งหมด 200 หุ้น โดยตั้ง Trailing Stop ดักไว้ที่ ฿265.00 (หากหลุดค่อย SELL 200 หุ้น)
SINGER (ไม้ 1): [HOLD 3,700 หุ้น] | กำไร +4.85% (ทุน ฿10.30 ➡️ ตลาด ฿10.80) ➡️ HOLD 3,700 หุ้น: ยก Trailing Stop ล็อกต้นทุนที่ ฿10.30 รันเทรนด์ต่อ
FORTH: [HOLD 2,500 หุ้น] | กำไร +4.79% (ทุน ฿14.60 ➡️ ตลาด ฿15.30) ➡️ HOLD 2,500 หุ้น: ยก Trailing Stop ล็อกต้นทุนที่ ฿14.60 รันเทรนด์ต่อ
CKP: [HOLD 16,000 หุ้น] | กำไร +2.54% (ทุน ฿2.36 ➡️ ตลาด ฿2.42) ➡️ HOLD 16,000 หุ้น: ยก Trailing Stop ล็อกต้นทุนที่ ฿2.36 รันเทรนด์ต่อ
🟢 5.3 Active Swings & Watchlist (14 ไม้):
Active Swings (เกาะทุน/บวกช่วงต้น — ถือรันตามรอบ 10 วันทำการ):
JMT: [HOLD 3,500 หุ้น] | กำไร +1.92% (ทุน ฿10.40 ➡️ ฿10.60) — Stop Loss: ฿10.15
SINGER (ไม้ 2): [HOLD 3,700 หุ้น] | กำไร +1.89% (ทุน ฿10.60 ➡️ ฿10.80) — Stop Loss: ฿10.35
AEONTS: [HOLD 400 หุ้น] | กำไร +1.29% (ทุน ฿97.25 ➡️ ฿98.50) — Stop Loss: ฿95.25
MC: [HOLD 3,500 หุ้น] | กำไร +0.89% (ทุน ฿11.20 ➡️ ฿11.30) — Stop Loss: ฿10.95
AOT (ไม้ 1): [HOLD 600 หุ้น] | กำไร +0.40% (ทุน ฿62.25 ➡️ ฿62.50) — Stop Loss: ฿61.00
UVAN: [HOLD 2,700 หุ้น] | เสมอทุน 0.00% (ทุน ฿14.20 ➡️ ฿14.20, ถือ 5/10 วัน) — Stop Loss: ฿13.90
TFM (ไม้ 2): [HOLD 6,300 หุ้น] | เสมอทุน 0.00% (ทุน ฿6.20 ➡️ ฿6.20) — Stop Loss: ฿6.05
Watchlist (ปริ่ม Stop 2% รอ Weed-Out หากหลุดเกณฑ์):
AOT (ไม้ 2): [HOLD 600 หุ้น] | ติดลบ -1.96% (ทุน ฿63.75 ➡️ ฿62.50) ➡️ SELL 600 หุ้น ทันทีหากราคาหลุด ฿62.25
TFM (ไม้ 1): [HOLD 4,500 หุ้น] | ติดลบ -1.59% (ทุน ฿6.30 ➡️ ฿6.20) ➡️ SELL 4,500 หุ้น ทันทีหากราคาหลุด ฿6.15
TIDLOR: [HOLD 2,000 หุ้น] | ติดลบ -1.05% (ทุน ฿19.00 ➡️ ฿18.80) ➡️ SELL 2,000 หุ้น ทันทีหากราคาหลุด ฿18.60
PTG (SHORT): [HOLD 6,400 หุ้น] | ติดลบ -0.64% (ทุน Short ฿7.85 ➡️ ฿7.90) ➡️ COVER 6,400 หุ้น ทันทีหากราคาทะลุ ฿8.00
AP (SHORT): [HOLD 5,000 หุ้น] | ติดลบ -0.62% (ทุน Short ฿8.10 ➡️ ฿8.15) ➡️ COVER 5,000 หุ้น ทันทีหากราคาทะลุ ฿8.25
VIH: [HOLD 4,600 หุ้น] | ติดลบ -0.59% (ทุน ฿8.45 ➡️ ฿8.40) ➡️ SELL 4,600 หุ้น ทันทีหากราคาหลุด ฿8.25
CPALL: [HOLD 800 หุ้น] | ติดลบ -0.54% (ทุน ฿46.25 ➡️ ฿46.00, ถือ 6 วัน) ➡️ SELL 800 หุ้น ทันทีหากราคาหลุด ฿45.25
"""


def test_parse_single_simple_signal():
    parser = SignalIntelligenceParser()
    text = "BUY TRUE @ 13.20 Vol: 3800"
    res = parser.parse_text(text)
    assert len(res.immediate_orders) == 1
    ord0 = res.immediate_orders[0]
    assert ord0.symbol == "TRUE"
    assert ord0.side == OrderSide.BUY
    assert ord0.volume == 3800
    assert ord0.price == 13.20
    assert ord0.is_valid_lot is True


@pytest.mark.asyncio
async def test_parse_multi_stock_tpsl():
    parser = SignalIntelligenceParser()
    thai_msg = "ตัว CPALL ตั้ง TP 68 SL 62 นะ ส่วนตัวที่ Short AP ไว้ ให้ TP 7.50 SL 8.10 แล้วก็ HMPRO ขายทำกำไรที่ 10 บาท คัทลอส 9.20"
    res = await parser.parse_multi_stock_tpsl(thai_msg)

    assert len(res.items) == 3
    items_by_sym = {item.symbol: item for item in res.items}

    assert "CPALL" in items_by_sym
    assert items_by_sym["CPALL"].side == "LONG"
    assert items_by_sym["CPALL"].take_profit == 68.0
    assert items_by_sym["CPALL"].stop_loss == 62.0

    assert "AP" in items_by_sym
    assert items_by_sym["AP"].side == "SHORT"
    assert items_by_sym["AP"].take_profit == 7.50
    assert items_by_sym["AP"].stop_loss == 8.10

    assert "HMPRO" in items_by_sym
    assert items_by_sym["HMPRO"].side == "LONG"
    assert items_by_sym["HMPRO"].take_profit == 10.0
    assert items_by_sym["HMPRO"].stop_loss == 9.20

