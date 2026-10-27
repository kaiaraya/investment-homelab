# TASK-jsfirst-0a-endpoint-map — Streaming / SBL / Liberator Endpoint Map

**Status:** DONE · read + order/change/cancel จับครบ (2026-10-26 ~11:52 +07)
**Source HAR:** `data/har/kss_all.har` · `data/har/liberator_all.har` · `data/har/liberator_order_all.har` · `data/har/kss_change_all.har`
**Source JSON:** `data/har/kss_endpoints.json` · `data/har/liberator_endpoints.json` · `data/har/liberator_order_endpoints.json` · `data/har/kss_change_endpoints.json`
**Captured at:** 2026-10-26 ~09:20 read · ~11:45–11:52 order/change/cancel (+07) บน CDP 9333 (kss) / 9334 (liberator)

---

## 1. Settrade Streaming (Krungsri SSO → StreamingPage.jsp)

| Action | Method | Endpoint | Payload | Response |
|---|---|---|---|---|
| **Place order** | POST | `https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/orders` | `{"side":"Cover-Buy","symbol":"TU","trusteeIdType":"Local","volume":3100,"price":12.7,"priceType":"Limit","validityType":"Day","bypassWarning":false,"pin":"******","positionType":""}` | `{"orderNo":11008566}` |
| **Cancel order** | PATCH | `https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/cancel` | `{"orders":[{"sequenceNo":"0","orderNo":"11007722","symbol":"TU","tradeDate":"2026-10-26"}],"pin":"******"}` | `{"results":[{"orderNo":"11007722","errorResponse":null,"httpStatus":"OK","httpStatusCode":200}]}` |
| Account info (read) | GET | `apigw.settrade.com/api/dgw/v3/029/accounts/3024952` | — | `{brokerId, accountNo, accountType:"CASH_ACCOUNT", creditLimit, cashBalance, lineAvailable, canTradeSBL:false, name, …}` |
| Open orders (read) | GET | `apigw.settrade.com/api/dgw/v3/029/accounts/3024952/orders` | — | `[]` (array ของ order) |
| Client account info | GET | `apigw.settrade.com/api/ereport/v3/029/client-account-info/3024952` | — | account metadata |
| Equity account info | GET | `wen045.settrade.com/realtime/getEquityAccountInformation.jsp?json=true` | — | `{result:"T", tradeNo:"3024952", turnoverList:[…]}` |
| Quote static (read) | GET | `apigwcld.settrade.com/api/marketdata/v4/029/static-data/{SYMBOL}?market=E` | — | `{ceiling, floor, last, close, firstBid, firstAsk, priceDigit, spreadList:[{lowerLimit,tick}]}` |
| Market-data auth token | GET | `apigwcld.settrade.com/api/market-data-auth/v1/token?service=DISPATCHER&codeChallenge=…` | — | `{token: "eyJ…"}` |
| Live quote stream | WS | `wss://apigwcld-i.settrade.com/websocket/dispatch?userRef=7123638&brokerId=029&codeVerifier=…` | frames | realtime bid/offer/tick |
| App init | POST | `wme2.settrade.com/realtime/streaming7/data/initData.jsp` | form-encoded | `{itpdRole, favouriteList:[…], …}` |
| **Change order (native in-place)** | PATCH | `https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/orders/{orderNo}/change` | `{"bypassWarning":false,"newVolume":100,"pin":"******","tradeDate":"26/10/2026","newPrice":6.7}` | re-read ยืนยัน `price` เปลี่ยนบน orderNo เดิม (ไม่สร้าง orderNo ใหม่) — จับ 2026-10-26 11:50 |

**Account switch (สำคัญ):** Streaming เปิดที่ `3024952` (Equity/Cash, `accountType=CASH_ACCOUNT`). Short/Cover ต้องสลับเป็น Margin `3024959` ก่อน (dropdown `div.position-relative.cursor-pointer` → `li:has-text("3024959")`) — endpoint ตัว account จะเป็น `accounts/3024959` หลังสลับ

---

## 2. Krungsri SBL Real Time (`sblweb/MainSBL.aspx`)

ASP.NET WebForms + Telerik. **ทุก action = POST กลับหน้าเดิม** `https://www.krungsrisecurities.com/sblweb/MainSBL.aspx` พร้อม payload:

| Field | ค่า |
|---|---|
| `__EVENTTARGET` | `ctl00$MainCenter$lbXD` / `lbSet50` / `lbSet100` / `lbNewSec` / `lbRefresh` / `lbBorrow` / return-button id |
| `__VIEWSTATE` | base64 (ใหญ่, state ของหน้า) |
| `__VIEWSTATEGENERATOR` | ค่า fix |
| `ctl00$ctl09` | `ctl00$MainCenter$up1|ctl00$MainCenter$lbXD` (UpdatePanel trigger) |
| `ctl09_TSM` | Telerik ScriptManager token (`;;System.Web.Extensions,Version=4.0.0.0,…`) |
| `__EVENTARGUMENT` / `__LASTFOCUS` | ตาม action |

Response = `1|#||4|5847|updatePanel|MainCenter_up1|` + HTML บางส่วน (XD/XR table, inventory SET50/100, borrow panel)

| Action | Selector | PostBack `__EVENTTARGET` |
|---|---|---|
| Tab SET50 / SET100 / NEW SEC / XD,XR | `#MainCenter_lbSet50` / `lbSet100` / `lbNewSec` / `lbXD` | `ctl00$MainCenter$lbXxx` |
| Refresh | `#MainCenter_lbRefresh` | `ctl00$MainCenter$lbRefresh` |
| Borrow | `#MainCenter_lbBorrow` (fill `#ctl00_MainCenter_txtSymbol` + `txtQty`) | `ctl00$MainCenter$lbBorrow` |
| Return | `a[id*='RadReturn']` (per row) | row-scoped |
| **PP / inventory read** | ✅ จับแล้ว (หน้าโหลด + tab click) | — |

---

## 3. Liberator WebTrade (`webtrade.liberator.co.th`)

REST JSON API ล้วน — `accountNo` (ใช้ใน payload) = **70559382** (8 หลัก, CASH BALANCE); `investorId` = **7055938** (7 หลัก). อ่านจาก `GET /va/profile` (UI ไม่แสดง accountNo โดยตรง)

| Action | Method | Endpoint | Payload | Response |
|---|---|---|---|---|
| Profile | GET | `/va/profile` | — | user info |
| Config | GET | `/va/webtrade-config`, `/vb/config` | — | app config |
| **Portfolio (read)** | POST | `/va/portfolio` | `{"accountNo":"70559382"}` | `{errorCode, result:{list:[], stock:[]}}` |
| **Open orders (read)** | POST | `/va/order` | `{"accountNo":"70559382"}` | `{errorCode, result:{list:[]}}` |
| **Quote bid/offer (10 level)** | POST | `/vb/stock/bid-offer` | `{"orderBookId":66234}` | `{result:{data:{bp[10],bv[10],op[10],ov[10]}}}` |
| Stock info | POST | `/vb/stock/info` | `{"orderBookIds":[66234]}` | `{result:{list:[{n:"BCPG",l,chg,bp,bv,op,ov,cl,fl,…}]}}` |
| Market index / status | GET | `/vb/market/index`, `/vb/status/set` | — | market data |
| Notifications | POST | `/va/noti` | — | noti list |
| **Place (pre-check)** | POST | `/va/order/pre-place` | `{"accountNo":"70559382","icebergVol":0,"volume":100,"symbol":"BCPG","side":"Buy","pin":"******","price":6.75,"priceType":"Limit","validityType":"Day","nvdr":false,"ip":""}` | `{result:{list:[{key:"Total",value:"675.00"},{key:"Commission Fee + VAT",value:"0.36"},{key:"Net Buy",value:"675.41"}]}}` |
| **Place (submit)** | POST | `/va/order/place` | payload ข้างบน + `"tstamp":"2026-10-26 11:45:46.022"` | `{"errorCode":0,"errMsg":"","result":{"data":[]}}` แล้ว re-read `POST /va/order` |
| **Change (in-place)** | PUT | `/va/order` | `{"orderNo":"16723","volume":100,"pin":"******","price":6.7,"ip":""}` | `{"errorCode":0,"errMsg":"","result":{"data":[]}}` — orderNo เดิมคงอยู่ (native amend, ไม่ cancel+replace) |
| **Cancel** | POST | `/va/order/cancelled` | `{"orderNo":["16723"],"pin":"******"}` | `{"errorCode":0,"errMsg":"","result":{"data":[]}}` |

> `orderBookId` ของ BCPG = `66234` (มาจาก `/vb/stock/info` หรือ symbol search)

---

## 4. Replayable? (nonce/sign/CSRF)

| Surface | Verdict |
|---|---|
| Settrade Streaming REST | ✅ replayable ตรงๆ (JWT/SSO cookie จาก session; ไม่มี nonce ต่อ request) — Place (`POST /orders`) และ Cancel (`PATCH /cancel`) ได้รับการ capture + confirm แล้ว พร้อม payload structure |
| Settrade live quote | ⚠️ websocket ต้องขอ `market-data-auth/v1/token` (PKCE `codeChallenge/codeVerifier`) ก่อน |
| SBL WebForms | ⚠️ ต้องยิง `__VIEWSTATE` + `ctl09_TSM` (Telerik token) + Anticsrf — ต้อง re-read state จากหน้าแล้วยิงกลับ (stateful PostBack) |
| Liberator REST | ✅ replayable ตรงๆ — auth = `Authorization: Bearer <api-token>` header (JWT ~210 chars; เก็บ client-side เป็น cookie `api-token` แล้ว JS อ่านส่งเป็น header — **ทุก request มี header นี้ ไม่มี cookie header**) · ไม่มี nonce ต่อ request · PIN field ยืนยันแล้ว: place/change/cancel ทุก payload มี `"pin"` ชัดเจน · **accountNo ต้อง 8 หลัก `70559382`** (ส่ง 7 หลัก `7055938` → `Error AccessAuthen: The given key was not present in the dictionary`) |

---

## 5. TODO (order/change/cancel capture — market open)

- [x] Streaming: place BUY BCPG passive → จับ POST → change (native PATCH `/change`) → จับ → cancel → จับ (2026-10-26 11:50)
- [ ] Streaming: (optional) SHORT ถ้ามีหุ้นยืม → จับ POST (ยังไม่ทำ — ไม่มีหุ้นยืมให้ยิง)
- [ ] SBL: borrow 100 → จับ PostBack → return → จับ PostBack (optional, minimal fee — ข้าม)
- [x] Liberator: place BUY BCPG passive → จับ POST → change (PUT `/va/order`) → จับ → cancel (POST `/va/order/cancelled`) → จับ (2026-10-26 11:45)
- [x] อัปเดตตารางข้างบน + เติมช่อง "replayable?" ให้ครบ
