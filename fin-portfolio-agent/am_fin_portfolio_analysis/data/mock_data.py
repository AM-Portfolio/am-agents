from datetime import datetime, timedelta
from typing import Dict, List, Any

# 1. Equity Portfolio (User Holdings)
EQUITY_PORTFOLIO: List[Dict[str, Any]] = [
    {
        "stock_name": "HDFC Bank",
        "quantity": 50,
        "buy_price": 1450.00,
        "buy_date": "2024-01-15"
    },
    {
        "stock_name": "Reliance Industries",
        "quantity": 20,
        "buy_price": 2300.00,
        "buy_date": "2023-11-20"
    },
    {
        "stock_name": "TCS",
        "quantity": 15,
        "buy_price": 3500.00,
        "buy_date": "2024-03-10"
    },
    {
        "stock_name": "Infosys",
        "quantity": 40,
        "buy_price": 1350.00,
        "buy_date": "2024-02-05"
    },
    {
        "stock_name": "ITC",
        "quantity": 200,
        "buy_price": 400.00,
        "buy_date": "2023-12-01"
    }
# ... existing specific stocks ...
]

# Live Price Mock Data (Simulated)
LIVE_PRICES: Dict[str, Dict[str, Any]] = {
    "HDFC Bank": {
        "current_price": 1600.00,
        "last_updated": datetime.now().isoformat()
    },
    "Reliance Industries": {
        "current_price": 2900.00,
        "last_updated": datetime.now().isoformat()
    },
    "TCS": {
        "current_price": 3900.00,
        "last_updated": datetime.now().isoformat()
    },
    "Infosys": {
        "current_price": 1500.00,
        "last_updated": datetime.now().isoformat()
    },
    "ITC": {
        "current_price": 450.00,
        "last_updated": datetime.now().isoformat()
    }
}

# --- GENERATE 500 HOLDINGS WITH REAL STOCK NAMES ---
import random

# List of 50 Real NSE Stocks (NIFTY 50 approximation)
REAL_STOCKS = [
    "Reliance Industries", "HDFC Bank", "ICICI Bank", "Infosys", "TCS", 
    "ITC", "L&T", "Axis Bank", "Kotak Mahindra Bank", "Hindustan Unilever", 
    "State Bank of India", "Bharti Airtel", "Bajaj Finance", "Asian Paints", 
    "Maruti Suzuki", "Titan Company", "Sun Pharma", "Tata Steel", "NTPC", 
    "Power Grid Corp", "Mahindra & Mahindra", "UltraTech Cement", "Nestle India", 
    "Adani Enterprises", "JSW Steel", "Grasim Industries", "HCL Technologies", 
    "Coal India", "Tata Motors", "ONGC", "HDFC Life", "Dr Reddys Labs", 
    "Bajaj Finserv", "Wipro", "SBI Life Insurance", "BPCL", "Cipla", 
    "Adani Ports", "Hero MotoCorp", "Eicher Motors", "Tech Mahindra", 
    "Hindalco Industries", "Britannia Industries", "Tata Consumer", "Divis Labs", 
    "Apollo Hospitals", "Bajaj Auto", "LTIMindtree", "IndusInd Bank", "UPL"
]

# 1. Initialize Live Prices for all Real Stocks
for stock in REAL_STOCKS:
    base_price = random.uniform(500, 5000)
    LIVE_PRICES[stock] = {
        "current_price": round(base_price, 2),
        "last_updated": datetime.now().isoformat()
    }

# 2. Generate 500 Random Holdings using these Real Stocks
#    (Simulating multiple buy lots for the same stocks)
for i in range(500):
    stock_sym = random.choice(REAL_STOCKS)
    current_market_price = LIVE_PRICES[stock_sym]["current_price"]
    
    # Randomize buy price relative to current price (Profit or Loss scenario)
    buy_px = current_market_price * random.uniform(0.7, 1.3) 
    qty = random.randint(1, 100)
    
    EQUITY_PORTFOLIO.append({
        "stock_name": stock_sym,
        "quantity": qty,
        "buy_price": round(buy_px, 2),
        "buy_date": f"2023-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
    })
# -----------------------------------------------------

# 2. Benchmark Index - NIFTY 50
BENCHMARK_INDEX: Dict[str, Any] = {
    "index_name": "NIFTY 50",
    "returns": {
        "1w": 1.2,
        "1m": 3.5,
        "1y": 12.8
    },
    "constituents": [
        {"stock_name": "HDFC Bank", "weightage": 13.5},
        {"stock_name": "Reliance Industries", "weightage": 10.2},
        {"stock_name": "ICICI Bank", "weightage": 7.8},
        {"stock_name": "Infosys", "weightage": 6.5},
        {"stock_name": "ITC", "weightage": 4.2},
        {"stock_name": "TCS", "weightage": 4.1},
        {"stock_name": "L&T", "weightage": 3.8},
        {"stock_name": "Axis Bank", "weightage": 3.2},
        {"stock_name": "Kotak Mahindra Bank", "weightage": 2.9},
        {"stock_name": "Bharti Airtel", "weightage": 2.7}
        # ... others implied
    ]
}

# 3. ETFs (3)
ETFS: List[Dict[str, Any]] = [
    {
        "name": "Nifty Bees",
        "category": "Index ETF",
        "returns": {
            "1w": 1.1,
            "1m": 3.4,
            "1y": 12.5
        },
        "holdings": [
             {"stock_name": "HDFC Bank", "weightage": 13.5},
             {"stock_name": "Reliance Industries", "weightage": 10.2},
             # Simplification: Tracking NIFTY 50 perfectly
             {"stock_name": "Others", "weightage": 76.3} 
        ],
        "expense_ratio": 0.05,
        "benchmark": "NIFTY 50"
    },
    {
        "name": "Bank Bees",
        "category": "Sector ETF",
        "returns": {
            "1w": 2.5,
            "1m": 5.0,
            "1y": 15.0
        },
        "holdings": [
            {"stock_name": "HDFC Bank", "weightage": 28.0},
            {"stock_name": "ICICI Bank", "weightage": 24.0},
            {"stock_name": "Axis Bank", "weightage": 12.0},
             {"stock_name": "Others", "weightage": 36.0}
        ],
        "expense_ratio": 0.08,
        "benchmark": "NIFTY Bank"
    },
    {
        "name": "IT Bees",
        "category": "Sector ETF",
        "returns": {
            "1w": 0.5,
            "1m": -1.2,
            "1y": 8.0
        },
        "holdings": [
             {"stock_name": "TCS", "weightage": 25.0},
             {"stock_name": "Infosys", "weightage": 25.0},
             {"stock_name": "Tech Mahindra", "weightage": 10.0},
             {"stock_name": "Others", "weightage": 40.0}
        ],
        "expense_ratio": 0.08,
        "benchmark": "NIFTY IT"
    }
]

# 4. Mutual Funds (3)
MUTUAL_FUNDS: List[Dict[str, Any]] = [
    {
        "fund_name": "HDFC Top 100 Fund",
        "fund_type": "Large Cap",
        "returns": {
            "1w": 1.5,
            "1m": 4.0,
            "1y": 18.0
        },
        "portfolio_holdings": [
            {"stock_name": "HDFC Bank", "weightage": 9.5},
            {"stock_name": "Reliance Industries", "weightage": 8.5},
            {"stock_name": "ICICI Bank", "weightage": 7.0},
            {"stock_name": "Infosys", "weightage": 5.5},
            {"stock_name": "L&T", "weightage": 4.5}
        ],
        "expense_ratio": 1.10,
        "benchmark": "NIFTY 100",
        "fund_manager": "Rahul Baijal"
    },
    {
        "fund_name": "Parag Parikh Flexi Cap Fund",
        "fund_type": "Flexi Cap",
        "returns": {
            "1w": 0.8,
            "1m": 2.5,
            "1y": 22.0
        },
        "portfolio_holdings": [
            {"stock_name": "HDFC Bank", "weightage": 8.0},
            {"stock_name": "ITC", "weightage": 7.5},
            {"stock_name": "Bajaj Holdings", "weightage": 6.0},
            {"stock_name": "Power Grid", "weightage": 5.0}
        ],
        "expense_ratio": 0.75,
        "benchmark": "NIFTY 500",
        "fund_manager": "Rajeev Thakkar"
    },
    {
        "fund_name": "Quant Small Cap Fund",
        "fund_type": "Small Cap",
        "returns": {
            "1w": 3.0,
            "1m": 8.0,
            "1y": 45.0
        },
        "portfolio_holdings": [
            {"stock_name": "Reliance Industries", "weightage": 5.0}, # Keep some common ones for overlap check
            {"stock_name": "Jio Financial", "weightage": 4.5},
            {"stock_name": "IRB Infra", "weightage": 4.0}
        ],
        "expense_ratio": 0.85,
        "benchmark": "NIFTY Smallcap 250",
        "fund_manager": "Ankit Pande"
    }
]

def get_live_price(stock_name: str) -> float:
    """Simulate fetching live price."""
    return LIVE_PRICES.get(stock_name, {}).get("current_price", 0.0)

def get_last_updated(stock_name: str) -> str:
    """Get last updated timestamp."""
    return LIVE_PRICES.get(stock_name, {}).get("last_updated", "")
