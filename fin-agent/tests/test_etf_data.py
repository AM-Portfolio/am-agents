import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from shared.core.db import db_client

def test_etf_access():
    print("--- Testing ETF Data Access ---")
    if not db_client.client:
        print("❌ DB Client not connected")
        return

    try:
        # Access 'mutual_funds' database
        mf_db = db_client.client["mutual_funds"]
        etf_coll = mf_db["etf_holdings"]
        
        # Try to find NIFTYBEES
        niftybees = etf_coll.find_one({"symbol": "NIFTYBEES"})
        
        if niftybees:
            print(f"✅ Found NIFTYBEES!")
            print(f"Name: {niftybees.get('etf_name')}")
            holdings = niftybees.get('holdings', [])
            print(f"Holdings count: {len(holdings)}")
            if holdings:
                print(f"Top holding: {holdings[0].get('stock_name')} ({holdings[0].get('percentage')}%)")
        else:
            print("❌ NIFTYBEES not found in mutual_funds.etf_holdings")
            
        # Count total
        count = etf_coll.count_documents({})
        print(f"\n📊 Total ETFs in Database: {count}")

    except Exception as e:
        print(f"❌ Error accessing mutual_funds DB: {e}")

if __name__ == "__main__":
    test_etf_access()
