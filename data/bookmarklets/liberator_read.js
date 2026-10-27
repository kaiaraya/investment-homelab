// Liberator read open orders via POST /va/order — raw list + Bearer auth (anti-mock source of truth)
// returns {ok, errorCode, errMsg, list, orderNos}
(async () => {
    const getTok = () => { const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/); return m ? decodeURIComponent(m[1]) : null; };
    const tok = getTok();
    if (!tok) return { ok: false, error: 'NO_API_TOKEN' };
    const r = await fetch('https://webtrade.liberator.co.th/va/order', {
        method: 'POST',
        headers: {'content-type': 'application/json', 'authorization': 'Bearer ' + tok},
        body: JSON.stringify({accountNo: '70559382'})
    });
    const j = await r.json();
    const list = j.result?.list || [];
    return { ok: j.errorCode === 0, errorCode: j.errorCode, errMsg: j.errMsg || '', list, orderNos: list.map(o => String(o.orderNo)) };
})()
