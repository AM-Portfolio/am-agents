import os
from dotenv import load_dotenv

# Load .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

class Config:
    ENABLE_PORTFOLIO_ANALYSIS = os.getenv("ENABLE_PORTFOLIO_ANALYSIS", "true").lower() == "true"
    ENABLE_API_TESTING = os.getenv("ENABLE_API_TESTING", "true").lower() == "true"
    
    # Other configs can be moved here too
    TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
    MONGODB_URI = os.getenv("MONGODB_URI")
    DB_NAME = os.getenv("DB_NAME", "portfolio")

settings = Config()
