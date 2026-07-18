import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from shared.core.db import db_client
from am_fin_portfolio_analysis.core.engine import engine

def test_mongo_connection():
    print("--- Testing MongoDB Connection ---")
    if db_client.client:
        print(f"✅ Client initialized using: {db_client.uri.split('@')[-1]}")
    else:
        print("❌ Client initialization failed")
        return

    portfolio = db_client.get_portfolio(owner_id="ssd2658")
    if portfolio:
        print(f"✅ Portfolio found for owner: {portfolio.get('owner')}")
        print(f"Total Equities: {len(portfolio.get('equities', []))}")
        
        # Determine if it's the specific zerodha portfolio from the sample
        if portfolio.get("name") == "zerodha":
            print("✅ Verified correct portfolio (zerodha)")
    else:
        print("❌ Portfolio not found")

def test_engine_integration():
    print("\n--- Testing Engine Integration ---")
    perf = engine.calculate_portfolio_performance()
    holdings = perf["holdings"]
    
    # Check for a stock that exists in the sample but NOT in the mock data
    # (Mock data usually has Reliance, TCS. Sample has AARTIIND, AMBUJACEM)
    checklist = ["AARTIIND", "AMBUJACEM", "ANGELONE"]
    found_count = 0
    
    print(f"Total Engine Holdings: {len(holdings)}")
    for h in holdings:
        if h["stock_name"] in checklist:
            found_count += 1
            print(f"✅ Found expected stock: {h['stock_name']}")
            
    if found_count > 0:
        print("✅ Engine is successfully using MongoDB data!")
    else:
        print("❌ Engine appears to still be using Mock data (or DB is empty)")

if __name__ == "__main__":
    test_mongo_connection()
    test_engine_integration()
