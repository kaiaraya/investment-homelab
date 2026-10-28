# -*- coding: utf-8 -*-
"""
Pre-market broker read-only snapshot service (SNAP.1).

Fetches real-time status directly from broker REST endpoints via CDP session daemons:
- KSS (Settrade Streaming on port 9333): accounts 3024959 (MARGIN) and 3024952 (CASH)
- Liberator (webtrade.liberator.co.th on port 9334): account 70559382 (CASH BALANCE)

Captures 4 datasets per broker:
1. Balance (creditLimit, cashBalance, lineAvailable, pp/equity)
2. Positions (portfolio holdings)
3. Open orders (queuing/unmatched orders)
4. Market status (SET status)

Enforces fail-closed: on missing sessions, invalid tokens, non-200 responses,
or reconciliation discrepancies, fails honestly without fabricating 0-item data.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from scripts.broker_cdp.client import connect_cdp, cdp_url_for, resolve_target_tab

logger = logging.getLogger("broker_snapshot")

TZ_BKK = timezone(timedelta(hours=7))

KSS_ACCOUNTS = ["3024959", "3024952"]
KSS_ACCOUNT_TYPES = {
    "3024959": "CREDIT_BALANCE",
    "3024952": "CASH_ACCOUNT",
}

LIB_ACCOUNT = "70559382"

KSS_JS_READ = """async () => {
    const results = {};
    const accounts = ['3024959', '3024952'];
    for (const acct of accounts) {
        const acctType = acct === '3024959' ? 'CREDIT_BALANCE' : 'CASH_ACCOUNT';
        try {
            const rBal = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}`, {credentials: 'include'});
            const bal = rBal.ok ? await rBal.json() : {http_status: rBal.status, error: 'HTTP_' + rBal.status};

            const rPort = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}/portfolios?accountType=${acctType}`, {credentials: 'include'});
            const port = rPort.ok ? await rPort.json() : {http_status: rPort.status, error: 'HTTP_' + rPort.status};

            const rOrd = await fetch(`https://apigw.settrade.com/api/dgw/v3/029/accounts/${acct}/orders`, {credentials: 'include'});
            const ord = rOrd.ok ? await rOrd.json() : {http_status: rOrd.status, error: 'HTTP_' + rOrd.status};

            results[acct] = {balance: bal, portfolio: port, orders: ord};
        } catch (err) {
            results[acct] = {error: String(err)};
        }
    }
    return results;
}"""

LIB_JS_READ = """async () => {
    const getTok = () => {
        const m = document.cookie.match(/(?:^|;\s*)api-token=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : null;
    };
    const tok = getTok();
    if (!tok) return { ok: false, error: 'NO_API_TOKEN' };
    const headers = {'content-type': 'application/json', 'authorization': 'Bearer ' + tok};

    try {
        const rProf = await fetch('https://webtrade.liberator.co.th/va/profile', {headers});
        const prof = rProf.ok ? await rProf.json() : {http_status: rProf.status, error: 'HTTP_' + rProf.status};

        const rPort = await fetch('https://webtrade.liberator.co.th/va/portfolio', {
            method: 'POST', headers, body: JSON.stringify({accountNo: '70559382'})
        });
        const port = rPort.ok ? await rPort.json() : {http_status: rPort.status, error: 'HTTP_' + rPort.status};

        const rOrd = await fetch('https://webtrade.liberator.co.th/va/order', {
            method: 'POST', headers, body: JSON.stringify({accountNo: '70559382'})
        });
        const ord = rOrd.ok ? await rOrd.json() : {http_status: rOrd.status, error: 'HTTP_' + rOrd.status};

        const rMkt = await fetch('https://webtrade.liberator.co.th/vb/status/set?roleGroup=SET0300', {headers});
        const mkt = rMkt.ok ? await rMkt.json() : {http_status: rMkt.status, error: 'HTTP_' + rMkt.status};

        return { ok: true, profile: prof, portfolio: port, orders: ord, market: mkt };
    } catch (err) {
        return { ok: false, error: String(err) };
    }
}"""


def reconcile_kss_data(raw_data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate and reconcile KSS datasets. Returns (success, reason, clean_payload)."""
    if not isinstance(raw_data, dict):
        return False, "raw_data is not dict", {}

    clean_accounts = {}
    reconcile_log = []

    for acct in KSS_ACCOUNTS:
        acct_data = raw_data.get(acct)
        if not acct_data or not isinstance(acct_data, dict):
            return False, f"KSS account {acct} missing from response", {}
        if "error" in acct_data and acct_data.get("error"):
            return False, f"KSS account {acct} error: {acct_data['error']}", {}

        bal = acct_data.get("balance", {})
        if not bal or bal.get("error") or bal.get("http_status"):
            return False, f"KSS account {acct} balance endpoint failed: {bal}", {}
        if str(bal.get("accountNo")) != acct:
            return False, f"KSS accountNo mismatch: expected {acct}, got {bal.get('accountNo')}", {}

        port = acct_data.get("portfolio", {})
        if not isinstance(port, dict) or port.get("error") or port.get("http_status"):
            return False, f"KSS account {acct} portfolio endpoint failed: {port}", {}

        ord_data = acct_data.get("orders")
        if not isinstance(ord_data, list):
            return False, f"KSS account {acct} orders endpoint failed (not list): {ord_data}", {}

        portfolio_list = port.get("portfolioList", [])
        if not isinstance(portfolio_list, list):
            return False, f"KSS account {acct} portfolioList is not list: {portfolio_list}", {}

        # Filter open orders
        open_orders = []
        for o in ord_data:
            st = str(o.get("showOrderStatus") or o.get("orderStatus") or "").upper()
            if any(k in st for k in ["QUEU", "OPEN", "PENDING", "PARTIAL", "WAIT"]):
                open_orders.append(o)

        # Reconcile logic
        cash_balance = float(bal.get("cashBalance") or 0.0)
        line_avail = float(bal.get("lineAvailable") or 0.0)
        credit_limit = float(bal.get("creditLimit") or 0.0)

        prices_stale = False
        for p in portfolio_list:
            vol = int(p.get("actualVolume") or p.get("currentVolume") or 0)
            if vol > 0 and float(p.get("marketPrice") or 0.0) == 0.0:
                prices_stale = True

        if acct == "3024959":  # MARGIN
            pp = float(bal.get("pp") or bal.get("purchasingPower") or 0.0)
            equity = float(bal.get("equity") or bal.get("equityBalance") or 0.0)

            # Check lineAvailable == cashBalance when no open orders
            if len(open_orders) == 0:
                if abs(line_avail - cash_balance) > 0.05:
                    return False, f"KSS 3024959 reconcile failed: lineAvailable ({line_avail}) != cashBalance ({cash_balance}) with 0 open orders", {}
                reconcile_log.append(f"3024959: lineAvailable == cashBalance ({line_avail})")
            else:
                if line_avail > cash_balance + 0.05:
                    return False, f"KSS 3024959 reconcile failed: lineAvailable ({line_avail}) > cashBalance ({cash_balance}) with open orders", {}
                reconcile_log.append(f"3024959: lineAvailable ({line_avail}) <= cashBalance ({cash_balance}) with {len(open_orders)} open orders")

            # Purchasing power check (pp == 2 * equity approx)
            if equity > 0:
                ratio = pp / equity
                if not (1.8 <= ratio <= 2.2):
                    return False, f"KSS 3024959 reconcile failed: pp/equity ratio {ratio:.2f} out of bounds (pp={pp}, equity={equity})", {}
                reconcile_log.append(f"3024959: pp ≈ 2*equity ({pp} / {equity} = {ratio:.2f})")

        elif acct == "3024952":  # CASH
            reconcile_log.append(f"3024952: cashBalance={cash_balance}, lineAvailable={line_avail}, limit={credit_limit}")

        clean_accounts[acct] = {
            "account_type": bal.get("accountType", KSS_ACCOUNT_TYPES.get(acct)),
            "balance": {
                "creditLimit": credit_limit,
                "cashBalance": cash_balance,
                "lineAvailable": line_avail,
                "pp": float(bal.get("pp") or 0.0),
                "ee": float(bal.get("ee") or 0.0),
                "equity": float(bal.get("equity") or 0.0),
                "purchasingPower": float(bal.get("purchasingPower") or 0.0),
                "creditBalance": bool(bal.get("creditBalance")),
            },
            "positions": portfolio_list,
            "open_orders": open_orders,
            "prices_stale": prices_stale,
        }

    payload = {
        "status": "OK",
        "reconcile_status": "PASS",
        "reconcile_notes": reconcile_log,
        "accounts": clean_accounts,
        "market_status": None,
    }
    return True, "PASS", payload


def reconcile_liberator_data(raw_data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate and reconcile Liberator datasets. Returns (success, reason, clean_payload)."""
    if not isinstance(raw_data, dict):
        return False, "raw_data is not dict", {}
    if not raw_data.get("ok"):
        return False, f"Liberator probe error: {raw_data.get('error')}", {}

    prof = raw_data.get("profile", {})
    if prof.get("errorCode") != 0:
        return False, f"Liberator profile errorCode: {prof.get('errorCode')} ({prof.get('errMsg')})", {}

    res = prof.get("result", {})
    accounts = res.get("accounts", [])
    acct_obj = next((a for a in accounts if str(a.get("accountNo")) == LIB_ACCOUNT), None)
    if not acct_obj:
        return False, f"Liberator account {LIB_ACCOUNT} not found in profile: {[a.get('accountNo') for a in accounts]}", {}

    port = raw_data.get("portfolio", {})
    if port.get("errorCode") != 0:
        return False, f"Liberator portfolio errorCode: {port.get('errorCode')} ({port.get('errMsg')})", {}
    port_list = port.get("result", {}).get("list", [])

    ord_data = raw_data.get("orders", {})
    if ord_data.get("errorCode") != 0:
        return False, f"Liberator order errorCode: {ord_data.get('errorCode')} ({ord_data.get('errMsg')})", {}
    ord_list = ord_data.get("result", {}).get("list", [])

    mkt = raw_data.get("market", {})
    mkt_st = None
    if mkt.get("errorCode") == 0:
        mkt_st = mkt.get("result", {}).get("data", {})

    # Reconcile logic
    cash_bal = float(acct_obj.get("cashBalance") or 0.0)
    line_avail = float(acct_obj.get("lineAvailable") or 0.0)
    withdraw_avail = float(acct_obj.get("withdrawAvailable") or 0.0)
    credit_limit = float(acct_obj.get("creditLimit") or 0.0)

    reconcile_log = []
    if len(ord_list) == 0 and len(port_list) == 0:
        if abs(line_avail - cash_bal) > 0.05 or abs(cash_bal - withdraw_avail) > 0.05:
            return False, f"Liberator reconcile failed: lineAvailable ({line_avail}) == cashBalance ({cash_bal}) == withdrawAvailable ({withdraw_avail}) expected with 0 orders and 0 positions", {}
        reconcile_log.append(f"{LIB_ACCOUNT}: lineAvailable == cashBalance == withdrawAvailable ({cash_bal})")
    else:
        reconcile_log.append(f"{LIB_ACCOUNT}: lineAvailable={line_avail}, cashBalance={cash_bal}, orders={len(ord_list)}, positions={len(port_list)}")

    payload = {
        "status": "OK",
        "reconcile_status": "PASS",
        "reconcile_notes": reconcile_log,
        "accounts": {
            LIB_ACCOUNT: {
                "account_type": acct_obj.get("type", "CASH BALANCE"),
                "balance": {
                    "creditLimit": credit_limit,
                    "cashBalance": cash_bal,
                    "lineAvailable": line_avail,
                    "withdrawAvailable": withdraw_avail,
                    "investorId": acct_obj.get("investorId"),
                },
                "positions": port_list,
                "open_orders": ord_list,
            }
        },
        "market_status": mkt_st,
    }
    return True, "PASS", payload


class BrokerSnapshotService:
    """Service to capture, validate, reconcile, and persist broker snapshots."""

    async def fetch_kss_raw(self, page=None) -> Dict[str, Any]:
        """Fetch raw KSS data via CDP or existing page."""
        if page:
            return await page.evaluate(KSS_JS_READ)

        pw, browser, ctx = await connect_cdp(cdp_url_for("kss"), "kss")
        try:
            target_page = await resolve_target_tab(ctx, "streaming", "kss")
            if not target_page:
                raise RuntimeError("No Settrade Streaming tab found on KSS CDP port 9333")
            return await target_page.evaluate(KSS_JS_READ)
        finally:
            await browser.close()
            await pw.stop()

    async def fetch_liberator_raw(self, page=None) -> Dict[str, Any]:
        """Fetch raw Liberator data via CDP or existing page."""
        if page:
            return await page.evaluate(LIB_JS_READ)

        pw, browser, ctx = await connect_cdp(cdp_url_for("lib"), "lib")
        try:
            target_page = await resolve_target_tab(ctx, "trade", "lib") or await resolve_target_tab(ctx, "any", "lib")
            if not target_page:
                raise RuntimeError("No Liberator tab found on Liberator CDP port 9334")
            return await target_page.evaluate(LIB_JS_READ)
        finally:
            await browser.close()
            await pw.stop()

    async def get_kss_snapshot(self, page=None) -> Tuple[bool, Dict[str, Any]]:
        """Fetch and reconcile KSS snapshot."""
        try:
            raw = await self.fetch_kss_raw(page=page)
            ok, reason, payload = reconcile_kss_data(raw)
            now_iso = datetime.now(TZ_BKK).isoformat()
            if not ok:
                return False, {
                    "status": "FAILED",
                    "error": reason,
                    "fetched_at": now_iso,
                    "reconcile_status": "FAIL",
                }
            payload["fetched_at"] = now_iso
            return True, payload
        except Exception as e:
            logger.error(f"KSS snapshot fetch error: {e}")
            return False, {
                "status": "ERROR",
                "error": str(e),
                "fetched_at": datetime.now(TZ_BKK).isoformat(),
                "reconcile_status": "ERROR",
            }

    async def get_liberator_snapshot(self, page=None) -> Tuple[bool, Dict[str, Any]]:
        """Fetch and reconcile Liberator snapshot."""
        try:
            raw = await self.fetch_liberator_raw(page=page)
            ok, reason, payload = reconcile_liberator_data(raw)
            now_iso = datetime.now(TZ_BKK).isoformat()
            if not ok:
                return False, {
                    "status": "FAILED",
                    "error": reason,
                    "fetched_at": now_iso,
                    "reconcile_status": "FAIL",
                }
            payload["fetched_at"] = now_iso
            return True, payload
        except Exception as e:
            logger.error(f"Liberator snapshot fetch error: {e}")
            return False, {
                "status": "ERROR",
                "error": str(e),
                "fetched_at": datetime.now(TZ_BKK).isoformat(),
                "reconcile_status": "ERROR",
            }

    async def create_snapshot(
        self,
        brokers: Optional[List[str]] = None,
        dry_run: bool = False,
        snapshot_dir: str = "data/snapshots",
        kss_page=None,
        lib_page=None,
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Create full snapshot for specified brokers, optionally saving to disk.

        Returns (overall_success, snapshot_dict, file_path).
        Fail-closed: if any requested broker fails or reconcile fails,
        overall_success is False.
        """
        target_brokers = [b.lower() for b in (brokers or ["kss", "lib"])]
        now = datetime.now(TZ_BKK)
        now_iso = now.isoformat()
        time_stamp_str = now.strftime("%Y-%m-%d_%H%M")

        snapshot: Dict[str, Any] = {
            "fetched_at": now_iso,
            "status": "OK",
            "brokers": {},
        }

        overall_success = True
        fail_reasons = []

        if "kss" in target_brokers:
            ok_kss, kss_data = await self.get_kss_snapshot(page=kss_page)
            snapshot["brokers"]["kss"] = kss_data
            if not ok_kss:
                overall_success = False
                fail_reasons.append(f"KSS: {kss_data.get('error', 'unknown error')}")

        if "lib" in target_brokers or "liberator" in target_brokers:
            ok_lib, lib_data = await self.get_liberator_snapshot(page=lib_page)
            snapshot["brokers"]["liberator"] = lib_data
            if not ok_lib:
                overall_success = False
                fail_reasons.append(f"Liberator: {lib_data.get('error', 'unknown error')}")

        if not overall_success:
            snapshot["status"] = "FAIL_CLOSED"
            snapshot["errors"] = fail_reasons
            return False, snapshot, None

        # Propagate SET market status to top-level or KSS if available
        lib_mkt = snapshot.get("brokers", {}).get("liberator", {}).get("market_status")
        if lib_mkt:
            snapshot["market_status"] = lib_mkt
            if "kss" in snapshot.get("brokers", {}):
                snapshot["brokers"]["kss"]["market_status"] = lib_mkt

        saved_path = None
        if not dry_run:
            os.makedirs(snapshot_dir, exist_ok=True)
            file_name = f"{time_stamp_str}.json"
            saved_path = os.path.join(snapshot_dir, file_name)
            if os.path.exists(saved_path):
                # Never overwrite an existing closed snapshot file
                # Fail-closed to protect snapshot immutability
                snapshot["status"] = "FAIL_CLOSED"
                snapshot["errors"] = [f"Snapshot file {saved_path} already exists. Refusing to overwrite closed snapshot."]
                return False, snapshot, None

            with open(saved_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

        return True, snapshot, saved_path


broker_snapshot_service = BrokerSnapshotService()
