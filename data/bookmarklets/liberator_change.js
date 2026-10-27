// Liberator change order in-place via PUT /va/order → re-read (anti-mock)
// arg: {orderNo, price, volume, pin}
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const getTok = () => { const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/); return m ? decodeURIComponent(m[1]) : null; };
    const tok = getTok();
    if (!tok) return { ok: false, step: 'auth', error: 'NO_API_TOKEN' };

    const H = { 'content-type': 'application/json', 'authorization': 'Bearer ' + tok };
    const base = 'https://webtrade.liberator.co.th';

    const orderNo = String(raw.orderNo || '');
    const price = parseFloat(raw.price);
    const volume = parseInt(raw.volume || 0, 10);
    const pin = String(raw.pin || '');
    if (!orderNo) return { ok: false, step: 'validate', error: 'NO_ORDER_NO' };
    if (!(price > 0)) return { ok: false, step: 'validate', error: 'INVALID_PRICE' };
    if (!volume || volume <= 0) return { ok: false, step: 'validate', error: 'INVALID_VOLUME' };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const chg = await fetch(base + '/va/order', { method: 'PUT', headers: H, body: JSON.stringify({ orderNo, volume, pin, price, ip: '' }) });
    const chgJson = await chg.json();
    if (chgJson.errorCode !== 0) return { ok: false, step: 'change', errorCode: chgJson.errorCode, errMsg: chgJson.errMsg };

    const read = await fetch(base + '/va/order', { method: 'POST', headers: H, body: JSON.stringify({ accountNo: '70559382' }) });
    const readJson = await read.json();
    const list = readJson.result?.list || [];
    const match = list.find(o => String(o.orderNo) === orderNo);
    return { ok: true, orderNo, changedPrice: match ? match.price : null, verified: !!(match && parseFloat(match.price) === price), list };
})()
