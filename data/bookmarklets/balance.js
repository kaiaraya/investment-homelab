// Balance snippet: fetch cash balance, line available, purchasing power
(async () => {
    const host = location.hostname;
    if (host.includes('settrade.com')) {
        let acct = '3024959';
        const acctMatch = document.body.innerText.match(/3024\d{3}/);
        if (acctMatch) acct = acctMatch[0];
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
            creditBalance: data.creditBalance
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
            cashBalance: res.result?.cashBalance ?? null,
            lineAvailable: res.result?.lineAvailable ?? null
        };
    }
    return {error: `unsupported host: ${host}`};
})()
