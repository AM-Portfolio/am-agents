"""
Analysis REST Client (Phase H.5)
Calls the am-analysis Spring Boot service.

Key facts from AnalysisController.java:
  - Dashboard endpoints: @RequestParam String userId  ← sent automatically from ContextVar
  - All requests forward the current user's Bearer token
  - portfolioId is OPTIONAL for /dashboard/portfolio-overviews (filters to one portfolio)
"""
import logging
import os
import httpx
from shared.context.request_context import auth_token_var, user_id_var

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
        auth_token = auth_token_var.get()
        if not auth_token:
            logger.warning("Analysis request blocked because no Bearer token is available")
            return {
                "error": "AUTH_REQUIRED",
                "detail": "A Bearer access token is required to query portfolio analysis.",
            }

        if not user_id or user_id == "anonymous":
            logger.warning("userId is 'anonymous' — query will likely return empty data")

        all_params = {"userId": user_id, **(params or {})}
        all_headers = {**(headers or {}), "Authorization": f"Bearer {auth_token}"}
        try:
            with httpx.Client(base_url=ANALYSIS_BASE_URL, timeout=TIMEOUT) as client:
                resp = client.get(path, params=all_params, headers=all_headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "API error [%s %s]: %s %s", "GET", path,
                e.response.status_code, e.response.text
            )
            if e.response.status_code == 401:
                return {
                    "error": "AUTH_REQUIRED",
                    "detail": "am-analysis rejected the Bearer access token.",
                }
            return {"error": f"API {e.response.status_code}", "detail": e.response.text[:200]}
        except httpx.RequestError as e:
            logger.error("Connection error [%s]: %s", path, e)
            return {
                "error": "ANALYSIS_UNAVAILABLE",
                "detail": f"am-analysis is unreachable at {ANALYSIS_BASE_URL}.",
            }

    # ─── Dashboard Endpoints (userId as @RequestParam) ────────────────────────

    def get_dashboard_summary(self) -> dict:
        """GET /v1/analysis/dashboard/summary?userId="""
        return self._get("/v1/analysis/dashboard/summary")

    def get_portfolio_overviews(self, portfolio_id: str = None) -> dict:
        """GET /v1/analysis/dashboard/portfolio-overviews?userId=[&portfolioId=]"""
        params = {}
        if portfolio_id:
            params["portfolioId"] = portfolio_id
        return self._get("/v1/analysis/dashboard/portfolio-overviews", params)

    def get_top_movers(self, time_frame: str = "1D") -> dict:
        """GET /v1/analysis/dashboard/top-movers?userId=&timeFrame="""
        return self._get("/v1/analysis/dashboard/top-movers",
                         params={"timeFrame": time_frame})

    def get_performance(self, time_frame: str = "1M") -> dict:
        """GET /v1/analysis/dashboard/performance?userId=&timeFrame="""
        return self._get("/v1/analysis/dashboard/performance",
                         params={"timeFrame": time_frame})

    def get_recent_activity(self, limit: int = 20, status: str = None,
                            sector: str = None, sort_by: str = "TIMESTAMP") -> dict:
        """GET /v1/analysis/dashboard/recent-activity?userId=[&status=][&sector=]"""
        params = {"size": limit, "sortBy": sort_by}
        if status:
            params["status"] = status
        if sector:
            params["sector"] = sector
        return self._get("/v1/analysis/dashboard/recent-activity", params)

    def get_allocation(self, entity_type: str = "PORTFOLIO",
                       entity_id: str = None, token: str = None) -> dict:
        """GET /v1/analysis/{type}/{id}/allocation."""
        user_id = user_id_var.get()
        _id = entity_id or user_id  # fallback to userId as entity id
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self._get(f"/v1/analysis/{entity_type.lower()}/{_id}/allocation",
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
