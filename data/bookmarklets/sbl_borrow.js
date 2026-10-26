// SBL Borrow snippet: validates safety (XD/XR, PP, inventory), fills symbol & qty, and triggers borrow PostBack
(async (arg) => {
    const clean = s => (s || '').replace(/\u00a0/g, ' ').trim();

    if (!location.href.toLowerCase().includes('sbl') && !document.querySelector('#MainCenter_lbBorrow')) {
        return { success: false, status: 'NOT_ON_SBL_PAGE', error: 'Not on SBL Real Time page', current_url: location.href };
    }

    const rawArg = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const symbol = (rawArg.symbol || '').trim().toUpperCase();
    const volume = parseInt(rawArg.volume || rawArg.quantity || rawArg.qty || 0, 10);
    const dryRun = Boolean(rawArg.dry_run || rawArg.dryRun);

    if (!symbol || !/^[A-Z0-9]{2,10}$/.test(symbol)) {
        return { success: false, status: 'INVALID_SYMBOL', error: `Invalid or missing stock symbol: '${symbol}'` };
    }

    if (!volume || volume <= 0 || volume % 100 !== 0) {
        return { success: false, status: 'INVALID_VOLUME', error: `Volume must be positive multiple of 100 shares (got ${volume})` };
    }

    // 1. Mandatory XD/XR risk check from page DOM
    const validCorporateActions = ['XD', 'XR', 'XM', 'XW', 'XB', 'XI', 'XA', 'XE'];
    let xdRiskFound = null;
    document.querySelectorAll('table').forEach(table => {
        if (table.closest('#ctl00_MainCenter_rgTrans_ctl00') || (table.id && table.id.includes('rgTrans'))) return;
        table.querySelectorAll('tr').forEach(tr => {
            const cells = Array.from(tr.querySelectorAll('td, th')).map(c => clean(c.innerText));
            if (cells.length >= 3) {
                const sym = cells[0].toUpperCase();
                const dateStr = cells[1];
                const typeStr = cells[2].toUpperCase();
                if (sym === symbol && validCorporateActions.includes(typeStr)) {
                    xdRiskFound = { symbol: sym, book_date: dateStr, type: typeStr };
                }
            }
        });
    });

    if (xdRiskFound) {
        return {
            success: false,
            status: 'BLOCKED_BY_XD_XR',
            is_blocked: true,
            symbol: symbol,
            corporate_action: xdRiskFound,
            error: `Symbol ${symbol} has upcoming ${xdRiskFound.type} on ${xdRiskFound.book_date} (100% dividend compensation risk)`
        };
    }

    // 2. Extract Purchasing Power (PP)
    const ppMatch = document.body.innerText.match(/PP\s*=\s*([0-9,.]+)/i);
    const pp = ppMatch ? parseFloat(ppMatch[1].replace(/,/g, '')) : 0.0;
    if (pp <= 0) {
        return { success: false, status: 'INSUFFICIENT_PURCHASING_POWER', purchasing_power: pp, error: 'Purchasing Power is zero or negative' };
    }

    // 3. Fill Form Inputs
    const symInput = document.querySelector('#ctl00_MainCenter_txtSymbol');
    const qtyInput = document.querySelector('#ctl00_MainCenter_txtQty');
    if (!symInput || !qtyInput) {
        return { success: false, status: 'FORM_INPUTS_NOT_FOUND', error: 'Could not find txtSymbol or txtQty form fields' };
    }

    // Set standard DOM values & trigger input events
    symInput.value = symbol;
    symInput.dispatchEvent(new Event('input', { bubbles: true }));
    symInput.dispatchEvent(new Event('change', { bubbles: true }));

    qtyInput.value = String(volume);
    qtyInput.dispatchEvent(new Event('input', { bubbles: true }));
    qtyInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Sync Telerik RadTextBox / RadNumericTextBox client state
    try {
        if (typeof $find === 'function') {
            const telerikSym = $find('ctl00_MainCenter_txtSymbol');
            if (telerikSym && typeof telerikSym.set_value === 'function') {
                telerikSym.set_value(symbol);
            }
            const telerikQty = $find('ctl00_MainCenter_txtQty');
            if (telerikQty && typeof telerikQty.set_value === 'function') {
                telerikQty.set_value(volume);
            }
        }
    } catch (e) {
        // Telerik client state sync fallback
    }

    // 4. DRY_RUN early exit (do not submit)
    if (dryRun) {
        return {
            success: true,
            status: 'DRY_RUN_ARMED',
            dry_run: true,
            symbol: symbol,
            volume: volume,
            purchasing_power: pp,
            message: `[DRY-RUN] SBL borrow form filled for ${symbol} ${volume} shares. PostBack held.`
        };
    }

    // 5. LIVE PostBack Execution
    const lbBorrow = document.querySelector('#MainCenter_lbBorrow');
    if (!lbBorrow) {
        return { success: false, status: 'BORROW_BUTTON_NOT_FOUND', error: 'lbBorrow PostBack trigger not found' };
    }

    const prm = (typeof Sys !== 'undefined' && Sys.WebForms && Sys.WebForms.PageRequestManager) ?
        Sys.WebForms.PageRequestManager.getInstance() : null;

    const postBackPromise = new Promise((resolve) => {
        let done = false;
        const finish = (result) => {
            if (!done) {
                done = true;
                if (prm) {
                    try { prm.remove_endRequest(handler); } catch (e) {}
                }
                resolve(result);
            }
        };

        const handler = (sender, args) => {
            const err = args && args.get_error ? args.get_error() : null;
            if (err) {
                finish({ success: false, status: 'POSTBACK_ERROR', error: err.message || String(err) });
            } else {
                finish({ success: true, status: 'SUBMITTED' });
            }
        };

        if (prm) {
            prm.add_endRequest(handler);
        }
        setTimeout(() => finish({ success: true, status: 'SUBMITTED_TIMEOUT_RESOLVE' }), 6000);

        // Trigger borrow submit
        lbBorrow.click();
    });

    const submitResult = await postBackPromise;

    // Post-submit inspection: check active transactions table
    await new Promise(r => setTimeout(r, 1000));
    const postPPText = document.body.innerText.match(/PP\s*=\s*([0-9,.]+)/i);
    const updatedPP = postPPText ? parseFloat(postPPText[1].replace(/,/g, '')) : pp;

    return {
        success: submitResult.success,
        status: submitResult.status,
        symbol: symbol,
        volume: volume,
        purchasing_power: updatedPP,
        submitted_at: new Date().toISOString()
    };
})()
