"""
Test Script: Live SBL Intelligence & Decision Audit on Krungsri TradeMan.
Audits candidate stock symbols:
1. CPALL, DELTA, AOT (Expected: BORROW_ALLOWED or OUT_OF_STOCK depending on pool)
2. BANPU, SCB (Expected: CAUTION_XD_RISK if in XD calendar)
3. NONEXISTENT_STOCK (Expected: OUT_OF_STOCK)
"""

import asyncio
import json
from app.services.sbl_intelligence_service import sbl_intelligence_service


async def main():
    test_symbols = ["CPALL", "DELTA", "AOT", "BANPU", "SCB", "XYZ_OUT"]
    print(f"\n================================================================================")
    print(f"📊 SBL CANDIDATE AUDIT TEST: {test_symbols}")
    print(f"================================================================================")

    res = await sbl_intelligence_service.audit_sbl_candidates(test_symbols)
    
    print("\n[Audit Summary]")
    print(json.dumps(res.get("summary", {}), indent=2, ensure_ascii=False))

    print("\n[Candidates Verdicts]")
    for sym, details in res.get("candidates", {}).items():
        print(f"\n--- {sym} ---")
        print(f"  Verdict: {details.get('verdict')} ({details.get('badge')})")
        print(f"  Available Qty: {details.get('available_qty', 0):,} shares")
        print(f"  Borrow Fee: {details.get('borrow_fee_pct', 0.0)}% per year")
        print(f"  Daily Fee per 100k THB: ~฿{details.get('daily_fee_per_100k_thb', 0.0)}/day")
        print(f"  Action Allowed: {details.get('action_allowed')}")
        if details.get('warning_message'):
            print(f"  Warning: {details.get('warning_message')}")
        if details.get('recommendation'):
            print(f"  Recommendation: {details.get('recommendation')}")

    print("\n[Strategic Advice]")
    print(res.get("strategic_advice"))
    print(f"\n================================================================================")


if __name__ == "__main__":
    asyncio.run(main())
