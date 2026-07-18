# AM Portfolio — AI Agent Task Tracker

> Last updated: 2026-02-22 03:00 IST | Status: 🔥 SYSTEM RIGID & RELIABLE - End-to-end Chat Live

## Quick Status

| Phase | Status | Description |
|---|---|---|
| H.1 | ✅ Done | UI Card Purification |
| H.2 | ✅ Done | Data Headless Migration (Dart SDK) |
| H.3 | ✅ Live | am-fin-agent FastAPI running on 8100 |
| H.4 | ✅ Live | am_app (Flutter) running on 9005 with AI Chat tab |
| H.5 | ✅ Done | REST Client layer wired to Java backend |
| H.7 | ✅ Done | Dashboard Reliability & Error Handling |
| H.8 | ✅ Done | Global 3-Retry Logic (ApiClient/AnalysisApiClient) |
| H.9 | ⬜ Planned | UI Architecture Overhaul (am_library) |
| H.10| 🚧 In Prog| Infinite Retry Investigation & Fix |

---

## Phase H.3 — AI Backend (`am-fin-agent`) ✅

- [x] `schemas/intent.py`, `context/`, `session/`
- [x] `tools/registry.py` + `portfolio_tools.py`
- [x] `tools/analysis_tools.py`
- [x] `tools/trade_tools.py`
- [x] `formatters/intent_formatter.py` + `middleware/`
- [x] `agents/finance_agent.py` (LangGraph ReAct + circuit breaker)
- [x] `api.py` (FastAPI + health + SSE)
- [x] 🛑 VERIFY: Server is live and processing real user data.

## Phase H.4 — Flutter AI Chat UI ✅

- [x] `am_ai_ui` module integrated into `am_app`.
- [x] `AiWidgetFactory` rendering dynamic financial widgets.
- [x] SSE listener for real-time AI status updates.
- [x] Premium dark theme integration.

**Phase H.9: UI Architecture Overhaul (am_library)**

- [ ] Create `am_library` module to centralize SDKs, networking, and STOMP.
- [ ] Implement `ServiceRegistry` for unified service access.
- [ ] Decouple all UI modules from direct technical dependencies.

**Phase H.10: Infinite Retry Root Cause Analysis & Fix**

- [ ] Identify source of automatic refresh loops on 500 errors.
- [ ] Ensure persistence of `AsyncError` state in Riverpod.
- [ ] Verify 3-retry limit is absolute.

**Phase H.11: UI Lab (Diagnostic Tooling)**

- [ ] Create `am_diagnostic_ui` (port 9001) for isolated SDK testing.
- [ ] Implement real-time health dashboard for all backend dependencies.

---

## Architecture Reference

| Layer | File | Port |
|---|---|---|
| Flutter UI | `am_app` | **9005** |
| AI Agent API | `am-fin-agent/api.py` | **8100** |
| Analysis Service | `am-analysis` (Java) | **8060** |
| Trade Service | `am-trade` (Java) | **8040** |
| Market Data | `am-market-data` (Java) | **8020** |
| **UI Lab** | `am_diagnostic_ui` | **9001** |

Full architecture doc: `am-fin-agent/docs/ARCHITECTURE.md`
