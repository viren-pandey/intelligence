import asyncio
import httpx
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob
from crawlers.browser.playwright_pool import pool as browser_pool


PUBLIC_DISCORD_SOURCES = [
    {"name": "reactiflux", "url": "https://www.reactiflux.com/", "type": "landing"},
    {"name": "devchat", "url": "https://devchat.com/community/", "type": "landing"},
]


class DiscordJobsCrawler(BaseCrawler):
    source_name = "discord_jobs"
    requires_js = True
    rate_limit_per_second = 0.3

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []

        for source in PUBLIC_DISCORD_SOURCES:
            try:
                async with browser_pool.acquire() as page:
                    await page.goto(
                        source["url"], wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(3)

                    text = await page.evaluate("document.body.innerText")
                    lines = text.split("\n")

                    for line in lines:
                        line = line.strip()
                        if not line or len(line) < 15:
                            continue
                        line_lower = line.lower()
                        if not any(
                            kw in line_lower
                            for kw in [
                                "job",
                                "hiring",
                                "intern",
                                "position",
                                "opening",
                                "career",
                            ]
                        ):
                            continue
                        if len(line) > 300:
                            line = line[:300]

                        urls = re.findall(r"https?://[^\s]+", line)
                        apply_link = urls[0] if urls else source["url"]

                        company_match = re.search(
                            r"(?:at|@|for)\s+([A-Z][a-zA-Z0-9\s&]+?)(?:\s+(?:is|are|has|we|and|\.|!|\?))",
                            line,
                        )
                        company = (
                            company_match.group(1).strip()
                            if company_match
                            else source["name"]
                        )

                        job = RawJob(
                            title=line[:200],
                            company=company[:100],
                            location="Remote",
                            remote_status="remote",
                            job_type="internship"
                            if "intern" in line_lower
                            else "fulltime",
                            description=line,
                            apply_link=apply_link,
                            source_platform="discord_jobs",
                            source_url=source["url"],
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

            except Exception:
                continue

        return jobs
