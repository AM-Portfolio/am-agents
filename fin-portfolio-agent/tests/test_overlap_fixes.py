import sys
import os
import json

# Ensure project root is in path
sys.path.append(os.getcwd())

from am_fin_portfolio_analysis.core.engine import engine
from shared.core.db import db_client

def test_overlap_fixes():
    print("--- 🛠️ Verifying ETF Overlap Fixes ---")

    # 1. Test Case Insensitivity (User asked for 'BankBees')
    print("\n1. Testing 'BankBees' (Mixed Case)...")
    result = engine.calculate_etf_overlap("BankBees")
    if "error" in result:
        print(f"❌ Failed: {result['error']}")
    else:
        print(f"✅ Success! Found: {result.get('etf_name')} (Overlap: {result.get('overlap_count')})")

    # 2. Test ISIN Lookup (User asked for 'INF204KB15I9')
    # Note: Using BANKBEES ISIN 'INF204KB15I9' from previous logs
    isin = "INF204KB15I9"
    print(f"\n2. Testing ISIN '{isin}'...")
    result_isin = engine.calculate_etf_overlap(isin)
    if "error" in result_isin:
        print(f"❌ Failed: {result_isin['error']}")
    else:
        print(f"✅ Success! Found: {result_isin.get('etf_name')}")

    # 2.1 Verify Direct DB Lookup via ISIN (bypassing portfolio logic)
    print(f"\n2.1 Direct DB Lookup for '{isin}'...")
    direct_doc = db_client.get_etf_holdings(isin)
    if direct_doc:
        print(f"✅ DB Lookup Success! Found Symbol: {direct_doc.get('symbol')}")
    else:
        print("❌ DB Lookup Failed!")

    # 3. Test Unknown ETF (Graceful Error)
    print("\n3. Testing 'FAKE_ETF'...")
    result_fake = engine.calculate_etf_overlap("FAKE_ETF")
    if "error" in result_fake:
        print(f"✅ Correctly returned error: {result_fake['error']}")
    else:
        print(f"❌ Argument should have failed but got: {result_fake}")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    test_overlap_fixes()
