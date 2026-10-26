// SBL Return snippet: inspects active contract, fills return quantity, and submits return
(async (arg) => {
    const clean = s => (s || '').replace(/\u00a0/g, ' ').trim();

    if (!location.href.toLowerCase().includes('sbl') && !document.querySelector('#ctl00_MainCenter_rgTrans_ctl00')) {
        return { success: false, status: 'NOT_ON_SBL_PAGE', error: 'Not on SBL Real Time page', current_url: location.href };
    }

    const rawArg = typeof arg === 'string' ? JSON.parse(arg || '{}') : (arg || {});
    const targetRef = (rawArg.ref_no || rawArg.ref || rawArg.lot_id || '').trim().toUpperCase();
    const targetSymbol = (rawArg.symbol || '').trim().toUpperCase();
    const volume = parseInt(rawArg.volume || rawArg.quantity || rawArg.return_qty || 0, 10);
    const remark = (rawArg.remark || '').trim();
    const dryRun = Boolean(rawArg.dry_run || rawArg.dryRun);

    // 1. Locate matching transaction in active table
    const dataTable = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00');
    if (!dataTable) {
        return { success: false, status: 'NO_ACTIVE_TRANSACTIONS_TABLE', error: 'Active transactions table not found' };
    }

    let matchedContract = null;
    const rows = Array.from(dataTable.querySelectorAll('tbody tr, tr.rgRow, tr.rgAltRow'));
    for (const tr of rows) {
        const cells = Array.from(tr.querySelectorAll('td')).map(c => clean(c.innerText));
        if (cells.length >= 9) {
            const refNo = cells[0].toUpperCase();
            const sym = cells[3].toUpperCase();
            if (!refNo || /no records|ลำดับ/i.test(refNo)) continue;

            const returnBtn = tr.querySelector("a[id*='RadReturn']") ||
                [...tr.querySelectorAll('a,button')].find(b => /คืน|return/i.test(b.textContent || '')) || null;

            const match = (targetRef && refNo.includes(targetRef)) || (targetSymbol && sym === targetSymbol);
            if (match) {
                matchedContract = {
                    ref_no: refNo,
                    tran_date: cells[1],
                    time: cells[2],
                    symbol: sym,
                    quantity: parseInt(cells[5].replace(/,/g, ''), 10) || 0,
                    borrow_price: parseFloat(cells[6].replace(/,/g, '')) || 0.0,
                    borrow_value: parseFloat(cells[7].replace(/,/g, '')) || 0.0,
                    fee_rate: parseFloat(cells[8]) || 3.5,
                    close_date: cells[9] || '',
                    has_return_button: !!returnBtn,
                    return_button_id: returnBtn ? returnBtn.id : null
                };
                break;
            }
        }
    }

    if (!matchedContract) {
        return {
            success: false,
            status: 'CONTRACT_NOT_FOUND',
            error: `No active SBL borrow contract matched ref='${targetRef}' symbol='${targetSymbol}'`
        };
    }

    const returnQty = volume > 0 ? volume : matchedContract.quantity;

    // 2. DRY_RUN validation check
    if (dryRun) {
        return {
            success: true,
            status: 'DRY_RUN_ARMED',
            dry_run: true,
            contract: matchedContract,
            return_qty: returnQty,
            message: `[DRY-RUN] Contract ${matchedContract.ref_no} (${matchedContract.symbol}) found with ${matchedContract.quantity} shares. Return held.`
        };
    }

    // 3. LIVE Execution via Return.aspx POST
    try {
        const getUrl = `Return.aspx?Ref=${encodeURIComponent(matchedContract.ref_no)}`;
        const pageResp = await fetch(getUrl);
        if (!pageResp.ok) {
            return { success: false, status: 'MODAL_FETCH_FAILED', error: `Failed to fetch ${getUrl}: HTTP ${pageResp.status}` };
        }
        const html = await pageResp.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');

        const viewState = doc.querySelector('#__VIEWSTATE') ? doc.querySelector('#__VIEWSTATE').value : '';
        const viewStateGen = doc.querySelector('#__VIEWSTATEGENERATOR') ? doc.querySelector('#__VIEWSTATEGENERATOR').value : '';
        const eventValidation = doc.querySelector('#__EVENTVALIDATION') ? doc.querySelector('#__EVENTVALIDATION').value : '';

        const formData = new URLSearchParams();
        formData.append('__EVENTTARGET', 'RadSave');
        formData.append('__EVENTARGUMENT', '');
        formData.append('__VIEWSTATE', viewState);
        if (viewStateGen) formData.append('__VIEWSTATEGENERATOR', viewStateGen);
        if (eventValidation) formData.append('__EVENTVALIDATION', eventValidation);
        formData.append('txtSymbol', matchedContract.symbol);
        formData.append('txtRef', matchedContract.ref_no);
        formData.append('txtReturnQty', String(returnQty));
        if (remark) formData.append('txtRemark', remark);

        const postResp = await fetch(getUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData.toString()
        });

        // Trigger grid refresh on parent window if available
        if (typeof window.refreshGrid === 'function') {
            try { window.refreshGrid(); } catch (e) {}
        }

        return {
            success: postResp.ok,
            status: postResp.ok ? 'RETURN_SUBMITTED' : 'RETURN_HTTP_ERROR',
            http_status: postResp.status,
            ref_no: matchedContract.ref_no,
            symbol: matchedContract.symbol,
            return_qty: returnQty,
            submitted_at: new Date().toISOString()
        };
    } catch (err) {
        return {
            success: false,
            status: 'RETURN_SUBMIT_EXCEPTION',
            ref_no: matchedContract.ref_no,
            error: err.message || String(err)
        };
    }
})()
