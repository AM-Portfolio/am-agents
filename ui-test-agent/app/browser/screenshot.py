import base64
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def capture_screenshot_base64(page: Page) -> str:
    png_bytes = await page.screenshot(type="png", full_page=False)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    logger.debug("Captured screenshot (%d bytes)", len(png_bytes))
    return encoded
