import asyncio
import json
import os
from playwright.async_api import async_playwright

async def test_full_extract():
    with open("data/liberator_session.json") as f:
        data = json.load(f)
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome")
        ctx = await b.new_context()
        await ctx.add_cookies(data.get("cookies", []))
        page = await ctx.new_page()
        await page.goto("https://webtrade.liberator.co.th/Portfolio", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        extracted = await page.evaluate("""() => {
            function cleanNum(val) {
                if (!val) return 0.0;
                let s = val.toString().replace(/,/g, "").replace(/–/g, "-").replace(/%/g, "").trim();
                return parseFloat(s) || 0.0;
            }

            // 1. Account balances
            let lineAvailable = 0.0;
            let cashBalance = 0.0;
            let creditLimit = 0.0;

            const allTexts = Array.from(document.querySelectorAll("div, p, span, td"));
            for (let i = 0; i < allTexts.length; i++) {
                const t = allTexts[i].innerText || "";
                if (t.includes("Line Available:")) {
                    const match = t.match(/Line Available:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) lineAvailable = cleanNum(match[1]);
                }
                if (t.includes("Cash Balance:")) {
                    const match = t.match(/Cash Balance:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) cashBalance = cleanNum(match[1]);
                }
                if (t.includes("Credit Limit:")) {
                    const match = t.match(/Credit Limit:\\s*([\\d,]+\\.?\\d*)/i);
                    if (match) creditLimit = cleanNum(match[1]);
                }
            }

            // 2. Deterministic Table Selection
            const tables = Array.from(document.querySelectorAll("table"));
            let holdingsTable = null;
            let ordersTable = null;

            for (const t of tables) {
                const head = t.querySelector("thead");
                const headTxt = head ? head.innerText.toLowerCase() : "";
                if (headTxt.includes("symbol") && headTxt.includes("in port")) {
                    holdingsTable = t;
                } else if (headTxt.includes("order #") && headTxt.includes("side")) {
                    ordersTable = t;
                }
            }

            // 2A. Scrape Holdings
            const positions = [];
            if (holdingsTable) {
                const rows = Array.from(holdingsTable.querySelectorAll("tbody tr"));
                for (const tr of rows) {
                    const parts = tr.innerText.trim().split(/\\s+/);
                    if (parts.length >= 8 && /^[A-Z][A-Z0-9.\\-]{1,9}$/.test(parts[0]) && !/^\\d+$/.test(parts[0])) {
                        positions.push({
                            symbol: parts[0],
                            act_vol: Math.round(cleanNum(parts[1])),
                            in_port: Math.round(cleanNum(parts[2])),
                            avg_cost: cleanNum(parts[3]),
                            market_price: cleanNum(parts[4]),
                            amount_cost: cleanNum(parts[5]),
                            market_value: cleanNum(parts[6]),
                            unrealized_pnl: cleanNum(parts[7]),
                            pct_unrealized_pnl: cleanNum(parts[8]),
                            realized_pnl: parts.length > 9 ? cleanNum(parts[9]) : 0.0
                        });
                    }
                }
            }

            // 2B. Scrape Orders
            const orders = [];
            if (ordersTable) {
                const rows = Array.from(ordersTable.querySelectorAll("tbody tr"));
                for (const tr of rows) {
                    const txt = tr.innerText.trim();
                    const parts = txt.split(/[\\s\\t|]+/);
                    if (parts.length >= 8 && /^\\d+$/.test(parts[0])) {
                        orders.push({
                            order_no: parts[0],
                            time: parts[1],
                            symbol: parts[2],
                            side: parts[3],
                            price: cleanNum(parts[4]),
                            volume: Math.round(cleanNum(parts[5])),
                            matched: Math.round(cleanNum(parts[6])),
                            balance: Math.round(cleanNum(parts[7])),
                            cancelled: parts.length > 8 ? Math.round(cleanNum(parts[8])) : 0,
                            status: parts.length > 9 ? parts[9] : "Unknown"
                        });
                    }
                }
            }

            const totalMarketValue = positions.reduce((acc, p) => acc + p.market_value, 0);
            const totalCost = positions.reduce((acc, p) => acc + p.amount_cost, 0);
            const totalUnrealized = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);
            const totalEquity = cashBalance + totalMarketValue;

            return {
                line_available: lineAvailable,
                cash_balance: cashBalance,
                credit_limit: creditLimit,
                total_equity: totalEquity,
                total_market_value: totalMarketValue,
                total_cost: totalCost,
                total_unrealized_pnl: totalUnrealized,
                positions: positions,
                orders: orders
            };
        }""")
        
        print("=== SCRAPED LIBERATOR PORTFOLIO DATA ===")
        print(f"Line Available:      ฿{extracted['line_available']:,.2f}")
        print(f"Cash Balance:        ฿{extracted['cash_balance']:,.2f}")
        print(f"Credit Limit:        ฿{extracted['credit_limit']:,.2f}")
        print(f"Total Market Value:  ฿{extracted['total_market_value']:,.2f}")
        print(f"Total Equity:        ฿{extracted['total_equity']:,.2f}")
        print(f"Total Unrealized PnL:฿{extracted['total_unrealized_pnl']:+,.2f}")
        print(f"\nHoldings ({len(extracted['positions'])} stocks):")
        for p in extracted['positions']:
            print(f"  • {p['symbol']:<5} Vol: {p['in_port']:<6} Cost: ฿{p['avg_cost']:<6.2f} Price: ฿{p['market_price']:<6.2f} Val: ฿{p['market_value']:<9,.2f} PnL: ฿{p['unrealized_pnl']:+,.2f} ({p['pct_unrealized_pnl']:+.2f}%)")
        print(f"\nOrders ({len(extracted['orders'])} orders):")
        for o in extracted['orders']:
            print(f"  • #{o['order_no']} {o['time']} {o['symbol']} {o['side']} Vol: {o['volume']} Matched: {o['matched']} Status: {o['status']}")
            
        # Write to cache test
        os.makedirs("data", exist_ok=True)
        with open("data/liberator_portfolio_cache.json", "w") as f:
            json.dump(extracted, f, indent=2)
        print("\nCached to data/liberator_portfolio_cache.json")
        await b.close()

if __name__ == "__main__":
    asyncio.run(test_full_extract())
