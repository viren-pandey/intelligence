import asyncio
import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob
from crawlers.browser.playwright_pool import pool as browser_pool


COMPANY_CAREER_PAGES = [
    {"company": "Razorpay", "url": "https://razorpay.com/jobs/", "js": False},
    {"company": "CRED", "url": "https://careers.cred.club/", "js": True},
    {"company": "Zerodha", "url": "https://zerodha.com/careers/", "js": False},
    {"company": "Notion", "url": "https://www.notion.so/careers", "js": True},
    {"company": "Linear", "url": "https://linear.app/careers", "js": True},
    {"company": "Vercel", "url": "https://vercel.com/careers", "js": True},
    {"company": "Supabase", "url": "https://supabase.com/careers", "js": True},
    {"company": "PlanetScale", "url": "https://planetscale.com/careers", "js": True},
    {"company": "Loom", "url": "https://www.loom.com/careers", "js": True},
    {"company": "Figma", "url": "https://www.figma.com/careers/", "js": True},
    {
        "company": "Stripe",
        "url": "https://stripe.com/jobs/search?remote_locations=India",
        "js": True,
    },
    {"company": "GitHub", "url": "https://github.com/about/careers", "js": True},
    {
        "company": "Atlassian",
        "url": "https://www.atlassian.com/company/careers",
        "js": True,
    },
    {"company": "Cloudflare", "url": "https://www.cloudflare.com/careers/", "js": True},
    {"company": "Datadog", "url": "https://www.datadoghq.com/careers/", "js": True},
    {"company": "Netflix", "url": "https://jobs.netflix.com/", "js": True},
    {"company": "Spotify", "url": "https://www.spotify.com/us/jobs/", "js": True},
    {"company": "Canva", "url": "https://www.canva.com/careers/", "js": True},
    {"company": "Airbnb", "url": "https://careers.airbnb.com/", "js": True},
    {"company": "Uber", "url": "https://www.uber.com/us/en/careers/", "js": True},
    {"company": "Stripe", "url": "https://stripe.com/jobs", "js": True},
    {"company": "Coinbase", "url": "https://www.coinbase.com/careers", "js": True},
    {"company": "Plaid", "url": "https://plaid.com/careers/", "js": True},
    {"company": "Figma", "url": "https://www.figma.com/careers/", "js": True},
    {"company": "Snowflake", "url": "https://www.snowflake.com/careers/", "js": True},
]


class CareerPagesCrawler(BaseCrawler):
    source_name = "career_pages"
    requires_js = False
    rate_limit_per_second = 0.5

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        query_keywords = set()
        for q in queries:
            for word in q.lower().replace('"', "").split():
                query_keywords.add(word)

        for company_info in COMPANY_CAREER_PAGES:
            if len(jobs) >= 200:
                break

            try:
                if company_info["js"]:
                    company_jobs = await self._crawl_with_js(
                        company_info, query_keywords
                    )
                else:
                    company_jobs = await self._crawl_static(
                        company_info, query_keywords
                    )
                jobs.extend(company_jobs)
            except Exception:
                continue

        return jobs

    async def _crawl_static(self, company: dict, keywords: set) -> list[RawJob]:
        jobs = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(
                company["url"],
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            if resp.status_code != 200:
                return jobs

            soup = BeautifulSoup(resp.text, "html.parser")
            for link_el in soup.select("a[href]"):
                href = link_el.get("href", "")
                title = link_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                if "intern" not in title.lower():
                    continue
                apply_link = (
                    href
                    if href.startswith("http")
                    else f"{company['url'].rstrip('/')}/{href.lstrip('/')}"
                )

                job = RawJob(
                    title=title,
                    company=company["company"],
                    location="Unknown",
                    apply_link=apply_link,
                    source_platform="career_pages",
                    source_url=company["url"],
                    posted_date=datetime.now(timezone.utc),
                )
                jobs.append(job)

        return jobs

    async def _crawl_with_js(self, company: dict, keywords: set) -> list[RawJob]:
        jobs = []
        try:
            async with browser_pool.acquire() as page:
                await page.goto(
                    company["url"], wait_until="domcontentloaded", timeout=30000
                )
                await asyncio.sleep(3)

                links = await page.evaluate("""
                    () => {
                        return Array.from(document.querySelectorAll('a[href]'))
                            .map(a => ({href: a.href, text: a.innerText.trim()}))
                            .filter(x => x.text.length > 5);
                    }
                """)

                for link_info in links:
                    title = link_info["text"]
                    if "intern" not in title.lower():
                        continue
                    job = RawJob(
                        title=title,
                        company=company["company"],
                        location="Unknown",
                        apply_link=link_info["href"],
                        source_platform="career_pages",
                        source_url=company["url"],
                        posted_date=datetime.now(timezone.utc),
                    )
                    jobs.append(job)

        except Exception:
            pass

        return jobs
