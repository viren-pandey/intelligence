import httpx
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class FounderPostsCrawler(BaseCrawler):
    source_name = "founder_posts"
    requires_js = False
    rate_limit_per_second = 1.0

    HIRING_PATTERNS = [
        r"hiring.*intern",
        r"looking for.*intern",
        r"intern.*position",
        r"intern.*open",
        r"we.*hire.*intern",
        r"join.*(our team|us).*intern",
    ]

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            search_terms = [
                "hiring intern",
                "internship",
                "looking for intern",
                "we are hiring intern",
            ]
            for term in search_terms:
                try:
                    encoded = term.replace(" ", "+")
                    url = f"https://www.google.com/search?q=site:twitter.com+OR+site:x.com+%22{encoded}%22&hl=en&num=20"
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
                    for result in soup.select("div.g") or soup.select(
                        "div[class*='result']"
                    ):
                        link_el = result.select_one("a[href]")
                        snippet_el = (
                            result.select_one(".VwiC3b")
                            or result.select_one(".st")
                            or result.select_one("span")
                        )
                        title_el = result.select_one("h3")

                        if not link_el:
                            continue

                        href = link_el.get("href", "")
                        if "twitter.com" not in href and "x.com" not in href:
                            continue

                        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                        title = title_el.get_text(strip=True) if title_el else ""

                        post_text = title + " " + snippet
                        if not any(
                            re.search(p, post_text.lower())
                            for p in self.HIRING_PATTERNS
                        ):
                            continue

                        company_match = re.search(r"@(\w+)", snippet) or re.search(
                            r"@(\w+)", title
                        )
                        company = (
                            f"@{company_match.group(1)}" if company_match else "Founder"
                        )

                        job = RawJob(
                            title=title[:200] if title else "Intern Position",
                            company=company,
                            location="Remote",
                            remote_status="remote",
                            job_type="internship",
                            paid=True,
                            apply_link=href,
                            source_platform="founder_posts",
                            source_url=url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs
