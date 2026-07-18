from typing import List, Dict, Any

class InsightGenerator:
    """Generates natural language insights from autonomous analysis."""
    
    def generate_insights(self, analysis: Dict[str, Any]) -> List[str]:
        """
        Convert raw analysis data into human-readable insights.
        
        Args:
            analysis: Output from AutonomousAnalyzer.analyze_portfolio()
        
        Returns:
            List of insight strings (with emoji prefixes for visual clarity)
        """
        insights = []
        
        if "error" in analysis:
            return [f"⚠️ Analysis Error: {analysis['error']}"]
        
        # Portfolio Summary
        summary = analysis.get("portfolio_summary", {})
        if summary:
            insights.append(
                f"📊 Portfolio: {summary.get('total_holdings', 0)} holdings "
                f"({summary.get('stock_count', 0)} stocks, {summary.get('etf_count', 0)} ETFs)"
            )
        
        # ETF Overlap Alerts
        overlaps = analysis.get("etf_overlap_alerts", [])
        for overlap in overlaps[:3]:  # Top 3
            severity_emoji = "🔴" if overlap["severity"] == "high" else "🟡"
            insights.append(
                f"{severity_emoji} High Exposure: **{overlap['stock']}** = {overlap['combined_exposure']:.1f}% "
                f"(Direct: {overlap['direct_exposure_pct']:.1f}% + "
                f"{overlap['etf']}: {overlap['etf_exposure_pct']:.1f}%)"
            )
        
        # Concentration Risks
        risks = analysis.get("concentration_risks", [])
        for risk in risks[:2]:  # Top 2
            if risk["source_count"] > 1:
                insights.append(
                    f"🎯 Concentration: **{risk['stock']}** appears in {risk['source_count']} holdings "
                    f"(Total: {risk['total_exposure_pct']:.1f}%)"
                )
        
        # Hidden Exposures
        hidden = analysis.get("hidden_exposures", [])
        for exp in hidden[:2]:  # Top 2
            if exp["suggestion"] == "consider_direct_investment":
                insights.append(
                    f"💡 Opportunity: {exp['exposure_pct']:.1f}% exposure to **{exp['stock']}** "
                    f"via ETFs (no direct holding)"
                )
            else:
                insights.append(
                    f"👁️ Hidden Exposure: {exp['exposure_pct']:.1f}% to **{exp['stock']}** via ETFs"
                )
        
        # If no insights, provide a positive message
        if len(insights) == 1:  # Only summary
            insights.append("✅ No concentration risks or significant overlaps detected")
        
        return insights
    
    def generate_welcome_message(self, analysis: Dict[str, Any]) -> str:
        """Generate a proactive welcome message with top insights."""
        insights = self.generate_insights(analysis)
        
        # Skip the summary line for welcome message
        key_insights = [i for i in insights if not i.startswith("📊")]
        
        if not key_insights:
            return "👋 Welcome! Your portfolio looks well-balanced. Ask me anything!"
        
        welcome = "👋 **Welcome!** I've analyzed your portfolio. Here's what I found:\n\n"
        welcome += "\n".join(key_insights[:4])  # Top 4 insights
        welcome += "\n\n💬 Ask me anything or say 'explain' for details on any insight."
        
        return welcome

# Singleton instance
insight_generator = InsightGenerator()
