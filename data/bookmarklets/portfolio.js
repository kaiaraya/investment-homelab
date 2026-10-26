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
        const r = await fetch('https://webtrade.liberator.co.th/va/portfolio', {
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
            result: res.result || {}
        };
    }
    return {error: `unsupported host: ${host}`};
})()
