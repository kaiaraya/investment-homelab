// Portfolio snippet: fetch stock balance / positions
(async () => {
    const host = location.hostname;
    if (host.includes('settrade.com')) {
        let acct = '3024959';
        const acctMatch = document.body.innerText.match(/3024\d{3}/);
        if (acctMatch) acct = acctMatch[0];
        // Portfolio on Streaming: fetched via account summary + equity account info
        const r = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}`, {credentials: 'include'});
        if (!r.ok) return {error: `HTTP ${r.status}`, account: acct};
        const data = await r.json();
        return {
            broker: 'kss',
            account: acct,
            accountType: data.accountType,
            lineAvailable: data.lineAvailable,
            cashBalance: data.cashBalance,
            creditLimit: data.creditLimit,
            equityBalance: data.equityBalance,
            portfolio: data.portfolio || []
        };
    } else if (host.includes('liberator.co.th')) {
        const getTok = () => { const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/); return m ? decodeURIComponent(m[1]) : null; };
        const r = await fetch('https://webtrade.liberator.co.th/va/portfolio', {
            method: 'POST',
            credentials: 'include',
            headers: {'content-type': 'application/json', 'authorization': 'Bearer ' + getTok()},
            body: JSON.stringify({accountNo: '70559382'})
        });
        if (!r.ok) return {error: `HTTP ${r.status}`};
        const res = await r.json();
        if (res.errorCode !== 0) return {error: res.errMsg || `errorCode ${res.errorCode}`, broker: 'liberator', account: '70559382'};
        return {
            broker: 'liberator',
            account: '70559382',
            result: res.result || {}
        };
    }
    return {error: `unsupported host: ${host}`};
})()
