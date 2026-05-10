import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from crawlers.base import BaseCrawler, RawJob
from crawlers.browser.playwright_pool import pool as browser_pool


class GoogleSERPCrawler(BaseCrawler):
    source_name = "google_serp"
    requires_js = True
    rate_limit_per_second = 0.3

    JOB_URL_PATTERNS = [
        r"/jobs/",
        r"/careers/",
        r"/internship",
        r"/apply",
        r"/opportunity",
        r"/position",
        r"/opening",
    ]

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        seen_urls = set()

        for query in queries[:8]:
            if len(jobs) >= 200:
                break

            search_url = (
                f"https://www.google.com/search?q={quote_plus(query)}&hl=en&num=10"
            )

            try:
                async with browser_pool.acquire() as page:
                    await page.goto(
                        search_url, wait_until="domcontentloaded", timeout=30000
                    )
                    await asyncio.sleep(2)

                    try:
                        await page.wait_for_selector("div#search", timeout=10000)
                    except Exception:
                        continue

                    result_links = await page.evaluate("""
                        () => {
                            const links = document.querySelectorAll('a[href]');
                            return Array.from(links).map(a => ({
                                href: a.href,
                                text: a.innerText.trim()
                            }));
                        }
                    """)

                    for link_info in result_links:
                        href = link_info.get("href", "")
                        text = link_info.get("text", "")

                        if not href or not text:
                            continue
                        if href in seen_urls:
                            continue
                        if not any(
                            re.search(p, href.lower()) for p in self.JOB_URL_PATTERNS
                        ):
                            continue

                        seen_urls.add(href)

                        job = RawJob(
                            title=text[:150],
                            company="Unknown",
                            location="Unknown",
                            apply_link=href,
                            source_platform="google_serp",
                            source_url=search_url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

            except Exception:
                continue

        return jobs
