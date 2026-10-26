// Dump selector tree and visible text of current page for probe SOP
(() => {
    const clean = s => (s || '').replace(/\s+/g, ' ').trim();
    const summary = {
        title: document.title,
        url: location.href,
        inputs: [],
        buttons: [],
        tables: [],
        visibleTextSnippets: []
    };
    document.querySelectorAll('input, select, textarea').forEach(el => {
        summary.inputs.push({
            tag: el.tagName,
            id: el.id || null,
            name: el.name || null,
            type: el.type || null,
            placeholder: el.placeholder || null,
            value: el.value ? String(el.value).slice(0, 50) : null
        });
    });
    document.querySelectorAll('button, a[role="button"], [class*="btn" i]').forEach(el => {
        const text = clean(el.innerText || el.textContent);
        if (text && text.length < 50) {
            summary.buttons.push({
                tag: el.tagName,
                id: el.id || null,
                class: el.className || null,
                text: text
            });
        }
    });
    document.querySelectorAll('table').forEach((tbl, idx) => {
        const rows = [];
        tbl.querySelectorAll('tr').forEach(tr => {
            const cells = [...tr.querySelectorAll('th, td')].map(c => clean(c.innerText));
            if (cells.length) rows.push(cells.join(' | ').slice(0, 150));
        });
        summary.tables.push({ index: idx, id: tbl.id || null, rowCount: rows.length, rows: rows.slice(0, 15) });
    });
    const rawLines = (document.body.innerText || '').split(/\r?\n/).map(clean).filter(Boolean);
    summary.visibleTextSnippets = rawLines.slice(0, 50);
    return summary;
})()
