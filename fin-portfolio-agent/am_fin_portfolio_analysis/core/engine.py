from typing import List, Dict, Any, Optional
from shared.core.db import db_client
from ..data.mock_data import (
    EQUITY_PORTFOLIO, 
    LIVE_PRICES, 
    BENCHMARK_INDEX, 
    ETFS, 
    MUTUAL_FUNDS,
    get_live_price
)

class FinanceEngine:
    """Core intelligence engine for financial calculations and analysis."""

    def calculate_portfolio_performance(self) -> Dict[str, Any]:
        """
        Calculate the overall portfolio performance.
        Aggregates multiple buy entries for the same stock.
        """
        total_invested = 0.0
        total_current_value = 0.0
        
        # Use a dict to aggregate holdings: { "StockName": {qty, invested, current_val} }
        aggregated_holdings = {}

        # 1. Try fetching from MongoDB
        # We default to a known owner if expected, or just get the first one for now
        # Per the user sample, owner is 'ssd2658'. Using None gets the first document.
        real_portfolio_doc = db_client.get_portfolio(owner_id="ssd2658")
        
        # 2. Determine source data
        raw_holdings = []
        if real_portfolio_doc and "equities" in real_portfolio_doc:
            # Map MongoDB format to our engine format
            # MongoDB: { "equity_symbol": "AARTIIND", "quantity": 8, "avgBuyingPrice": 592.0562, ... }
            # Engine Expected: { "stock_name": "AARTIIND", "quantity": 8, "buy_price": 592.0562 }
            for item in real_portfolio_doc["equities"]:
                # Determine Asset Type
                # Logic: If ISIN starts with 'INF', it's likely a Fund (ETF/MF).
                isin = item.get("isin", "")
                is_file_etf = isin.startswith("INF")
                
                raw_holdings.append({
                    "stock_name": item.get("equity_symbol"),
                    "quantity": item.get("quantity"),
                    "buy_price": item.get("avgBuyingPrice"),
                    "isin": isin,
                    "is_etf": is_file_etf,
                    "symbol": item.get("equity_symbol") # Keep rough symbol
                })
        else:
            # Fallback to mock data
            raw_holdings = EQUITY_PORTFOLIO

        for holding in raw_holdings:
            stock = holding["stock_name"]
            qty = holding["quantity"]
            buy_price = holding["buy_price"]
            
            invested = qty * buy_price
            current_price = get_live_price(stock)
            current_val = qty * current_price
            
            # Helper for clean key in dict
            # If stock name is None (data issue), use ISIN or a placeholder
            key = stock if stock else (holding.get("isin") or "UNKNOWN_ASSET")
            
            if key not in aggregated_holdings:
                aggregated_holdings[key] = {
                    "stock_name": key,
                    "quantity": 0,
                    "invested_value": 0.0,
                    "current_value": 0.0,
                    "current_price": current_price,
                    "is_etf": holding.get("is_etf", False),
                    "isin": holding.get("isin", "")
                }
            
            # Accumulate
            aggregated_holdings[key]["quantity"] += qty
            aggregated_holdings[key]["invested_value"] += invested
            aggregated_holdings[key]["current_value"] += current_val
            
            # Totals
            total_invested += invested
            total_current_value += current_val

        # Finalize list and calculate P&L per stock
        final_holdings_list = []
        for stock, data in aggregated_holdings.items():
            inv = data["invested_value"]
            curr = data["current_value"]
            pnl = curr - inv
            pnl_pct = (pnl / inv * 100) if inv > 0 else 0.0
            
            # formatting
            data["average_buy_price"] = round(inv / data["quantity"], 2) if data["quantity"] > 0 else 0.0
            data["pnl"] = round(pnl, 2)
            data["pnl_pct"] = round(pnl_pct, 2)
            
            final_holdings_list.append(data)

        total_pnl = total_current_value - total_invested
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

        return {
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "holdings": final_holdings_list
        }

    def compare_portfolio_vs_benchmark(self) -> Dict[str, Any]:
        """
        Compare portfolio returns against NIFTY 50.
        """
        pf_performance = self.calculate_portfolio_performance()
        pf_return_pct = pf_performance["total_pnl_pct"]
        
        benchmark_returns = BENCHMARK_INDEX["returns"]
        
        # Simple comparison against 1y benchmark return
        benchmark_1y = benchmark_returns.get("1y", 0.0)
        
        outperformance = pf_return_pct - benchmark_1y
        
        return {
            "portfolio_return_pct": pf_return_pct,
            "benchmark_name": BENCHMARK_INDEX["index_name"],
            "benchmark_return_1y": benchmark_1y,
            "outperformance": outperformance,
            "status": "Outperforming" if outperformance > 0 else "Underperforming"
        }

    def analyze_allocation(self, stock_name: str) -> Dict[str, Any]:
        """
        Analyze the allocation of a specific stock in the user's portfolio
        vs the Benchmark (NIFTY 50).
        """
        # 1. Calculate Portfolio Weightage
        pf_perf = self.calculate_portfolio_performance()
        total_val = pf_perf["total_current_value"]
        
        stock_holding = next((h for h in pf_perf["holdings"] if h["stock_name"].lower() == stock_name.lower()), None)
        
        if not stock_holding:
            user_weightage = 0.0
        else:
            user_weightage = (stock_holding["current_value"] / total_val * 100) if total_val > 0 else 0.0

        # 2. Get Benchmark Weightage
        benchmark_constituent = next(
            (c for c in BENCHMARK_INDEX["constituents"] if c["stock_name"].lower() == stock_name.lower()), 
            None
        )
        benchmark_weightage = benchmark_constituent["weightage"] if benchmark_constituent else 0.0

        return {
            "stock_name": stock_name,
            "user_portfolio_weightage": round(user_weightage, 2),
            "benchmark_weightage": benchmark_weightage,
            "difference": round(user_weightage - benchmark_weightage, 2),
            "status": "Overweight" if user_weightage > benchmark_weightage else "Underweight"
        }
    
    def get_etf_details(self, etf_name: str) -> Optional[Dict[str, Any]]:
        """Get details for a specific ETF (from Real DB)."""
        if not etf_name:
            return None
            
        # Try fetching from MongoDB first
        # Note: etf_name from User query might be 'NIFTYBEES' or 'Nifty Bees' or 'Nippon India...'
        # We'll try to match it against symbol first, then name.
        
        # 1. Direct symbol lookup
        real_etf = db_client.get_etf_holdings(etf_name)
        
        if real_etf:
            # Map DB format to Engine format
            # DB: holdings=[{stock_name, percentage, ...}]
            # Engine: holdings=[{stock_name, weightage}]
            mapped_holdings = []
            for h in real_etf.get("holdings", []):
                mapped_holdings.append({
                    "stock_name": h.get("stock_name"),
                    "weightage": h.get("percentage")
                })
            
            return {
                "name": real_etf.get("etf_name"),
                "symbol": real_etf.get("symbol"),
                "category": "Index ETF", # Defaulting for now
                "returns": { "1y": 12.0 }, # Placeholder if not in DB
                "holdings": mapped_holdings,
                "expense_ratio": 0.05,
                "benchmark": "NIFTY 50"
            }
            
        # Fallback to Mock Data
        return next((e for e in ETFS if e["name"].lower() == etf_name.lower()), None)

    def get_mf_details(self, mf_name: str) -> Optional[Dict[str, Any]]:
        """Get details for a specific Mutual Fund."""
        return next((m for m in MUTUAL_FUNDS if m["fund_name"].lower() == mf_name.lower()), None)
    
    def get_all_holdings(self) -> List[Dict[str, Any]]:
        # Fetch fresh every time
        real_portfolio_doc = db_client.get_portfolio(owner_id="ssd2658")
        if real_portfolio_doc and "equities" in real_portfolio_doc:
             mapped_holdings = []
             for item in real_portfolio_doc["equities"]:
                mapped_holdings.append({
                    "stock_name": item.get("equity_symbol"),
                    "quantity": item.get("quantity"),
                    "buy_price": item.get("avgBuyingPrice")
                })
             return mapped_holdings
        return EQUITY_PORTFOLIO

    def calculate_etf_overlap(self, etf_symbol_or_isin: str) -> Dict[str, Any]:
        """
        Calculate overlap between a specific ETF held by the user and their direct stocks.
        """
        if not etf_symbol_or_isin:
            return {"error": "No ETF symbol provided."}

        # 1. Get User's Portfolio
        pf_perf = self.calculate_portfolio_performance()
        user_holdings = {h["stock_name"]: h for h in pf_perf["holdings"]}
        
        # 2. Find the ETF in User's Portfolio (by symbol or ISIN)
        target_etf = None
        search_key = etf_symbol_or_isin.lower().strip()
        
        for h in pf_perf["holdings"]:
            # Match by Symbol (e.g. NIFTYBEES) or ISIN
            # Safe lower() check on stock_name and isin
            h_name = (h.get("stock_name") or "").lower()
            h_isin = (h.get("isin") or "").lower()
            
            if (h_name == search_key) or (h_isin == search_key):
                target_etf = h
                break
        
        if not target_etf:
            return {"error": f"ETF '{etf_symbol_or_isin}' not found in your portfolio."}

        # 3. Fetch ETF's internal holdings from DB
        # Use symbol from the portfolio entry
        etf_name = target_etf["stock_name"]
        if not etf_name: # Handle case where name is missing but found by ISIN
             # Fallback: try to see if DB can find it by ISIN directly in future, 
             # but for now we rely on the DB client utilizing symbol mainly.
             # If symbol is None, we can't look it up easily in current architecture without ISIN lookup
             return {"error": f"ETF found in portfolio but missing symbol name. Cannot fetch details."}

        etf_details = self.get_etf_details(etf_name)
        if not etf_details:
             return {"error": f"Could not fetch internal details for ETF '{etf_name}' from database."}
             
        if not etf_details.get("holdings"):
             return {"error": f"ETF '{etf_name}' has no holdings data available."}

        # 4. Calculate Overlap
        etf_holdings = etf_details["holdings"] # list of {stock_name, weightage}
        
        overlaps = []
        for stock in etf_holdings:
            s_name = stock["stock_name"]
            etf_weight = stock["weightage"]
            
            # Check if user owns this stock directly
            # Simple name matching (could be improved with ISIN if available in ETF payload)
            # We'll try basic fuzzy match or exact match
            direct_holding = None
            
            # Try exact match first
            if s_name in user_holdings:
                direct_holding = user_holdings[s_name]
            else:
                 # Try case-insensitive and partial matching
                 # ETF might have "Cipla Ltd." while portfolio has "CIPLA"
                 for u_name, u_data in user_holdings.items():
                     # Safe string check
                     u_name_safe = (u_name if u_name else "").lower().strip()
                     s_name_safe = (s_name if s_name else "").lower().strip()
                     
                     # Exact match (case-insensitive)
                     if u_name_safe == s_name_safe:
                         direct_holding = u_data
                         break
                     
                     # Partial match: Check if one contains the other
                     # "CIPLA" in "Cipla Ltd." or vice versa
                     # Extract the core company name (first word before space/dot)
                     u_core = u_name_safe.split()[0] if u_name_safe else ""
                     s_core = s_name_safe.split()[0] if s_name_safe else ""
                     
                     # Match if core names match (e.g., "cipla" == "cipla")
                     if u_core and s_core and u_core == s_core:
                         direct_holding = u_data
                         break
            
            if direct_holding:
                overlaps.append({
                    "stock_name": s_name,
                    "etf_weight": etf_weight,
                    "direct_value": direct_holding["current_value"],
                    "direct_quantity": direct_holding["quantity"]
                })
                
        # Sort by weightage for top 10 display
        all_holdings_sorted = sorted(etf_holdings, key=lambda x: x.get("weightage", 0), reverse=True)
        top_10 = all_holdings_sorted[:10]
        
        return {
            "etf_name": etf_details.get("name"),
            "etf_symbol": etf_details.get("symbol"),
            "total_holdings_count": len(etf_holdings),
            "overlap_count": len(overlaps),
            "overlapping_stocks": overlaps,
            "top_10_holdings": top_10
        }

    def get_benchmark_returns(self) -> Dict[str, float]:
        return BENCHMARK_INDEX["returns"]

engine = FinanceEngine()
