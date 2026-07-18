import streamlit as st
import asyncio
import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Config
st.set_page_config(page_title="Finance Intelligence", layout="wide")
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path, override=True)

# Path setup
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Force Portfolio Mode
os.environ["ENABLE_PORTFOLIO_ANALYSIS"] = "true"
os.environ["ENABLE_API_TESTING"] = "false"

from am_fin_portfolio_analysis.chatbot.bot import ChatAgent
from am_fin_portfolio_analysis.core.engine import engine
from am_fin_portfolio_analysis.core.analyzer import autonomous_analyzer
from am_fin_portfolio_analysis.core.insights import insight_generator

# Initialize Agent
if "agent" not in st.session_state:
    st.session_state.agent = ChatAgent()

# Initialize Chat History
if "messages" not in st.session_state:
    st.session_state.messages = []

# Run Autonomous Analysis (once per session)
if "autonomous_analysis" not in st.session_state:
    st.session_state.autonomous_analysis = autonomous_analyzer.analyze_portfolio()
    st.session_state.insights = insight_generator.generate_insights(st.session_state.autonomous_analysis)

# --- Sidebar: Model Selection ---
st.sidebar.title("🤖 Model Settings")

# Model Provider Selection
current_provider = os.getenv("LLM_PROVIDER", "gemini")
provider = st.sidebar.selectbox(
    "Provider",
    ["gemini", "together"],
    index=0 if current_provider == "gemini" else 1,
    key="provider_select"
)

# Model Selection based on provider
if provider == "gemini":
    model_options = [
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro"
    ]
    current_model = os.getenv("LLM_MODEL", "gemini-2.0-flash-lite")
else:  # together
    model_options = [
        "ServiceNow-AI/Apriel-1.6-15b-Thinker",
        "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "Qwen/Qwen2.5-72B-Instruct-Turbo"
    ]
    current_model = os.getenv("LLM_MODEL", "ServiceNow-AI/Apriel-1.6-15b-Thinker")

model = st.sidebar.selectbox(
    "Model",
    model_options,
    index=model_options.index(current_model) if current_model in model_options else 0,
    key="model_select"
)

# Apply button
if st.sidebar.button("🔄 Apply Model Change", type="primary"):
    # Update environment variables
    os.environ["LLM_PROVIDER"] = provider
    os.environ["LLM_MODEL"] = model
    
    # Clear agent to force reinitialization
    if "agent" in st.session_state:
        del st.session_state.agent
    
    st.sidebar.success(f"Switched to {model}")
    st.rerun()

# Display current model (runtime value)
runtime_provider = os.environ.get("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "gemini"))
runtime_model = os.environ.get("LLM_MODEL", os.getenv("LLM_MODEL", "N/A"))
st.sidebar.caption(f"✅ Active: {runtime_provider} / {runtime_model}")

st.sidebar.markdown("---")

# --- Sidebar: Portfolio Overview ---
st.sidebar.title("📊 Portfolio Overview")

# Refresh buttons
col1, col2 = st.sidebar.columns(2)
with col1:
    if st.button("🔄 Refresh Data"):
        st.rerun()
with col2:
    if st.button("🧹 Clear Cache"):
        from shared.core.cache import cache
        cache.clear()
        if "autonomous_analysis" in st.session_state:
            del st.session_state.autonomous_analysis
        if "insights" in st.session_state:
            del st.session_state.insights
        st.rerun()

# Fetch Core Data
try:
    pf_perf = engine.calculate_portfolio_performance()
    
    st.sidebar.metric("Total Invested", f"₹{pf_perf['total_invested']:,.2f}")
    st.sidebar.metric("Current Value", f"₹{pf_perf['total_current_value']:,.2f}")
    
    pnl_color = "normal"
    if pf_perf['total_pnl'] > 0:
        pnl_color = "off" # Streamlit metric delta check handles color
    
    st.sidebar.metric(
        "Total P&L", 
        f"₹{pf_perf['total_pnl']:,.2f}", 
        f"{pf_perf['total_pnl_pct']:.2f}%"
    )
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Holdings")
    df_holdings = pd.DataFrame(pf_perf['holdings'])
    st.sidebar.dataframe(df_holdings[["stock_name", "quantity", "current_value", "pnl_pct"]], hide_index=True)

except Exception as e:
    st.sidebar.error(f"Error loading data: {e}")

# --- AI Insights Section ---
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 AI Insights")

try:
    insights = st.session_state.get("insights", [])
    if insights:
        for insight in insights[:5]:  # Top 5 insights
            st.sidebar.info(insight)
    else:
        st.sidebar.write("No insights available")
except Exception as e:
    st.sidebar.error(f"Error loading insights: {e}")

# --- Main Chat Interface ---
st.title("💬 Financial Intelligence Assistant")
st.markdown("Ask about your portfolio, NIFTY 50, ETFs, or Mutual Funds.")

# Display Chat History
# Add proactive welcome message if this is first load
if len(st.session_state.messages) == 0:
    welcome_msg = insight_generator.generate_welcome_message(st.session_state.autonomous_analysis)
    st.session_state.messages.append({"role": "assistant", "content": welcome_msg})

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("Ask a financial question..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # Generate Response
    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        final_response_container = st.empty()
        
        # We need a small async wrapper to iterate the async generator
        async def run_chat():
            with st.status("Thinking...", expanded=True) as status:
                final_text = ""
                # Pass history (excluding current prompt which is added inside)
                history = st.session_state.messages
                async for event in st.session_state.agent.process_query(prompt, history):
                    if event["type"] == "status":
                        status.write(event["content"])
                    elif event["type"] == "response":
                        final_text = event["content"]
                        status.update(label="Complete!", state="complete", expanded=False)
                return final_text

        try:
            # Safer way to run async in Streamlit threads
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(run_chat())
            loop.close()
            
            final_response_container.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
        except Exception as e:
            st.error(f"Error: {e}")

# Debug Info (Optional)
with st.expander("Debug: Mock Data Status"):
    st.json(engine.compare_portfolio_vs_benchmark())
