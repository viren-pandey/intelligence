import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from crawlers.browser.fingerprint import get_random_context_options, apply_stealth


class PlaywrightPool:
    def __init__(self, max_contexts: int = 10):
        self.max_contexts = max_contexts
        self._semaphore = asyncio.Semaphore(max_contexts)
        self._playwright = None
        self._browser: Optional[Browser] = None

    async def start(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

    async def stop(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @asynccontextmanager
    async def acquire(self):
        await self._semaphore.acquire()
        context = None
        try:
            opts = get_random_context_options()
            context = await self._browser.new_context(
                user_agent=opts["user_agent"],
                viewport=opts["viewport"],
                locale=opts["locale"],
                timezone_id=opts["timezone_id"],
                ignore_https_errors=True,
            )
            page = await context.new_page()
            await apply_stealth(page)
            yield page
        finally:
            if context:
                await context.close()
            self._semaphore.release()

    @property
    def available(self) -> int:
        return (
            self.max_contexts - self._semaphore._value
            if hasattr(self._semaphore, "_value")
            else self.max_contexts
        )


pool = PlaywrightPool()
