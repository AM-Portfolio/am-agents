# AM UI Test Agent

Autonomous UI regression testing agent built using **Playwright** and **LangGraph**. This agent runs automated end-to-end interface walks, registers baseline snapshots, and compares runtime UI rendering against preprod baselines.

---

## 1. Quick Start

### Prerequisites
*   Python 3.10+
*   Node.js (for NPM workspace integration)
*   Playwright browser binaries

### Local Setup
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install
   ```
2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```

---

## 2. Workspace Integration & Commands

This agent is registered as the `@am/ui-test-agent` NPM workspace. You can trigger commands either locally or from the monorepo root:

| Command | Action |
|---------|--------|
| `npm run dev` | Start local UI-test FastAPI server |
| `npm run test` | Run pytest unit tests |
| `npm run test:auth:preprod` | Run Playwright authentication flow test against preprod |
| `npm run test:e2e:preprod` | Run integrated e2e walks and register a new baseline |
| `npm run test:e2e:preprod:compare` | Run e2e walks and compare UI rendering to preprod baseline |

---

## 3. Configuration Properties

The following properties are configured via `.env` (or Kubernetes secrets):

*   `APP_PORT` — The port the test runner API binds to (default: `8130`).
*   `KEYCLOAK_TOKEN_URL` — Keycloak endpoint used to authenticate UI flows.
*   `QDRANT_HOST` / `QDRANT_PORT` — Vector store connection to match visual elements.
*   `LANGFUSE_ENABLED` — Enables tracing of LangGraph navigation decisions.
