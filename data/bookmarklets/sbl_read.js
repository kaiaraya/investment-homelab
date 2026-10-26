// SBL Real Time reader bookmarklet: extracts PP, full inventory (SET50/100/NEWSEC), XD-XR calendar, and active contracts
(async (arg) => {
    const clean = s => (s || '').replace(/\u00a0/g, ' ').trim();

    if (!location.href.toLowerCase().includes('sbl') && !document.querySelector('#MainCenter_lbBorrow')) {
        return { error: 'Not on SBL Real Time page', current_url: location.href };
    }

    // 1. Purchasing Power
    const ppMatch = document.body.innerText.match(/PP\s*=\s*([0-9,.]+)/i);
    const ppRaw = ppMatch ? ppMatch[1] : null;
    const pp = ppRaw ? parseFloat(ppRaw.replace(/,/g, '')) : 0.0;

    // 2. Account info
    const cusCodeEl = document.querySelector('#ctl00_MainCenter_txtCusCode, #ctl00_MainCenter_txSearchCode');
    const cusNameEl = document.querySelector('#ctl00_MainCenter_lbCusName, #MainCenter_lbName');
    const account = cusCodeEl ? (cusCodeEl.value || cusCodeEl.innerText || '').trim() : '';
    const customerName = cusNameEl ? (cusNameEl.value || cusNameEl.innerText || '').trim() : '';

    // 3. Extraction helpers
    const extractInventoryTable = (tabName = '') => {
        const items = [];
        const seen = new Set();
        document.querySelectorAll('table').forEach(table => {
            if (table.closest('#ctl00_MainCenter_rgTrans_ctl00') || (table.id && table.id.includes('rgTrans'))) return;
            table.querySelectorAll('tr').forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td, th')).map(c => clean(c.innerText));
                if (cells.length >= 4) {
                    const sym = cells[0].toUpperCase();
                    const feeStr = cells[1].replace(/,/g, '');
                    const volStr = cells[2].replace(/,/g, '');
                    const imStr = cells[3].replace(/,/g, '');
                    if (/^[A-Z0-9]{2,10}$/.test(sym) && !['SYMBOL', 'FEE', 'VOLUME', 'IM', 'SET50', 'SET100'].includes(sym)) {
                        if (!seen.has(sym)) {
                            seen.add(sym);
                            const item = {
                                symbol: sym,
                                borrow_fee_pct: parseFloat(feeStr) || 3.5,
                                available_qty: parseInt(volStr, 10) || 0,
                                initial_margin_pct: parseFloat(imStr) || 50.0
                            };
                            if (tabName) item.tab = tabName;
                            items.push(item);
                        }
                    }
                }
            });
        });
        return items;
    };

    const extractXDXRTable = () => {
        const items = [];
        const seen = new Set();
        const validCorporateActions = ['XD', 'XR', 'XM', 'XW', 'XB', 'XI', 'XA', 'XE'];
        document.querySelectorAll('table').forEach(table => {
            if (table.closest('#ctl00_MainCenter_rgTrans_ctl00') || (table.id && table.id.includes('rgTrans'))) return;
            table.querySelectorAll('tr').forEach(tr => {
                const cells = Array.from(tr.querySelectorAll('td, th')).map(c => clean(c.innerText));
                if (cells.length >= 3) {
                    const sym = cells[0].toUpperCase();
                    const dateStr = cells[1];
                    const typeStr = cells[2].toUpperCase();
                    if (/^[A-Z0-9]{2,10}$/.test(sym) && !['SYMBOL', 'BOOK DATE', 'TYPE'].includes(sym) && validCorporateActions.includes(typeStr)) {
                        if (!seen.has(sym)) {
                            seen.add(sym);
                            items.push({
                                symbol: sym,
                                book_date: dateStr,
                                type: typeStr,
                                sign: typeStr
                            });
                        }
                    }
                }
            });
        });
        return items;
    };

    const extractTransactions = () => {
        const items = [];
        const dataTable = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00');
        if (!dataTable) return items;
        dataTable.querySelectorAll('tbody tr, tr.rgRow, tr.rgAltRow').forEach(tr => {
            const cells = Array.from(tr.querySelectorAll('td')).map(c => clean(c.innerText));
            if (cells.length >= 9) {
                const refNo = cells[0];
                if (refNo && !/no records|ลำดับ/i.test(refNo)) {
                    const returnBtn = tr.querySelector("a[id*='RadReturn']") ||
                        [...tr.querySelectorAll('a,button')].find(b => /คืน|return/i.test(b.textContent || '')) || null;
                    items.push({
                        ref_no: refNo,
                        tran_date: cells[1],
                        time: cells[2],
                        symbol: cells[3].toUpperCase(),
                        type: cells[4],
                        quantity: parseInt(cells[5].replace(/,/g, ''), 10) || 0,
                        borrow_price: parseFloat(cells[6].replace(/,/g, '')) || 0.0,
                        borrow_value: parseFloat(cells[7].replace(/,/g, '')) || 0.0,
                        fee_rate: parseFloat(cells[8]) || 3.5,
                        close_date: cells[9] || '',
                        has_return_button: !!returnBtn,
                        return_button_id: returnBtn ? returnBtn.id : null
                    });
                }
            }
        });
        return items;
    };

    // 4. UpdatePanel tab switcher
    const switchTab = async (selector) => {
        const btn = document.querySelector(selector);
        if (!btn) return false;
        const prm = (typeof Sys !== 'undefined' && Sys.WebForms && Sys.WebForms.PageRequestManager) ?
            Sys.WebForms.PageRequestManager.getInstance() : null;
        if (!prm) {
            btn.click();
            await new Promise(r => setTimeout(r, 1500));
            return true;
        }
        await new Promise((resolve) => {
            let done = false;
            const handler = () => {
                if (!done) {
                    done = true;
                    try { prm.remove_endRequest(handler); } catch (e) {}
                    resolve();
                }
            };
            prm.add_endRequest(handler);
            setTimeout(() => {
                if (!done) {
                    done = true;
                    try { prm.remove_endRequest(handler); } catch (e) {}
                    resolve();
                }
            }, 2500);
            btn.click();
        });
        return true;
    };

    const activeTransactions = extractTransactions();
    const mode = (typeof arg === 'string' ? arg.toLowerCase() : (arg && arg.mode) ? arg.mode.toLowerCase() : 'all');

    let set50 = [];
    let set100 = [];
    let newsec = [];
    let xdXr = [];

    if (mode === 'current') {
        const currentInv = extractInventoryTable();
        return {
            broker: 'kss',
            app: 'sbl_realtime',
            url: location.href,
            account: account,
            customer_name: customerName,
            purchasing_power: pp,
            purchasing_power_raw: ppRaw,
            counts: {
                inventory: currentInv.length,
                active_borrows: activeTransactions.length
            },
            inventory: currentInv,
            active_borrow_transactions: activeTransactions
        };
    }

    if (mode === 'xd' || mode === 'xdxr') {
        await switchTab('#MainCenter_lbXD');
        xdXr = extractXDXRTable();
        await switchTab('#MainCenter_lbSet50');
        return {
            broker: 'kss',
            app: 'sbl_realtime',
            url: location.href,
            account: account,
            purchasing_power: pp,
            purchasing_power_raw: ppRaw,
            counts: { xd_xr_risks: xdXr.length, active_borrows: activeTransactions.length },
            xd_xr_risks: xdXr,
            active_borrow_transactions: activeTransactions
        };
    }

    // Full multi-tab scan: SET50 -> SET100 -> NEWSEC -> XD,XR -> reset to SET50
    await switchTab('#MainCenter_lbSet50');
    set50 = extractInventoryTable('SET50');

    await switchTab('#MainCenter_lbSet100');
    set100 = extractInventoryTable('SET100');

    await switchTab('#MainCenter_lbNewSec');
    newsec = extractInventoryTable('NEWSEC');

    await switchTab('#MainCenter_lbXD');
    xdXr = extractXDXRTable();

    // Reset active view back to SET50
    await switchTab('#MainCenter_lbSet50');

    // Combined unique inventory
    const combined = [];
    const seenSyms = new Set();
    [...set50, ...set100, ...newsec].forEach(item => {
        if (!seenSyms.has(item.symbol)) {
            seenSyms.add(item.symbol);
            combined.push(item);
        }
    });

    return {
        broker: 'kss',
        app: 'sbl_realtime',
        url: location.href,
        account: account,
        customer_name: customerName,
        purchasing_power: pp,
        purchasing_power_raw: ppRaw,
        counts: {
            set50: set50.length,
            set100: set100.length,
            newsec: newsec.length,
            xd_xr_risks: xdXr.length,
            active_borrows: activeTransactions.length,
            total_unique_inventory: combined.length
        },
        inventory: combined,
        set50_inventory: set50,
        set100_inventory: set100,
        newsec_inventory: newsec,
        xd_xr_risks: xdXr,
        active_borrow_transactions: activeTransactions
    };
})()
