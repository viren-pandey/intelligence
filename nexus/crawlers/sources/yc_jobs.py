import httpx
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class YCJobsCrawler(BaseCrawler):
    source_name = "yc_jobs"
    requires_js = False
    rate_limit_per_second = 1.0

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        urls = [
            "https://www.ycombinator.com/jobs?regions=Remote",
            "https://www.ycombinator.com/jobs?regions=India",
        ]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for url in urls:
                try:
                    resp = await client.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Accept": "text/html",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")

                    for card in (
                        soup.select("[class*='job']")
                        or soup.select("article")
                        or soup.select("tr")
                    ):
                        title_el = (
                            card.select_one("[class*='title']")
                            or card.select_one("h3")
                            or card.select_one("h2")
                        )
                        company_el = card.select_one(
                            "[class*='company']"
                        ) or card.select_one("[class*='org']")
                        location_el = card.select_one(
                            "[class*='location']"
                        ) or card.select_one("[class*='loc']")
                        link_el = card.select_one("a[href]")

                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        if not title or "intern" not in title.lower():
                            continue

                        company = (
                            company_el.get_text(strip=True)
                            if company_el
                            else "YC Startup"
                        )
                        location = (
                            location_el.get_text(strip=True)
                            if location_el
                            else "Remote"
                        )
                        href = link_el.get("href", "") if link_el else ""
                        apply_link = (
                            f"https://www.ycombinator.com{href}"
                            if href.startswith("/")
                            else href
                        )

                        job = RawJob(
                            title=title,
                            company=company,
                            location=location,
                            remote_status="remote"
                            if "remote" in location.lower()
                            else "unknown",
                            job_type="internship",
                            paid=True,
                            apply_link=apply_link or url,
                            source_platform="yc_jobs",
                            source_url=url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs
