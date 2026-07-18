import json
from typing import Dict, Any, List
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import DuckDuckGoSearchException
from am_fin_portfolio_analysis.core.engine import engine

# --- Tool Schemas (OpenAI/Together Format) ---

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_summary",
            "description": "Get overall portfolio performance including total value, P&L, and invested amount.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_holding_details",
            "description": "Get detailed performance metrics for a specific stock in the user's portfolio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_name": {
                        "type": "string",
                        "description": "The name of the stock (e.g., 'Reliance', 'TCS')."
                    }
                },
                "required": ["stock_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_stocks",
            "description": "Compare the performance of two stocks from the user's portfolio side-by-side.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_parent": {
                        "type": "string",
                        "description": "The first stock name."
                    },
                    "stock_comparison": {
                        "type": "string",
                        "description": "The second stock name to compare against."
                    }
                },
                "required": ["stock_parent", "stock_comparison"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_benchmark_comparison",
            "description": "Compare the user's portfolio performance against the NIFTY 50 benchmark.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_holdings_batch",
            "description": "Get detailed performance metrics for a list of stocks in the user's portfolio. Use this when the user asks for multiple stocks at once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_names": {
                        "type": "array",
                        "items": { "type": "string" },
                        "description": "The list of stock names (e.g., ['Reliance', 'TCS', 'HDFC'])."
                    }
                },
                "required": ["stock_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fund_details",
            "description": "Get details about an ETF or Mutual Fund.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fund_name": {
                        "type": "string",
                        "description": "The name of the ETF or Mutual Fund."
                    }
                },
                "required": ["fund_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the live internet for stock news, market trends, or general info not found in the portfolio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'HDFC Bank dividends 2024')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_etf_overlap",
            "description": "Calculate true portfolio exposure by overlapping a user's ETF holding with their direct stock holdings. Use this when the user asks about exposure, overlap, or 'what is inside X ETF'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "etf_symbol": {
                        "type": "string",
                        "description": "The symbol or name of the ETF to analyze (e.g., 'NIFTYBEES')."
                    }
                },
                "required": ["etf_symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_etfs",
            "description": "Count the number of ETFs in the user's portfolio. ETFs are identified by ISINs starting with 'INF'. Use this when the user asks 'how many ETFs do I have' or similar questions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

# --- Tool Implementation Functions ---

def get_portfolio_summary() -> str:
    data = engine.calculate_portfolio_performance()
    return f"Portfolio Performance: {json.dumps(data, indent=2)}"

def get_holding_details(stock_name: str) -> str:
    pf = engine.calculate_portfolio_performance()
    # Fuzzy match logic
    holding = next((h for h in pf["holdings"] if stock_name.lower() in h["stock_name"].lower()), None)
    if holding:
        return f"Holding Details for {stock_name}: {json.dumps(holding, indent=2)}"
    else:
        return f"User does not hold {stock_name}."

def get_holdings_batch(stock_names: List[str]) -> str:
    pf = engine.calculate_portfolio_performance()
    results = {}
    for name in stock_names:
        holding = next((h for h in pf["holdings"] if name.lower() in h["stock_name"].lower()), None)
        results[name] = holding if holding else "Not Found"
    return f"Batch Holdings Results: {json.dumps(results, indent=2)}"

def compare_stocks(stock_parent: str, stock_comparison: str) -> str:
    pf = engine.calculate_portfolio_performance()
    holdings = pf["holdings"]
    
    data_1 = next((h for h in holdings if stock_parent.lower() in h["stock_name"].lower()), None) if stock_parent else None
    data_2 = next((h for h in holdings if stock_comparison.lower() in h["stock_name"].lower()), None) if stock_comparison else None
    
    result = {
        f"{stock_parent}": data_1 if data_1 else "Not Found",
        f"{stock_comparison}": data_2 if data_2 else "Not Found"
    }
    return f"Comparison Data: {json.dumps(result, indent=2)}"

def get_benchmark_comparison() -> str:
    data = engine.compare_portfolio_vs_benchmark()
    return f"Benchmark Comparison: {json.dumps(data, indent=2)}"

def get_fund_details(fund_name: str) -> str:
    etf = engine.get_etf_details(fund_name)
    mf = engine.get_mf_details(fund_name)
    
    if etf:
        return f"ETF Details: {json.dumps(etf, indent=2)}"
    elif mf:
        return f"Mutual Fund Details: {json.dumps(mf, indent=2)}"
    else:
        return f"Fund '{fund_name}' not found in database."

def web_search(query: str) -> str:
    """Perform a web search using DuckDuckGo, with news fallback and error handling."""
    print(f"[LOG] 🌐 Searching Web for: {query}")
    try:
        results = []
        with DDGS() as ddgs:
            # Try text search first
            try:
                responses = ddgs.text(query, max_results=5)
                for r in responses:
                    results.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})
            except DuckDuckGoSearchException as de:
                if "Ratelimit" in str(de):
                    return "Error: Search engine is temporarily rate-limited. I cannot fetch live results at this moment. Please wait a few minutes and try again."
                raise de

            # If no results or very few, try news search specifically
            if len(results) < 2:
                responses = ddgs.news(query, max_results=5)
                for r in responses:
                    results.append({"title": r.get("title"), "snippet": r.get("body"), "link": r.get("href")})

        if not results:
            return f"No results found for '{query}'. The stock might be new or unlisted, or there's no recent news."
            
        return f"Web Search Results for '{query}': {json.dumps(results, indent=2)}"
    except Exception as e:
        return f"Error performing web search: {str(e)}"

def analyze_etf_overlap(etf_symbol: str) -> str:
    try:
        if not etf_symbol:
            return "Error: No ETF symbol provided."
        result = engine.calculate_etf_overlap(etf_symbol)
        return f"ETF Overlap Analysis: {json.dumps(result, indent=2)}"
    except Exception as e:
        return f"Error analyzing ETF overlap: {str(e)}"

def count_etfs() -> str:
    try:
        pf_perf = engine.calculate_portfolio_performance()
        etfs = [h for h in pf_perf["holdings"] if h.get("is_etf")]
        
        if not etfs:
            return "You have 0 ETFs in your portfolio."
        
        etf_list = [f"{h['stock_name']} (ISIN: {h.get('isin')})" for h in etfs]
        return f"You have {len(etfs)} ETF(s) in your portfolio:\n" + "\n".join(f"- {e}" for e in etf_list)
    except Exception as e:
        return f"Error counting ETFs: {str(e)}"


# --- Dispatcher ---

def execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Execute python logic for the given tool name."""
    print(f"[LOG] 🛠️ Executing Tool: {tool_name} with args: {args}")
    
    if tool_name == "get_portfolio_summary":
        return get_portfolio_summary()
    elif tool_name == "get_holding_details":
        return get_holding_details(args.get("stock_name"))
    elif tool_name == "get_holdings_batch":
        return get_holdings_batch(args.get("stock_names"))
    elif tool_name == "compare_stocks":
        return compare_stocks(args.get("stock_parent"), args.get("stock_comparison"))
    elif tool_name == "get_benchmark_comparison":
        return get_benchmark_comparison()
    elif tool_name == "get_fund_details":
        return get_fund_details(args.get("fund_name"))
    elif tool_name == "web_search":
        return web_search(args.get("query"))
    elif tool_name == "analyze_etf_overlap":
        return analyze_etf_overlap(args.get("etf_symbol"))
    elif tool_name == "count_etfs":
        return count_etfs()
    else:
        return f"Error: Unknown tool '{tool_name}'"
