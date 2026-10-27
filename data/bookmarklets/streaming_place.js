// Settrade Streaming (KSS) place order via POST /api/dgw/v3/029/accounts/{acct}/orders
// → re-read orders (Anti-Mock).
// arg: {symbol, side: 'BUY'|'SELL'|'SHORT'|'COVER'|'Buy'|'Sell'|'Cover-Buy'|'Short-Sell', volume, price, pin, dryRun?, acct?}
// Contract captured live: data/har/place_cover_captured.json & TASK-jsfirst-0a-endpoint-map.md
//   POST https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/orders
//   body: {side: 'Cover-Buy'|'Short-Sell'|'Buy'|'Sell', symbol, trusteeIdType: 'Local', volume, price, priceType: 'Limit', validityType: 'Day', bypassWarning: false, pin, positionType: ''}
//   SSO session cookie auth (credentials: 'include')
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const acct = String(
        raw.acct ||
        (document.body.innerText.match(/3024\d{3}/) || [])[0] ||
        ''
    );
    if (!acct) return { ok: false, step: 'auth', error: 'NO_ACCOUNT' };

    const symbol = String(raw.symbol || '').trim().toUpperCase();
    const sideRaw = String(raw.side || '').trim().toUpperCase();
    let side = 'Buy';
    if (sideRaw === 'COVER' || sideRaw === 'COVER-BUY' || sideRaw === 'C') {
        side = 'Cover-Buy';
    } else if (sideRaw === 'SHORT' || sideRaw === 'SHORT-SELL' || sideRaw === 'H' || sideRaw === 'SBL') {
        side = 'Short-Sell';
    } else if (sideRaw === 'SELL' || sideRaw === 'S') {
        side = 'Sell';
    } else {
        side = 'Buy';
    }

    const volume = parseInt(raw.volume || 0, 10);
    const price = parseFloat(raw.price);
    const pin = String(raw.pin || '');
    const dryRun = Boolean(raw.dryRun);

    if (!symbol) return { ok: false, step: 'validate', error: 'NO_SYMBOL' };
    if (!volume || volume <= 0 || volume % 100 !== 0) return { ok: false, step: 'validate', error: 'INVALID_VOLUME', volume };
    if (!(price > 0)) return { ok: false, step: 'validate', error: 'INVALID_PRICE', price };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const base = 'https://apigw.settrade.com/api/dgw/v3/029/accounts/' + acct;
    const payload = {
        side,
        symbol,
        trusteeIdType: 'Local',
        volume,
        price,
        priceType: 'Limit',
        validityType: 'Day',
        bypassWarning: false,
        pin,
        positionType: '',
    };

    if (dryRun) {
        return { ok: true, dryRun: true, preview: payload, acct };
    }

    const res = await fetch(`${base}/orders`, {
        method: 'POST',
        credentials: 'include',
        headers: {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'clientversion': '4.0.0',
            'terminal': 'streaming',
        },
        body: JSON.stringify(payload),
    });

    let resBody = '';
    try { resBody = await res.text(); } catch (e) { resBody = ''; }
    let resJson = null;
    try { resJson = JSON.parse(resBody); } catch (e) { resJson = null; }

    if (!res.ok) {
        return { ok: false, step: 'place', httpStatus: res.status, body: resBody.slice(0, 400), error: resJson?.message || 'PLACE_FAILED' };
    }

    // Anti-Mock: re-read orders list from same DGW endpoint
    const read = await fetch(`${base}/orders`, { credentials: 'include' });
    if (!read.ok) {
        return { ok: false, step: 'verify', error: 'READ_FAILED', httpStatus: read.status, rawResponse: resJson || resBody };
    }
    const list = await read.json();
    const orders = Array.isArray(list) ? list : [];

    // Normalize side check
    const match = orders.find(o => {
        if (String(o.symbol || '').toUpperCase() !== symbol) return false;
        const oSide = String(o.side || '').toUpperCase();
        const targetSide = side.toUpperCase();
        if (oSide !== targetSide && !oSide.startsWith(targetSide.slice(0, 4))) return false;
        if (Math.abs(parseFloat(o.price || 0) - price) > 0.005) return false;
        const statusText = String(o.showOrderStatus || o.status || '').toUpperCase();
        return !statusText.includes('CANCEL') && !['X', 'R'].includes(String(o.status || '').toUpperCase());
    });

    const orderNo = match ? String(match.orderNo || match.orderNoSeos || '') : null;
    const verified = !!match && !!orderNo;
    return {
        ok: verified,
        step: verified ? 'verified' : 'verify',
        acct,
        orderNo: orderNo || (resJson?.orderNo ? String(resJson.orderNo) : null),
        symbol,
        side,
        price,
        volume,
        verified,
        error: verified ? undefined : 'ANTI_MOCK_VERIFY_FAILED',
        rawResponse: resJson || resBody,
        list,
    };
})()
