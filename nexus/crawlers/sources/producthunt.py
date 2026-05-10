import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class ProductHuntCrawler(BaseCrawler):
    source_name = "producthunt"
    requires_js = False
    rate_limit_per_second = 1.0

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        url = "https://www.producthunt.com/jobs"

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/html",
                    },
                )
                if resp.status_code != 200:
                    return jobs

                soup = BeautifulSoup(resp.text, "html.parser")

                for card in (
                    soup.select("a[href*='/jobs/']")
                    or soup.select("div[class*='job']")
                    or soup.select("article")
                ):
                    title_el = (
                        card.select_one("h2")
                        or card.select_one("h3")
                        or card.select_one("span[class*='title']")
                    )
                    company_el = card.select_one(
                        "span[class*='company']"
                    ) or card.select_one("span[class*='org']")
                    link_el = card if card.name == "a" else card.select_one("a[href]")

                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue

                    company = (
                        company_el.get_text(strip=True)
                        if company_el
                        else "Product Hunt Startup"
                    )
                    href = ""
                    if link_el:
                        href = link_el.get("href", "")
                        if href and not href.startswith("http"):
                            href = f"https://www.producthunt.com{href}"

                    job = RawJob(
                        title=title,
                        company=company,
                        location="Remote",
                        remote_status="remote",
                        job_type="internship"
                        if "intern" in title.lower()
                        else "fulltime",
                        paid=True,
                        apply_link=href or url,
                        source_platform="producthunt",
                        source_url=url,
                        posted_date=datetime.now(timezone.utc),
                    )
                    jobs.append(job)

            except Exception:
                pass

        return jobs
