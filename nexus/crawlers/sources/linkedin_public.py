import asyncio
import re
from datetime import datetime, timezone

from crawlers.base import BaseCrawler, RawJob
from crawlers.browser.playwright_pool import pool as browser_pool


class LinkedInPublicCrawler(BaseCrawler):
    source_name = "linkedin_public"
    requires_js = True
    rate_limit_per_second = 0.2

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        seen_urls = set()

        for query in queries[:5]:
            if len(jobs) >= 100:
                break

            keywords = query.replace('"', "").strip()
            url = (
                f"https://www.linkedin.com/jobs/search/"
                f"?keywords={keywords}"
                f"&f_TPR=r604800"
                f"&f_E=1"
                f"&location=Worldwide"
                f"&refresh=true"
            )

            try:
                async with browser_pool.acquire() as page:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(3)

                    try:
                        await page.wait_for_selector(
                            ".jobs-search__results-list", timeout=10000
                        )
                    except Exception:
                        continue

                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    await asyncio.sleep(2)

                    cards = await page.query_selector_all(".job-card-container")
                    for card in cards:
                        try:
                            title_el = await card.query_selector(
                                ".job-card-list__title"
                            )
                            company_el = await card.query_selector(
                                ".job-card-container__company-name"
                            )
                            location_el = await card.query_selector(
                                ".job-card-container__metadata-wrapper"
                            )
                            link_el = await card.query_selector(
                                "a.job-card-list__title"
                            )

                            title = await title_el.inner_text() if title_el else ""
                            company = (
                                await company_el.inner_text() if company_el else ""
                            )
                            location = (
                                await location_el.inner_text()
                                if location_el
                                else "Unknown"
                            )
                            href = (
                                await link_el.get_attribute("href") if link_el else ""
                            )

                            if not title or not href:
                                continue

                            apply_link = (
                                href
                                if href.startswith("http")
                                else f"https://www.linkedin.com{href}"
                            )

                            if apply_link in seen_urls:
                                continue
                            seen_urls.add(apply_link)

                            job = RawJob(
                                title=title.strip(),
                                company=company.strip(),
                                location=location.strip(),
                                remote_status="remote"
                                if "remote" in location.lower()
                                else "onsite",
                                job_type="internship",
                                apply_link=apply_link,
                                source_platform="linkedin_public",
                                source_url=url,
                                posted_date=datetime.now(timezone.utc),
                            )
                            jobs.append(job)
                        except Exception:
                            continue

            except Exception:
                continue

        return jobs
