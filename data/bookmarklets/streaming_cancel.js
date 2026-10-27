// Settrade Streaming (KSS) cancel order via PATCH /api/dgw/v3/029/accounts/{acct}/cancel
// → re-read orders (Anti-Mock).
// arg: {orderNo, pin, symbol?, tradeDate?, acct?, dryRun?}
// Contract captured live: data/har/kss_cancel_ui_endpoints.json & TASK-jsfirst-0a-endpoint-map.md
//   PATCH https://apigw.settrade.com/api/dgw/v3/029/accounts/{acct}/cancel
//   body: {orders: [{sequenceNo: '0', orderNo: '11007722', symbol: 'TU', tradeDate: '2026-10-26'}], pin: '515286'}
//   response: {results: [{orderNo: '11007722', errorResponse: null, httpStatus: 'OK', httpStatusCode: 200}]}
//   SSO session cookie auth (credentials: 'include')
(async (arg) => {
    const raw = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const acct = String(
        raw.acct ||
        (document.body.innerText.match(/3024\d{3}/) || [])[0] ||
        ''
    );
    if (!acct) return { ok: false, step: 'auth', error: 'NO_ACCOUNT' };

    const orderNo = String(raw.orderNo || '').trim();
    const pin = String(raw.pin || '').trim();
    if (!orderNo) return { ok: false, step: 'validate', error: 'NO_ORDER_NO' };
    if (!pin) return { ok: false, step: 'validate', error: 'NO_PIN' };

    const dryRun = Boolean(raw.dryRun);
    const base = 'https://apigw.settrade.com/api/dgw/v3/029/accounts/' + acct;

    // Step 1: Pre-read to locate the order and extract sequenceNo & tradeDate & symbol
    const preRead = await fetch(`${base}/orders`, { credentials: 'include' });
    if (!preRead.ok) {
        return { ok: false, step: 'pre_read', error: 'PRE_READ_FAILED', httpStatus: preRead.status };
    }
    const preList = await preRead.json();
    const orders = Array.isArray(preList) ? preList : [];
    const target = orders.find(o => String(o.orderNo || o.orderNoSeos || '') === orderNo);
    if (!target) {
        return { ok: false, step: 'pre_read', error: 'ORDER_NOT_FOUND', orderNo };
    }

    const sequenceNo = String(target.sequenceNo || '0');
    const symbol = String(raw.symbol || target.symbol || '').trim().toUpperCase();
    const tradeDate = String(raw.tradeDate || target.tradeDate || (() => {
        const d = new Date();
        const p = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    })());

    const payload = {
        orders: [{
            sequenceNo: sequenceNo,
            orderNo: orderNo,
            symbol: symbol,
            tradeDate: tradeDate,
        }],
        pin: pin,
    };

    if (dryRun) {
        return { ok: true, dryRun: true, preview: payload, acct, orderNo };
    }

    const can = await fetch(`${base}/cancel`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'clientversion': '4.0.0',
            'terminal': 'streaming',
        },
        body: JSON.stringify(payload),
    });

    let canBody = '';
    try { canBody = await can.text(); } catch (e) { canBody = ''; }
    let canJson = null;
    try { canJson = JSON.parse(canBody); } catch (e) { canJson = null; }

    if (!can.ok) {
        return { ok: false, step: 'cancel', httpStatus: can.status, body: canBody.slice(0, 400), error: canJson?.message || 'CANCEL_FAILED' };
    }

    const resItem = canJson?.results?.[0];
    if (resItem && resItem.httpStatusCode && resItem.httpStatusCode !== 200) {
        return { ok: false, step: 'cancel', errorCode: resItem.httpStatusCode, errorResponse: resItem.errorResponse, error: 'CANCEL_REJECTED' };
    }

    // Anti-Mock: re-read orders list
    const postRead = await fetch(`${base}/orders`, { credentials: 'include' });
    if (!postRead.ok) {
        return { ok: false, step: 'verify', error: 'POST_READ_FAILED', httpStatus: postRead.status, cancelResult: canJson || canBody };
    }
    const postList = await postRead.json();
    const postOrders = Array.isArray(postList) ? postList : [];
    const match = postOrders.find(o => String(o.orderNo || o.orderNoSeos || '') === orderNo);

    const statusText = match ? String(match.showOrderStatus || match.status || '').toUpperCase() : '';
    const isCancelled = match ? (['X', 'XC', 'R'].includes(String(match.status || '').toUpperCase()) || statusText.includes('CANCEL')) : true;

    return {
        ok: isCancelled,
        step: isCancelled ? 'verified' : 'verify',
        orderNo,
        acct,
        cancelled: isCancelled,
        verified: isCancelled,
        status: statusText || (match ? match.status : 'CANCELLED_NOT_IN_LIST'),
        cancelResult: canJson || canBody,
        list: postList,
    };
})()
