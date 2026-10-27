// Liberator cancel order via POST /va/order/cancelled → re-read (anti-mock)
// arg: {orderNo, pin}
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const getTok = () => { const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/); return m ? decodeURIComponent(m[1]) : null; };
    const tok = getTok();
    if (!tok) return { ok: false, step: 'auth', error: 'NO_API_TOKEN' };

    const H = { 'content-type': 'application/json', 'authorization': 'Bearer ' + tok };
    const base = 'https://webtrade.liberator.co.th';

    const orderNo = String(raw.orderNo || '');
    const pin = String(raw.pin || '');
    if (!orderNo) return { ok: false, step: 'validate', error: 'NO_ORDER_NO' };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const can = await fetch(base + '/va/order/cancelled', { method: 'POST', headers: H, body: JSON.stringify({ orderNo: [orderNo], pin }) });
    const canJson = await can.json();
    if (canJson.errorCode !== 0) return { ok: false, step: 'cancel', errorCode: canJson.errorCode, errMsg: canJson.errMsg };

    const read = await fetch(base + '/va/order', { method: 'POST', headers: H, body: JSON.stringify({ accountNo: '70559382' }) });
    const readJson = await read.json();
    const list = readJson.result?.list || [];
    const match = list.find(o => String(o.orderNo) === orderNo);
    return { ok: true, orderNo, cancelled: match ? match.cancelled : null, balance: match ? match.balance : null, verified: !!(match && (match.cancelled > 0 || match.status === 'XC' || match.balance === 0)), list };
})()
