// Orders snippet: fetch open/queuing orders for current account
(async () => {
    const host = location.hostname;
    if (host.includes('settrade.com')) {
        // Detect active account from DOM or fallback to margin 3024959 / cash 3024952
        let acct = '3024959';
        const acctMatch = document.body.innerText.match(/3024\d{3}/);
        if (acctMatch) acct = acctMatch[0];
        const r = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}/orders`, {credentials: 'include'});
        if (!r.ok) return {error: `HTTP ${r.status}`, account: acct};
        const list = await r.json();
        return {
            broker: 'kss',
            account: acct,
            orders: (list || []).map(o => ({
                orderNo: o.orderNo,
                symbol: o.symbol,
                side: o.side,
                price: o.price,
                vol: o.vol,
                status: o.showOrderStatus || o.orderStatus,
                canCancel: o.canCancel || false,
                rejectReason: o.rejectReason || null
            }))
        };
    } else if (host.includes('liberator.co.th')) {
        const r = await fetch('https://webtrade.liberator.co.th/va/order', {
            method: 'POST',
            credentials: 'include',
            headers: {'content-type': 'application/json'},
            body: JSON.stringify({accountNo: '70559382'})
        });
        if (!r.ok) return {error: `HTTP ${r.status}`};
        const res = await r.json();
        return {
            broker: 'liberator',
            account: '70559382',
            orders: (res.result?.list || []).map(o => ({
                orderNo: o.orderNo || o.orderId,
                symbol: o.stockSymbol || o.symbol,
                side: o.side,
                price: o.price,
                vol: o.volume,
                status: o.status
            }))
        };
    }
    return {error: `unsupported host: ${host}`};
})()
