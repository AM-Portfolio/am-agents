import os
import logging
from typing import Optional, Dict, Any
from pymongo import MongoClient
from dotenv import load_dotenv

# Load env in case db.py is imported directly
load_dotenv(override=True)

logger = logging.getLogger(__name__)

class MongoDBClient:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI")
        self.db_name = os.getenv("DB_NAME", "portfolio")
        self.client = None
        self.db = None
        
        if self.uri:
            try:
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
                self.db = self.client[self.db_name]
                logger.info(f"Connected to MongoDB: {self.db_name}")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
        else:
            logger.warning("MONGODB_URI not found in environment variables.")

    def get_portfolio(self, owner_id: str = None):
        """
        Fetch portfolio for a specific owner. 
        If owner_id is None, it tries to fetch the first portfolio found.
        """
        if self.db is None:
            logger.error("Database not initialized.")
            return None

        collection = self.db["portfolios"]
        
        try:
            query = {"owner": owner_id} if owner_id else {}
            portfolio = collection.find_one(query)
            
            if portfolio:
                logger.info(f"Fetched portfolio for owner: {portfolio.get('owner')}")
            else:
                logger.warning(f"No portfolio found for query: {query}")
                
            return portfolio
            
        except Exception as e:
            logger.error(f"Error fetching portfolio: {e}")
            return None

    def get_etf_holdings(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch ETF holdings from the mutual_funds database.
        """
        if self.client is None:
            return None
        
        try:
            # Connect to sibling DB 'mutual_funds'
            mf_db = self.client["mutual_funds"]
            collection = mf_db["etf_holdings"]
            
            # Case-insensitive search on Symbol OR ISIN
            query = {
                "$or": [
                    {"symbol": {"$regex": f"^{symbol}$", "$options": "i"}},
                    {"isin": {"$regex": f"^{symbol}$", "$options": "i"}}
                ]
            }
            doc = collection.find_one(query)
            return doc
        except Exception as e:
            logger.error(f"Error fetching ETF holdings for {symbol}: {e}")
            return None

# Singleton instance
db_client = MongoDBClient()
