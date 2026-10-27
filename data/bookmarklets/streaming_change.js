// Settrade Streaming (KSS) native change in-place via PATCH .../orders/{orderNo}/change
// → re-read the same orderNo (anti-mock). Mirrors data/bookmarklets/liberator_change.js.
// arg: {orderNo, price, volume, pin, tradeDate?, acct?}
// Contract: data/har/kss_change_all.har (2026-10-26 11:50, live market).
//   PATCH https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/orders/{orderNo}/change
//   body {"bypassWarning":false,"newVolume":100,"pin":"******","tradeDate":"26/10/2026","newPrice":6.7}
//   auth = SSO cookie only (no nonce/CSRF) · 200 returns an EMPTY body (verify by re-read)
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const acct = String(
        raw.acct ||
        (document.body.innerText.match(/3024\d{3}/) || [])[0] ||
        ''
    );
    if (!acct) return { ok: false, step: 'auth', error: 'NO_ACCOUNT' };

    const orderNo = String(raw.orderNo || '');
    const price = parseFloat(raw.price);
    const volume = parseInt(raw.volume || 0, 10);
    const pin = String(raw.pin || '');
    const d = new Date();
    const tradeDate = String(raw.tradeDate || `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`);

    if (!orderNo) return { ok: false, step: 'validate', error: 'NO_ORDER_NO' };
    if (!(price > 0)) return { ok: false, step: 'validate', error: 'INVALID_PRICE' };
    if (!volume || volume <= 0) return { ok: false, step: 'validate', error: 'INVALID_VOLUME' };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const base = 'https://apigw.settrade.com/api/dgw/v3/029/accounts/' + acct;
    const chg = await fetch(
        `${base}/orders/${encodeURIComponent(orderNo)}/change`,
        {
            method: 'PATCH',
            credentials: 'include',
            headers: {
                'accept': 'application/json, text/plain, */*',
                'content-type': 'application/json',
                'clientversion': '4.0.0',
                'terminal': 'streaming',
            },
            body: JSON.stringify({ bypassWarning: Boolean(raw.bypassWarning || false), newVolume: volume, pin, tradeDate, newPrice: price }),
        }
    );
    let chgBody = '';
    try { chgBody = (await chg.text()) || ''; } catch (e) { chgBody = ''; }
    if (!chg.ok) return { ok: false, step: 'change', httpStatus: chg.status, body: chgBody.slice(0, 400) };

    const read = await fetch(`${base}/orders`, { credentials: 'include' });
    if (!read.ok) return { ok: false, step: 'verify', error: 'READ_FAILED', httpStatus: read.status };
    const list = await read.json();
    const match = (Array.isArray(list) ? list : []).find(o => String(o.orderNo) === orderNo);
    if (!match) return { ok: false, step: 'verify', error: 'ORDER_NOT_FOUND', orderNo };
    const statusText = String(match.showOrderStatus || match.status || '').toUpperCase();
    if (statusText.includes('CANCEL') || ['X', 'R'].includes(String(match.status || '').toUpperCase())) {
        return { ok: false, step: 'verify', error: 'ORDER_NOT_OPEN', status: statusText, orderNo };
    }
    const verified = Math.abs(parseFloat(match.price || 0) - price) <= 0.005;
    return {
        ok: verified,
        step: verified ? 'verified' : 'verify',
        orderNo,
        acct,
        changedPrice: match.price,
        changedVolume: match.vol,
        verified,
        error: verified ? undefined : `PRICE_MISMATCH:${match.price}`,
        list,
    };
})()
