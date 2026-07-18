#!/usr/bin/env python3
"""
Quick diagnostic script — run this first to check what's configured.
python check_setup.py
"""
import os, sys
from dotenv import load_dotenv
load_dotenv(override=True)

print("\n=== am-fin-agent Setup Check ===\n")

ok = True

# 1. LLM Key
google_key = os.getenv("GOOGLE_API_KEY")
together_key = os.getenv("TOGETHER_API_KEY")
if google_key:
    print(f"✅ GOOGLE_API_KEY     : set ({google_key[:6]}...)")
elif together_key:
    print(f"✅ TOGETHER_API_KEY   : set ({together_key[:6]}...)")
else:
    print("❌ LLM API KEY        : MISSING — set GOOGLE_API_KEY or TOGETHER_API_KEY in .env")
    ok = False

# 2. MongoDB
mongo_uri = os.getenv("MONGODB_URI")
if mongo_uri:
    print(f"✅ MONGODB_URI        : set ({mongo_uri[:30]}...)")
else:
    print("⚠️  MONGODB_URI        : not set — agent will use mock data")

# 3. Import check
print("\n--- Import Check ---")
try:
    from fastapi import FastAPI
    print("✅ fastapi            : ok")
except ImportError as e:
    print(f"❌ fastapi            : {e}")
    ok = False

try:
    from langchain_core.messages import HumanMessage
    print("✅ langchain_core     : ok")
except ImportError as e:
    print(f"❌ langchain_core     : {e}")
    ok = False

try:
    from langgraph.graph import StateGraph
    print("✅ langgraph          : ok")
except ImportError as e:
    print(f"❌ langgraph          : {e}")
    ok = False

try:
    import duckduckgo_search
    print("✅ duckduckgo_search  : ok")
except ImportError as e:
    print(f"❌ duckduckgo_search  : {e}")
    ok = False

try:
    from google import genai
    print("✅ google-genai       : ok")
except Exception as e:
    print(f"⚠️  google-genai       : {e}")

# 4. Summary
print()
if ok:
    print("✅ All clear! Run:  python api.py")
else:
    print("❌ Fix the above issues, then run:  python api.py")
    print("\nQuick fix:")
    print("  Create a .env file with:")
    print("    GOOGLE_API_KEY=your_key_here")
    print("    MONGODB_URI=mongodb://localhost:27017    (or your connection string)")
