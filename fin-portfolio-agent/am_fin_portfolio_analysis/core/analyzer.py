from typing import Dict, Any, List
import logging
from .engine import engine
from .cache import cache

logger = logging.getLogger(__name__)

class AutonomousAnalyzer:
    """Autonomous portfolio analysis engine that proactively discovers insights."""
    
    def __init__(self, concentration_threshold: float = 15.0, cache_ttl: int = 3600):
        """
        Args:
            concentration_threshold: % threshold for flagging high exposure (default 15%)
            cache_ttl: Cache time-to-live in seconds (default 1 hour)
        """
        self.concentration_threshold = concentration_threshold
        self.cache_ttl = cache_ttl
    
    def analyze_portfolio(self) -> Dict[str, Any]:
        """Run comprehensive autonomous analysis on the portfolio (with caching)."""
        # Generate cache key based on portfolio state
        cache_key = cache.make_key("autonomous_analysis", self.concentration_threshold)
        
        # Try to get from cache
        cached_result = cache.get(cache_key, ttl_seconds=self.cache_ttl)
        if cached_result:
            logger.info("Returning cached autonomous analysis")
            return cached_result
        
        # Cache miss - run analysis
        logger.info("Running fresh autonomous analysis")
        try:
            pf_perf = engine.calculate_portfolio_performance()
            
            insights = {
                "etf_overlap_alerts": self._detect_etf_overlaps(pf_perf),
                "concentration_risks": self._detect_concentration(pf_perf),
                "hidden_exposures": self._find_hidden_exposures(pf_perf),
                "portfolio_summary": {
                    "total_value": pf_perf["total_current_value"],
                    "total_holdings": len(pf_perf["holdings"]),
                    "etf_count": len([h for h in pf_perf["holdings"] if h.get("is_etf")]),
                    "stock_count": len([h for h in pf_perf["holdings"] if not h.get("is_etf")])
                }
            }
            
            # Store in cache
            cache.set(cache_key, insights)
            return insights
        except Exception as e:
            logger.error(f"Error in autonomous analysis: {e}")
            return {"error": str(e)}
    
    def _detect_etf_overlaps(self, pf_perf: Dict) -> List[Dict]:
        """Detect overlaps between ETF holdings and direct stocks."""
        alerts = []
        
        # Get all ETFs in portfolio
        etfs = [h for h in pf_perf["holdings"] if h.get("is_etf")]
        
        # Get all direct stocks (non-ETFs)
        direct_stocks = {h["stock_name"]: h for h in pf_perf["holdings"] if not h.get("is_etf")}
        
        total_portfolio_value = pf_perf["total_current_value"]
        
        for etf in etfs:
            etf_symbol = etf["stock_name"]
            
            # Get ETF details and holdings
            try:
                overlap_result = engine.calculate_etf_overlap(etf_symbol)
                
                if "error" in overlap_result:
                    continue
                
                # Check each overlapping stock
                for overlap in overlap_result.get("overlapping_stocks", []):
                    stock_name = overlap["stock_name"]
                    etf_weight = overlap["etf_weight"]
                    direct_value = overlap["direct_value"]
                    
                    # Calculate exposures as % of total portfolio
                    direct_exposure_pct = (direct_value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
                    
                    # ETF exposure to this stock = (ETF weight in stock) * (ETF value in portfolio)
                    etf_value = etf["current_value"]
                    etf_exposure_to_stock = (etf_weight / 100) * etf_value
                    etf_exposure_pct = (etf_exposure_to_stock / total_portfolio_value * 100) if total_portfolio_value > 0 else 0
                    
                    combined_exposure = direct_exposure_pct + etf_exposure_pct
                    
                    # Flag if combined exposure exceeds threshold
                    if combined_exposure >= self.concentration_threshold:
                        alerts.append({
                            "stock": stock_name,
                            "etf": etf_symbol,
                            "direct_exposure_pct": round(direct_exposure_pct, 2),
                            "etf_exposure_pct": round(etf_exposure_pct, 2),
                            "combined_exposure": round(combined_exposure, 2),
                            "etf_weight": etf_weight,
                            "severity": "high" if combined_exposure >= 20 else "medium"
                        })
            except Exception as e:
                logger.warning(f"Could not analyze overlap for {etf_symbol}: {e}")
                continue
        
        # Sort by combined exposure (highest first)
        alerts.sort(key=lambda x: x["combined_exposure"], reverse=True)
        return alerts
    
    def _detect_concentration(self, pf_perf: Dict) -> List[Dict]:
        """Detect stocks with high concentration across multiple holdings."""
        stock_exposure = {}  # {stock_name: {total_value, sources: [...]}}
        total_value = pf_perf["total_current_value"]
        
        # Track direct holdings
        for holding in pf_perf["holdings"]:
            if not holding.get("is_etf"):
                stock_name = holding["stock_name"]
                if stock_name not in stock_exposure:
                    stock_exposure[stock_name] = {"total_value": 0, "sources": []}
                
                stock_exposure[stock_name]["total_value"] += holding["current_value"]
                stock_exposure[stock_name]["sources"].append({
                    "type": "direct",
                    "value": holding["current_value"]
                })
        
        # Track ETF exposures
        etfs = [h for h in pf_perf["holdings"] if h.get("is_etf")]
        for etf in etfs:
            try:
                overlap_result = engine.calculate_etf_overlap(etf["stock_name"])
                if "error" in overlap_result:
                    continue
                
                # Add all stocks in this ETF (not just overlaps)
                for stock in overlap_result.get("top_10_holdings", []):
                    stock_name = stock["stock_name"]
                    weight = stock["weightage"]
                    
                    if stock_name not in stock_exposure:
                        stock_exposure[stock_name] = {"total_value": 0, "sources": []}
                    
                    etf_exposure_value = (weight / 100) * etf["current_value"]
                    stock_exposure[stock_name]["total_value"] += etf_exposure_value
                    stock_exposure[stock_name]["sources"].append({
                        "type": "etf",
                        "etf_name": etf["stock_name"],
                        "value": etf_exposure_value,
                        "weight": weight
                    })
            except Exception as e:
                logger.warning(f"Could not analyze concentration for ETF {etf['stock_name']}: {e}")
                continue
        
        # Generate concentration alerts
        risks = []
        for stock_name, data in stock_exposure.items():
            exposure_pct = (data["total_value"] / total_value * 100) if total_value > 0 else 0
            source_count = len(data["sources"])
            
            # Flag if appears in multiple sources OR high single exposure
            if source_count > 1 or exposure_pct >= self.concentration_threshold:
                risks.append({
                    "stock": stock_name,
                    "total_exposure_pct": round(exposure_pct, 2),
                    "source_count": source_count,
                    "sources": data["sources"],
                    "severity": "high" if exposure_pct >= 20 else "medium"
                })
        
        # Sort by exposure (highest first)
        risks.sort(key=lambda x: x["total_exposure_pct"], reverse=True)
        return risks
    
    def _find_hidden_exposures(self, pf_perf: Dict) -> List[Dict]:
        """Find stocks user doesn't own directly but has significant ETF exposure to."""
        hidden = []
        
        # Get direct stock names
        direct_stocks = {h["stock_name"].lower() for h in pf_perf["holdings"] if not h.get("is_etf")}
        
        # Track all stocks in ETFs
        etf_exposures = {}  # {stock_name: total_exposure_value}
        total_value = pf_perf["total_current_value"]
        
        etfs = [h for h in pf_perf["holdings"] if h.get("is_etf")]
        for etf in etfs:
            try:
                overlap_result = engine.calculate_etf_overlap(etf["stock_name"])
                if "error" in overlap_result:
                    continue
                
                for stock in overlap_result.get("top_10_holdings", []):
                    stock_name = stock["stock_name"]
                    weight = stock["weightage"]
                    
                    # Skip if user owns this directly
                    if stock_name.lower() in direct_stocks:
                        continue
                    
                    if stock_name not in etf_exposures:
                        etf_exposures[stock_name] = {"value": 0, "etfs": []}
                    
                    exposure_value = (weight / 100) * etf["current_value"]
                    etf_exposures[stock_name]["value"] += exposure_value
                    etf_exposures[stock_name]["etfs"].append({
                        "etf": etf["stock_name"],
                        "weight": weight
                    })
            except Exception as e:
                logger.warning(f"Could not analyze hidden exposures for {etf['stock_name']}: {e}")
                continue
        
        # Flag significant hidden exposures
        for stock_name, data in etf_exposures.items():
            exposure_pct = (data["value"] / total_value * 100) if total_value > 0 else 0
            
            if exposure_pct >= 5.0:  # 5% threshold for "significant"
                hidden.append({
                    "stock": stock_name,
                    "exposure_pct": round(exposure_pct, 2),
                    "etfs": data["etfs"],
                    "suggestion": "consider_direct_investment" if exposure_pct >= 10 else "monitor"
                })
        
        # Sort by exposure (highest first)
        hidden.sort(key=lambda x: x["exposure_pct"], reverse=True)
        return hidden

# Singleton instance
autonomous_analyzer = AutonomousAnalyzer()
