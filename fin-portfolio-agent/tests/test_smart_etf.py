import sys
import os
import json

# Ensure project root is in path
sys.path.append(os.getcwd())

from am_fin_portfolio_analysis.core.engine import engine

def test_smart_etf_detection():
    print("--- 🧠 Testing Smart ETF Detection & Overlap ---")
    
    # 1. Check if Engine Auto-Detects ETFs in Portfolio
    print("\n1. Checking Portfolio Classification...")
    perf = engine.calculate_portfolio_performance()
    holdings = perf["holdings"]
    
    etf_count = 0
    stock_count = 0
    
    for h in holdings:
        if h.get("is_etf"):
            etf_count += 1
            print(f"   ✅ Detected ETF: {h['stock_name']} (ISIN: {h.get('isin')})")
        else:
            stock_count += 1
            
    print(f"   Summary: Found {etf_count} ETFs and {stock_count} Stocks.")
    
    if etf_count == 0:
        print("   ⚠️ No ETFs detected. Check if DB has holdings with ISIN starting with 'INF'.")
    
    # 2. Test Overlap Logic
    # We force 'BANKBEES' as we know it's in the list and likely has data
    target_etf = "BANKBEES"
    
    print(f"\n2. Testing Overlap for: {target_etf}")
    overlap_result = engine.calculate_etf_overlap(target_etf)
    
    if "error" in overlap_result:
        print(f"   ❌ Overlap Error: {overlap_result['error']}")
    else:
        print(f"   ✅ Overlap Calculation Successful!")
        print(f"   ETF Name: {overlap_result.get('etf_name')}")
        print(f"   Overlap Count: {overlap_result.get('overlap_count')} stocks")
        
        if overlap_result.get('overlap_count') > 0:
            top_overlap = overlap_result['overlapping_stocks'][0]
            print(f"   Example Overlap: {top_overlap['stock_name']} (ETF Weight: {top_overlap['etf_weight']}%)")
        else:
            print("   (No overlapping stocks found, but calculation ran successully)")
            
    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_smart_etf_detection()
