import logging
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

class BrowserController:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None

    async def start(self, headless: bool = True) -> Browser:
        logger.info(f"Launching Playwright Browser (headless={headless})...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        return self.browser

    async def stop(self):
        if self.browser:
            logger.info("Stopping Playwright Browser...")
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Playwright Browser stopped.")

    @asynccontextmanager
    async def get_page(self, viewport_width: int = 1280, viewport_height: int = 800):
        """Context manager to obtain a new page with a configured viewport."""
        context = await self.browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height}
        )
        page = await context.new_page()
        try:
            yield page
        finally:
            await page.close()
            await context.close()

browser_controller = BrowserController()
