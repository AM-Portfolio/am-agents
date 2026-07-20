import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env vars BEFORE local imports
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path, override=True)

# Ensure the parent directory (root) is in python path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Force Portfolio Mode
os.environ["ENABLE_PORTFOLIO_ANALYSIS"] = "true"
os.environ["ENABLE_API_TESTING"] = "false"

from am_fin_portfolio_analysis.chatbot.bot import ChatAgent

async def main():
    
    # Check for API Key
    if not os.getenv("TOGETHER_API_KEY"):
        print("WARNING: TOGETHER_API_KEY not found in environment variables.")
        print("Please set it in .env file.")
        # Optional: Ask user for key input if missing
        
    agent = ChatAgent()
    
    print("\n" + "="*50)
    print("Welcome to the Financial Intelligence Assistant")
    print("You can ask about your portfolio, NIFTY 50, ETFs, etc.")
    print("Type 'exit' to quit.")
    print("="*50 + "\n")
    
    while True:
        try:
            user_input = input("You: ")
            if user_input.lower() in ["exit", "quit"]:
                break
                
            if not user_input.strip():
                continue
            
            print("Assistant: Thinking...", end="\r")
            response = await agent.process_query(user_input)
            print(f"Assistant: {response}\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    asyncio.run(main())
