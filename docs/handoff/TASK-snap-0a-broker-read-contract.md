# SNAP.0a — Broker Read-Only REST Endpoint Contract

Probe date: 2026-10-28 · fetched_at 03:58Z (≈10:58 +07, ตลาดเปิดช่วงเช้า)
Session: CDP daemon 9333 (Streaming) / 9334 (Liberator) — ล็อกอินอยู่แล้ว ไม่ OTP
Method: JS fetch ในหน้า (read-only) → HTTP 200 ทั้งหมด

`Probe: PROBE_DONE`

## 1. KSS / Krungsri — Settrade Streaming (brokerId=029)

Auth: `credentials:'include'` จากหน้า streaming (`wme2.settrade.com`) — cookie SSO ครอบ apigw.settrade.com

| Endpoint | ผล | ฟิลด์ยืนยัน |
|---|---|---|
| `GET apigw.settrade.com/api/dgw/v3/029/accounts/{acct}` | 200 | `brokerId, accountNo, accountType, creditLimit, cashBalance, lineAvailable, pp, ee, equity, equityBalance, purchasingPower, canTradeSBL, name` |
| `GET …/accounts/{acct}/portfolios?accountType={CREDIT_BALANCE\|CASH_ACCOUNT}` | 200 | `portfolioList[]: symbol, flag(B/S), nvdrFlag, marketPrice, amount, marketValue, profit, percentProfit, realizeProfit, startVolume, currentVolume, actualVolume, averagePrice, portFlag, marginRate` + `totalPortfolio` |
| `GET …/accounts/{acct}/orders` | 200 | array (ว่าง = ไม่มี order) |

### Live values (probe)
- **3024959 MARGIN** (`CREDIT_BALANCE`): creditLimit 1,200,000 · cashBalance 354,741.63 · lineAvailable 354,741.63 · pp 709,483.26 · ee/equity 354,741.63 · creditBalance=true
- **3024952 CASH** (`CASH_ACCOUNT`): creditLimit 500,000 · cashBalance 0 · lineAvailable 0 · name "Mr. ARAYA SAWASDICHAI"
- **Positions (MARGIN)**: AEONTS 600 · TU 3,100 (ledger volumes OK) — ⚠️ `marketPrice/marketValue/profit/averagePrice` = **0** (ดู caveat 3)
- **Orders**: `[]` ทั้งสอง account

### Reconcile ✓
- MARGIN: `lineAvailable == cashBalance` (354,741.63) — ไม่มี order ค้าง = ไม่มี block ✓ · `pp == 2×equity` ✓
- CASH: ว่างทั้ง portfolio/orders สอดคล้อง balance=0 ✓

## 2. Liberator (webtrade.liberator.co.th) — CASH BALANCE

Auth: **ต้อง** `Authorization: Bearer <api-token>` (อ่านจาก cookie `api-token` ตอนรัน — ห้าม hardcode) · cookie-only ได้ `Error AccessAuthen` (ยืนยันตาม skill)

| Endpoint | ผล | ฟิลด์ยืนยัน |
|---|---|---|
| `GET /va/profile` | 200 | `result.accounts[]: accountNo, type, creditLimit, lineAvailable, cashBalance, withdrawAvailable, investorId, marketVal, unrealizedPL, unrealizedPLPercent, realizedPL, stocks[]` |
| `POST /va/portfolio {accountNo}` | 200 | `result.list[]`, `result.stock[]` (ว่าง = ไม่มีหุ้น) |
| `POST /va/order {accountNo}` | 200 | `result.list[]` (ว่าง = ไม่มี order ค้าง) |

### Live values (probe)
- **70559382 CASH BALANCE**: creditLimit 500,000 · lineAvailable 225,877.48 · cashBalance 225,877.48 · withdrawAvailable 225,877.48 · investorId 7055938 · marketVal 0 · unrealizedPL 0
- positions / orders: ว่าง

### Reconcile ✓
- `lineAvailable == cashBalance == withdrawAvailable` (225,877.48) — ไม่มีหุ้น/order = ไม่มี block ✓

## 3. Caveats (ต้องรู้ก่อนเขียน SNAP.1)

1. **เลขบัญชี 2 รูป** — KSS: `3024959`=MARGIN, `3024952`=CASH (คนละ accountType ต้องแยก query) · LIB: API ใช้ `accountNo=70559382` (8 หลัก), ค่า investorId = `7055938` (7 หลัก) — ปกติทั้งสองฝั่ง ไม่งั้น /buy พัง
2. **Liberator read ต้อง Bearer** — `/va/portfolio`, `/va/order` (POST) ต้องส่ง header `Authorization: Bearer <api-token>` ไม่งั้นได้ `Error AccessAuthen` + list ว่าง (ยืนยันแล้ว: ใช้ Bearer → 200/errorCode 0)
3. **KSS market-price fields เป็น 0 ได้ทั้งที่ตลาดเปิด** — probe นี้ตอน 10:58 ตลาดเปิดอยู่ แต่ `marketPrice/marketValue/profit/averagePrice` = 0 ขณะที่ ledger fields (volumes, cost, creditLimit, lineAvailable) ถูกต้อง → field ที่ได้จาก realtime feed จะ 0 ถ้า daemon tab ไม่ได้ต่อ realtime/ws market-data auth สด. Snapshot ต้องถือว่า **ledger/cash/volume/order fields = authoritative** ส่วนราคาสดดึงจาก `marketdata/v4/029/static-data/{sym}` หรือยอมรับ 0 แล้ว flag `prices_stale` — ห้ามเอาค่า 0 ไปคำนวณ P/L จริง
4. **Fail-closed**: ถ้า endpoint ว่าง/status ≠ 200/session หมด → ออก non-zero สถานะชัด (ห้ามรายงาน "0 รายการ" ปลอม) · ทุก snapshot ปัก `fetched_at`

## 4. สรุป field ที่ snapshot ต้องเก็บ (read-only)

| ชุด | KSS | LIB |
|---|---|---|
| balance | accountType, creditLimit, cashBalance, lineAvailable, pp, ee, equity | type, creditLimit, lineAvailable, cashBalance, withdrawAvailable |
| positions | symbol, flag, currentVolume/actualVolume, averagePrice, (marketValue หลังต่อ feed) | stock[] (ถ้ามี) |
| open orders | orderNo, symbol, side, price, vol, matched, balance, status, validity | orderNo, symbol, side, price, volume, matched, balance, status |
| market status | — | `GET /vb/status/set?roleGroup=SET0300` → st |
