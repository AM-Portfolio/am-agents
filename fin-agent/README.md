# AM Finance Agent (am-fin-agent)

An AI-powered financial intelligence agent with a modular plugin architecture.

## 🌟 Modular Architecture

The project is split into two independent domain modules that can be run separately or together:

### 1. Portfolio Analysis (`am_fin_portfolio_analysis`)
Focuses on personal finance, stock portfolios, ETF overlap analysis, and market insights.
- **API**: `python am_fin_portfolio_analysis/api.py` (Port 8101)
- **UI**: `streamlit run am_fin_portfolio_analysis/ui.py`
- **CLI**: `python am_fin_portfolio_analysis/main.py`

### 2. API Testing & Discovery (`am_fin_api_testing`)
Focuses on autonomous microservice discovery, OpenAPI tool generation, and automated testing.
- **API**: `python am_fin_api_testing/api.py` (Port 8102)
- **CLI**: `python am_fin_api_testing/main.py`
- **Dashboard**: Integrated into the API at `/dashboard`

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
The system is detachable via environment variables:
```env
ENABLE_PORTFOLIO_ANALYSIS=true
ENABLE_API_TESTING=true
```

### 3. Run the Monolith (Both Enabled)
```bash
python api.py
```
Port: `8100`

### 4. Run Modules Separately
You can run only what you need by using the module-specific entry points listed above.

---

## 📂 New Project Structure

- `am_fin_portfolio_analysis/`: Core logic, tools, and UI for portfolio management.
- `am_fin_api_testing/`: Meta-engine for microservice discovery and testing.
- `agents/`: Shared `FinanceAgent` that dynamically loads tools from enabled modules.
- `tools/`: Shared registry and vector indexing infrastructure.
- `core/`: Shared configuration, database, and context management.
- `mcp_server/`: Official MCP server implementation.

---

## 🤖 Guide for AI Agents/Developers

If you are a new agent or developer taking over this repository:
1.  **Discovery**: Look at `SERVICES` in `api.py` or your local `services.json`. The system bootstraps from these URLs.
2.  **Tool Flow**: The `FinanceAgent` in `agents/finance_agent.py` uses `tools/tool_index.py` to retrieve the best candidate tools before making an LLM call.
3.  **Extending**: To add a new capability, simply expose it as an OpenAPI endpoint in any of your microservices. The agent will discover it on the next restart.

---

## 🛠 Self-Verification
Run the integrated test suite to ensure everything is operational:
```bash
pytest tests/
```
