import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class InternshalaPublicCrawler(BaseCrawler):
    source_name = "internshala_public"
    requires_js = False
    rate_limit_per_second = 0.3

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        search_queries = [
            "python internship",
            "web development internship",
            "machine learning internship",
            "data science internship",
            "software development internship",
        ]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for search in search_queries:
                try:
                    url = f"https://internshala.com/internships/{search.replace(' ', '%20')}-internship/"
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
                        soup.select(".internship_meta")
                        or soup.select(".individual_internship")
                        or soup.select("div[class*='internship']")
                    ):
                        title_el = (
                            card.select_one(".heading_4_5")
                            or card.select_one(".profile")
                            or card.select_one("h3")
                        )
                        company_el = (
                            card.select_one(".company_name")
                            or card.select_one(".company")
                            or card.select_one(".link_display_like_text")
                        )
                        location_el = (
                            card.select_one(".location")
                            or card.select_one(".row-1")
                            or card.select_one(".locations")
                        )
                        stipend_el = (
                            card.select_one(".stipend")
                            or card.select_one(".salary")
                            or card.select_one("span[class*='stipend']")
                        )
                        link_el = card.select_one("a[href]")

                        if not title_el:
                            continue

                        title = title_el.get_text(strip=True)
                        company = (
                            company_el.get_text(strip=True) if company_el else "Unknown"
                        )
                        location = (
                            location_el.get_text(strip=True) if location_el else "India"
                        )
                        stipend_text = (
                            stipend_el.get_text(strip=True) if stipend_el else ""
                        )

                        stipend_inr = None
                        if stipend_text:
                            try:
                                nums = [
                                    int(s)
                                    for s in stipend_text.replace(",", "").split()
                                    if s.isdigit()
                                ]
                                if nums:
                                    stipend_inr = nums[0]
                            except (ValueError, IndexError):
                                pass

                        href = ""
                        if link_el:
                            href = link_el.get("href", "")
                            if href and not href.startswith("http"):
                                href = f"https://internshala.com{href}"

                        job = RawJob(
                            title=title,
                            company=company,
                            location=location,
                            remote_status="onsite",
                            job_type="internship",
                            paid=stipend_inr is not None,
                            stipend_inr=stipend_inr,
                            apply_link=href or url,
                            source_platform="internshala_public",
                            source_url=url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs
