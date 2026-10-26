# TASK-loop2-test-and-witness — Test Matrix (T0/T1/T2/HITL) + Probe Gaps

**Status:** PLAN — APPROVED 2026-10-21 · **Owner:** Argon · **Board:** `investment-homelab`
**ที่มา:** Loop 2 implementation เสร็จใน working tree (123 tests ผ่าน, rich menu render OK 2500x1686)
— เอกสารนี้คือ **แผนทดสอบ/พยาน** ที่ปิดช่องว่างก่อนปิด Loop 2

---

## 1. ผลตรวจ implementation (ของจริง ไม่ใช่ self-report)

| ส่วน | สถานะ | หลักฐาน |
|---|---|---|
| Async Queue | ✅ ต่อจริง | `line_service.py:218` enqueue, OTP อยู่ก่อน CLI (sync), `/halt` bypass |
| Value-based sizing | ✅ ต่อจริง | `handlers.py:1355` floor 100 หุ้น, `resolved_volume/price` เข้า draft |
| SBL commands | ✅ dispatch ครบ | `SblCommand/Borrow/Return` → handlers 1686/1762/1813 |
| SBL realtime driver | ⚠️ **live = stub** | `execute_sbl_borrow` คืน `LIVE_SBL_NOT_IMPLEMENTED` เมื่อ `DRY_RUN_MODE=false` |
| Rich Menu | ⚠️ render ได้, upload ไม่เคยรัน | PNG 2500x1686 ✅ · LINE API ยังไม่พิสูจน์ |
| Postback reply-token | ✅ แก้แล้ว | `_send_or_push` ใช้ push ไม่ reuse token |
| Tests | ✅ 123 passed | 6 suites (queue/sbl/handlers_sbl/value/order_draft/trade_parser) |

## 2. บั๊ก/ช่องว่างที่เจอ (ต้องแก้ก่อน witness)

| # | ระดับ | เรื่อง | ไฟล์ |
|---|---|---|---|
| G1 | 🔴 capital | `execute_confirmed_order(draft)` **ไม่ส่ง `last_trade_price`** → `/short` ทาง LINE ได้ `E_NO_QUOTE` ทุกครั้ง (G6 พิสูจน์ไม่ได้) | `handlers.py` handle_postback |
| G2 | 🔴 anti-mock | DRY-RUN borrow **เขียน `SBLBorrowLot` สถานะ ACTIVE จริง** → `/sbl` เห็น lot ผี, `/short` ผ่าน E_NO_SBL ด้วยของปลอม | `handlers.py` sbl_borrow_confirm |
| G3 | 🟡 quote | value sizing ของ kss ใช้ `trademan_driver` (TradeMan REST) แต่ผู้ใช้ตัดสินให้ใช้ **CDP tab (`connect_cdp`)** = `streaming_driver` | `handlers.py:_broker_quote` |
| G4 | 🟡 XD | `check_symbol_risk` อ่าน cache `data/krungsri_sbl_realtime.json` — cache ว่าง/เก่า = XD block ผ่านเงียบ (fail-open) | `sbl_realtime_driver.py` |
| G5 | 🟡 live SBL | borrow/return live ยัง fail-closed stub — ต้องเขียน DOM flow จริงก่อน witness | `sbl_realtime_driver.py` |

## 3. Probe ที่ต้องทำเพิ่ม (STEP 0a — read-only ก่อน)

| Probe | ต้องรู้ | เหตุผล |
|---|---|---|
| **2.0a quote source** | TradeMan REST (`loadstockinformation`) คืน bid/offer depth จริงไหม vs `streaming_driver.get_market_bid_offer()` บน CDP tab | G3 · ตัดสิน canonical quote path (ผู้ใช้เลือก CDP) |
| **2.0b SBL submit flow** | selectors + post-submit row shape ของ borrow (`#MainCenter_lbBorrow`) และ return (`a[id*='RadReturn']`→`ShowReturnForm`) | G5 · เขียน live flow ให้ anti-mock ได้ |
| **2.0c Rich Menu API** | create/upload/alias/set-default sequence + status codes | upload ยังไม่เคยรัน |
| **2.0d webhook ack** | HTTP 200 latency จริง + push delivery + queue-full reject | queue ผ่านแค่ unit test |

## 4. Test Matrix — T0 / T1 / T2 / HITL

> **Timing / actor labels (up-front on every card title):**
> - `⏰ ปิดตลาด` — ทำได้ตลอด (code · unit test · docs · API ที่ไม่พึ่งราคา)
> - `🔔 เปิดตลาด` — ต้องมี quote/order/borrow สด (09:55–12:30 · 14:25–16:30 +07)
> - `🙋 Human วาง Order ก่อน` — ต้องมี order/lot/position ที่คนสร้างก่อน การ์ดจึงทดสอบได้

### 🟢 T0 (code-only, Jules 3.6 Flash / dispatcher)
| Card | Test ที่ต้องผ่าน | Done when |
|---|---|---|
| 2.1 SHORT quote wiring | `/short` draft → confirm → executor ได้ `last_trade_price`; SHORT dry-run ไม่ `E_NO_QUOTE` | unit + dry-run probe |
| 2.2 dry-run no phantom lot | DRY-RUN borrow **ไม่** สร้าง ACTIVE lot (หรือ status=DRY_RUN) | unit: `/sbl` ไม่เห็น lot หลัง dry-run |
| 2.3 rich menu upload | `setup_rich_menu.py --dry-run` + `--upload` idempotent | exit 0 + menuId |
| 2.4 postback+queue tests | 6 postback actions ผ่าน `_handle_postback`; OTP sync; `/halt` bypass; queue-full; timeout push | suite เขียว |

### 🟡 T1 (code-only, Jules 3.1 Pro)
| Card | Test | Done when |
|---|---|---|
| 2.5 SBL live borrow/return | DOM flow จริง + anti-mock re-read Ref.No + PIN + DRY_RUN + XD block + idempotency | unit + dry-run |
| 2.6 value edge cases | tick round, board-lot floor, budget ต่ำกว่า 100 หุ้น, E_NO_QUOTE, หน่วยติด (`50,000 บาท`) | unit ครบ |

### 🔴 T2 (live witness — human ที่จอ, blocked)
| Card | Witness | ผ่านเมื่อ |
|---|---|---|
| 2.7 value BUY | `/buy <sym> 50k` → card → confirm → executor (DRY_RUN แล้ว live เล็ก) | order no. จริงตรงจอ + DB `source=bot_cdp` |
| 2.8 SBL cycle | `/borrow` → `/short` → `/return` บน kss MARGIN 3024959 (PIN) | Ref.No จริง + lot ตรง + คืนแล้วปิด |
| 2.9 rich menu + postback | ติดเมนูบนมือถือ → กด Quick Trade → card → draft | เห็นเมนูจริง + card 4 ปุ่ม |

### 🟠 HITL (human taps — blocked)
| Card | ทดสอบ | ผ่านเมื่อ |
|---|---|---|
| 2.10 confirm/cancel TTL | กดยืนยัน/ยกเลิก + ปล่อยหมดอายุ 3 นาที | ไม่มี double reply, cancel drops draft, expired แจ้งถูก |
| 2.11 XD hard-block | ยืม/ชอร์ตหุ้นที่อยู่ใน XD list | ถูกบล็อกพร้อมเหตุผล 100% compensation |

## 5. Dependency map

```
2.0a ─► 2.1 ─► 2.6 ─► 2.7 ─► 2.10
2.0b ─► 2.5 ─► 2.8 ─► 2.11
2.0c ─► 2.3 ─► 2.9
2.2 ─────────► 2.8
2.4 ─────────► 2.9
```
**Parallel-safe:** 2.1 ∥ 2.2 ∥ 2.3 ∥ 2.4 (คนละไฟล์) · 2.5 ∥ 2.6
**ห้ามขนาน:** 2.1 กับ 2.6 (handlers.py) · 2.5 กับ 2.4 (handlers.py)
