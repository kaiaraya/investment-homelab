// Quote snippet: fetch static data / bid-offer for symbol
// Usage: called with symbol param interpolated or extracted from window / URL
(async (symbol = (typeof window !== 'undefined' && window.__QUOTE_SYMBOL) || 'TU') => {
    const host = location.hostname;
    if (host.includes('settrade.com')) {
        const r = await fetch(`https://apigwcld.settrade.com/api/marketdata/v4/029/static-data/${symbol}?market=E`, {credentials: 'include'});
        if (!r.ok) return {error: `HTTP ${r.status}`, symbol};
        const data = await r.json();
        return {
            broker: 'kss',
            symbol: symbol,
            bid: data.firstBid,
            ask: data.firstAsk,
            last: data.last,
            close: data.close,
            ceiling: data.ceiling,
            floor: data.floor,
            spreadList: data.spreadList || []
        };
    } else if (host.includes('liberator.co.th')) {
        try {
            const cfgRes = await fetch('https://webtrade.liberator.co.th/vb/config', {credentials: 'include'});
            if (!cfgRes.ok) return {error: `HTTP ${cfgRes.status}`, symbol};
            const cfg = await cfgRes.json();
            const config = cfg?.result?.data?.config || {};
            let orderBookId = null;
            const ordered = ['set', 'set50if', 'tfex', ...Object.keys(config)];
            for (const grp of ordered) {
                const node = config[grp];
                if (!node) continue;
                for (const key of ['securities', 'indexes']) {
                    for (const row of node[key] || []) {
                        if (Array.isArray(row) && row[0]?.toUpperCase() === symbol.toUpperCase()) {
                            orderBookId = parseInt(row[1]);
                            break;
                        }
                    }
                    if (orderBookId) break;
                }
                if (orderBookId) break;
            }
            if (!orderBookId) return {error: 'SYMBOL_NOT_FOUND', symbol};
            const r = await fetch('https://webtrade.liberator.co.th/vb/stock/info', {
                method: 'POST',
                credentials: 'include',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify({orderBookIds: [orderBookId]})
            });
            if (!r.ok) return {error: `HTTP ${r.status}`, symbol};
            const data = await r.json();
            const item = (data?.result?.list || [])[0];
            if (!item) return {error: 'NO_RECORD', symbol};
            return {
                broker: 'liberator',
                symbol: symbol,
                bid: parseFloat(item.bp) || null,
                ask: parseFloat(item.op) || null,
                last: parseFloat(item.l) || null,
                close: parseFloat(item.prior) || null,
                ceiling: parseFloat(item.cl) || null,
                floor: parseFloat(item.fl) || null,
                orderBookId: orderBookId
            };
        } catch (e) {
            return {error: String(e), symbol};
        }
    }
    return {error: `unsupported host: ${host}`};
})()
