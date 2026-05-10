import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class WeWorkRemotelyCrawler(BaseCrawler):
    source_name = "weworkremotely"
    requires_js = False
    rate_limit_per_second = 1.0

    CATEGORY_URLS = [
        "https://weworkremotely.com/categories/remote-programming-jobs",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs",
        "https://weworkremotely.com/categories/remote-data-jobs",
    ]

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for cat_url in self.CATEGORY_URLS:
                try:
                    resp = await client.get(
                        cat_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")

                    for li in (
                        soup.select("li.job")
                        or soup.select("li")
                        or soup.select("article")
                    ):
                        link_el = li.select_one("a[href]") if li.name == "li" else li
                        if not link_el:
                            continue

                        title_el = (
                            li.select_one(".title")
                            or li.select_one("h2")
                            or li.select_one("span")
                        )
                        company_el = li.select_one(".company") or li.select_one(
                            ".employer"
                        )

                        title = title_el.get_text(strip=True) if title_el else ""
                        company = (
                            company_el.get_text(strip=True) if company_el else "Unknown"
                        )
                        href = (
                            link_el.get("href", "") if hasattr(link_el, "get") else ""
                        )
                        apply_link = (
                            f"https://weworkremotely.com{href}"
                            if href.startswith("/")
                            else href
                        )

                        if not title:
                            continue

                        job = RawJob(
                            title=title,
                            company=company,
                            location="Remote",
                            remote_status="remote",
                            job_type="internship"
                            if "intern" in title.lower()
                            else "fulltime",
                            paid=True,
                            apply_link=apply_link,
                            source_platform="weworkremotely",
                            source_url=cat_url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs
