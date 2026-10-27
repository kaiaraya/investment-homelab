// Liberator place order via /va/order/pre-place → /va/order/place → re-read (anti-mock)
// arg: {symbol, side: 'Buy'|'Sell', volume, price, pin, dryRun?, accountNo?}
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const getTok = () => { const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/); return m ? decodeURIComponent(m[1]) : null; };
    const tok = getTok();
    if (!tok) return { ok: false, step: 'auth', error: 'NO_API_TOKEN' };

    const H = { 'content-type': 'application/json', 'authorization': 'Bearer ' + tok };
    const base = 'https://webtrade.liberator.co.th';

    const symbol = String(raw.symbol || '').trim().toUpperCase();
    const sideRaw = String(raw.side || '').toUpperCase();
    const side = (sideRaw === 'SELL' || sideRaw === 'S') ? 'Sell' : 'Buy';
    const volume = parseInt(raw.volume || 0, 10);
    const price = parseFloat(raw.price);
    const pin = String(raw.pin || '');
    const dryRun = Boolean(raw.dryRun);
    const accountNo = String(raw.accountNo || '70559382');

    if (!symbol) return { ok: false, step: 'validate', error: 'NO_SYMBOL' };
    if (!volume || volume <= 0 || volume % 100 !== 0) return { ok: false, step: 'validate', error: 'INVALID_VOLUME', volume };
    if (!(price > 0)) return { ok: false, step: 'validate', error: 'INVALID_PRICE', price };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const payload = {
        accountNo, icebergVol: 0, volume, symbol, side, pin, price,
        priceType: 'Limit', validityType: 'Day', nvdr: false, ip: ''
    };

    const pre = await fetch(base + '/va/order/pre-place', { method: 'POST', headers: H, body: JSON.stringify(payload) });
    const preJson = await pre.json();
    if (preJson.errorCode !== 0) return { ok: false, step: 'pre-place', errorCode: preJson.errorCode, errMsg: preJson.errMsg };

    if (dryRun) return { ok: true, dryRun: true, preview: preJson.result };

    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    const tstamp = `${now.getFullYear()}-${p(now.getMonth()+1)}-${p(now.getDate())} ${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}.${String(now.getMilliseconds()).padStart(3,'0')}`;
    const place = await fetch(base + '/va/order/place', { method: 'POST', headers: H, body: JSON.stringify({ ...payload, tstamp }) });
    const placeJson = await place.json();
    if (placeJson.errorCode !== 0) return { ok: false, step: 'place', errorCode: placeJson.errorCode, errMsg: placeJson.errMsg };

    const read = await fetch(base + '/va/order', { method: 'POST', headers: H, body: JSON.stringify({ accountNo }) });
    const readJson = await read.json();
    const list = readJson.result?.list || [];
    const sideCode = side === 'Buy' ? 'B' : 'S';
    const match = list.find(o => o.symbol === symbol && o.side === sideCode && parseFloat(o.price) === price && o.status === 'PENDING');
    return { ok: true, preview: preJson.result, orderNo: match ? match.orderNo : null, verified: !!match, list };
})()
