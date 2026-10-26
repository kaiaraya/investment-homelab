#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe SBL Real Time page DOM contract via CDP 9333."""
import asyncio
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab  # noqa: E402


async def probe():
    pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
    page = await resolve_target_tab(ctx, "sbl", "kss")
    await page.bring_to_front()
    await page.wait_for_timeout(1000)

    info = {
        "url": page.url,
        "title": await page.title(),
    }

    # 1. Borrow Form
    borrow_info = await page.evaluate("""() => {
        const sym = document.querySelector('#ctl00_MainCenter_txtSymbol');
        const qty = document.querySelector('#ctl00_MainCenter_txtQty');
        const cusCode = document.querySelector('#ctl00_MainCenter_txtCusCode') || document.querySelector('#ctl00_MainCenter_txSearchCode');
        const cusName = document.querySelector('#ctl00_MainCenter_lbCusName');
        const lbBorrow = document.querySelector('#MainCenter_lbBorrow') || document.querySelector('#ctl00_MainCenter_lbBorrow');
        const borrowPanel = document.querySelector('#ctl00_MainCenter_ctl00_MainCenter_pnlBorrowPanel') || document.querySelector('[id*="BorrowPanel"]');
        
        // Find all inputs / buttons near borrow panel
        const allInputs = Array.from(document.querySelectorAll('input, button, a.btn, a[id*="Borrow"]')).map(el => ({
            id: el.id,
            name: el.name,
            tagName: el.tagName,
            type: el.type,
            value: el.value,
            outerHTML: el.outerHTML.slice(0, 200)
        }));

        return {
            sym: sym ? { id: sym.id, outerHTML: sym.outerHTML } : null,
            qty: qty ? { id: qty.id, outerHTML: qty.outerHTML } : null,
            cusCode: cusCode ? { id: cusCode.id, value: cusCode.value || cusCode.innerText, outerHTML: cusCode.outerHTML } : null,
            cusName: cusName ? { id: cusName.id, text: cusName.innerText } : null,
            lbBorrow: lbBorrow ? { id: lbBorrow.id, href: lbBorrow.getAttribute('href'), onclick: lbBorrow.getAttribute('onclick'), outerHTML: lbBorrow.outerHTML } : null,
            borrowPanel: borrowPanel ? { id: borrowPanel.id, text: borrowPanel.innerText } : null,
            allInputs: allInputs
        };
    }""")
    info["borrow_form"] = borrow_info

    # 2. Transaction Grid (#ctl00_MainCenter_rgTrans_ctl00)
    trans_info = await page.evaluate("""() => {
        const grid = document.querySelector('#ctl00_MainCenter_rgTrans_ctl00') || document.querySelector('[id*="rgTrans"]');
        if (!grid) return { found: false };
        
        const headers = Array.from(grid.querySelectorAll('th, thead td')).map(th => ({
            id: th.id,
            text: th.innerText.trim(),
            outerHTML: th.outerHTML.slice(0, 150)
        }));

        const rows = Array.from(grid.querySelectorAll('tbody tr')).map(tr => ({
            id: tr.id,
            className: tr.className,
            cells: Array.from(tr.querySelectorAll('td')).map(td => ({
                text: td.innerText.trim(),
                innerHTML: td.innerHTML.slice(0, 150)
            }))
        }));

        return {
            found: true,
            id: grid.id,
            headers: headers,
            rowCount: rows.length,
            rows: rows.slice(0, 10)
        };
    }""")
    info["trans_grid"] = trans_info

    # 3. Return function / modals / scripts
    script_info = await page.evaluate("""() => {
        const res = {};
        res.hasShowReturnForm = typeof window.ShowReturnForm !== 'undefined';
        if (res.hasShowReturnForm) {
            res.showReturnFormSource = window.ShowReturnForm.toString();
        }
        
        // Look for return elements or modals
        const returnLinks = Array.from(document.querySelectorAll('a[id*="Return"], a[href*="Return"], [onclick*="Return"]')).map(el => ({
            id: el.id,
            href: el.getAttribute('href'),
            onclick: el.getAttribute('onclick'),
            text: el.innerText.trim()
        }));
        res.returnLinks = returnLinks;

        // Look for RadWindow or popup modals in DOM
        const radWindows = Array.from(document.querySelectorAll('[id*="RadWindow"], [class*="RadWindow"], div.modal, div.popup')).map(el => ({
            id: el.id,
            className: el.className,
            outerHTML: el.outerHTML.slice(0, 300)
        }));
        res.radWindows = radWindows;

        // Find all script contents defining ShowReturnForm or borrow submit
        const scripts = Array.from(document.querySelectorAll('script')).map(s => s.innerText);
        res.matchingScripts = scripts.filter(s => s.includes('ShowReturnForm') || s.includes('lbBorrow') || s.includes('rgTrans')).map(s => s.slice(0, 500));

        return res;
    }""")
    info["return_scripts"] = script_info

    # 4. XD tab inspection
    xd_info = await page.evaluate("""() => {
        const lbXD = document.querySelector('#MainCenter_lbXD') || document.querySelector('[id*="lbXD"]');
        return {
            found: !!lbXD,
            id: lbXD ? lbXD.id : null,
            href: lbXD ? lbXD.getAttribute('href') : null,
            onclick: lbXD ? lbXD.getAttribute('onclick') : null,
            outerHTML: lbXD ? lbXD.outerHTML : null
        };
    }""")
    info["xd_tab"] = xd_info

    # 5. Look for error / alert containers
    error_info = await page.evaluate("""() => {
        const errs = Array.from(document.querySelectorAll('[id*="lbl"], [id*="Error"], [id*="Msg"], [class*="error"], [class*="alert"], span[style*="color:Red"], span[style*="color:red"]')).map(el => ({
            id: el.id,
            text: el.innerText.trim(),
            outerHTML: el.outerHTML.slice(0, 200)
        }));
        return errs;
    }""")
    info["error_elements"] = error_info

    print(json.dumps(info, ensure_ascii=False, indent=2))

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(probe())
