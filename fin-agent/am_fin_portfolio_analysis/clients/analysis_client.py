"""
Analysis REST Client (Phase H.5)
Calls am-analysis Spring Boot service (port 8060).

Key facts from AnalysisController.java:
  - Dashboard endpoints: @RequestParam String userId  ← sent automatically from ContextVar
  - Entity endpoints: @RequestHeader "Authorization"  ← JWT token needed (future auth integration)
  - portfolioId is OPTIONAL for /dashboard/portfolio-overviews (filters to one portfolio)
"""
import logging
import os
import httpx
from shared.context.request_context import user_id_var

logger = logging.getLogger(__name__)

ANALYSIS_BASE_URL = os.getenv("ANALYSIS_BASE_URL", "http://localhost:8060")
TIMEOUT = httpx.Timeout(10.0, read=20.0)


class AnalysisClient:
    """
    Thin httpx wrapper for am-analysis REST API.
    userId is injected automatically from request ContextVar.
    """

    def _get(self, path: str, params: dict = None, headers: dict = None) -> dict:
        """Make a GET request.  userId always appended from ContextVar."""
        user_id = user_id_var.get()
        if not user_id or user_id == "anonymous":
            logger.warning("userId is 'anonymous' — query will likely return empty data")

        all_params = {"userId": user_id, **(params or {})}
        try:
            with httpx.Client(base_url=ANALYSIS_BASE_URL, timeout=TIMEOUT) as client:
                resp = client.get(path, params=all_params, headers=headers or {})
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "API error [%s %s]: %s %s", "GET", path,
                e.response.status_code, e.response.text
            )
            return {"error": f"API {e.response.status_code}", "detail": e.response.text[:200]}
        except httpx.RequestError as e:
            logger.error("Connection error [%s]: %s", path, e)
            return {"error": f"am-analysis unreachable at {ANALYSIS_BASE_URL}. Is the service running on port 8060?"}

    # ─── Dashboard Endpoints (userId as @RequestParam) ────────────────────────

    def get_dashboard_summary(self) -> dict:
        """GET /api/v1/analysis/dashboard/summary?userId="""
        return self._get("/api/v1/analysis/dashboard/summary")

    def get_portfolio_overviews(self, portfolio_id: str = None) -> dict:
        """GET /api/v1/analysis/dashboard/portfolio-overviews?userId=[&portfolioId=]"""
        params = {}
        if portfolio_id:
            params["portfolioId"] = portfolio_id
        return self._get("/api/v1/analysis/dashboard/portfolio-overviews", params)

    def get_top_movers(self, time_frame: str = "1D") -> dict:
        """GET /api/v1/analysis/dashboard/top-movers?userId=&timeFrame="""
        return self._get("/api/v1/analysis/dashboard/top-movers",
                         params={"timeFrame": time_frame})

    def get_performance(self, time_frame: str = "1M") -> dict:
        """GET /api/v1/analysis/dashboard/performance?userId=&timeFrame="""
        return self._get("/api/v1/analysis/dashboard/performance",
                         params={"timeFrame": time_frame})

    def get_recent_activity(self, limit: int = 20, status: str = None,
                            sector: str = None, sort_by: str = "TIMESTAMP") -> dict:
        """GET /api/v1/analysis/dashboard/recent-activity?userId=[&status=][&sector=]"""
        params = {"size": limit, "sortBy": sort_by}
        if status:
            params["status"] = status
        if sector:
            params["sector"] = sector
        return self._get("/api/v1/analysis/dashboard/recent-activity", params)

    def get_allocation(self, entity_type: str = "PORTFOLIO",
                       entity_id: str = None, token: str = None) -> dict:
        """GET /api/v1/analysis/{type}/{id}/allocation  — requires Authorization header."""
        user_id = user_id_var.get()
        _id = entity_id or user_id  # fallback to userId as entity id
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self._get(f"/api/v1/analysis/{entity_type.lower()}/{_id}/allocation",
                         headers=headers)

    # ─── Health ───────────────────────────────────────────────────────────────

    def health(self) -> bool:
        try:
            with httpx.Client(base_url=ANALYSIS_BASE_URL,
                              timeout=httpx.Timeout(3.0)) as c:
                return c.get("/actuator/health").status_code == 200
        except Exception:
            return False


# Singleton — tools import this directly
analysis_client = AnalysisClient()
