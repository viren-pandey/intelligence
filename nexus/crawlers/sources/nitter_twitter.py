import httpx
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class NitterTwitterCrawler(BaseCrawler):
    source_name = "nitter_twitter"
    requires_js = False
    rate_limit_per_second = 0.5

    HIRING_PATTERNS = [
        r"hiring.*intern",
        r"looking for.*intern",
        r"intern.*open",
        r"we.*hire.*intern",
        r"join.*our team.*intern",
        r"internship.*open",
        r"apply.*intern",
        r"we.*(want|need).*intern",
    ]

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        search_terms = [
            '"we are hiring" "intern"',
            '"hiring" "intern" "apply"',
            '"looking for" "intern"',
            '"internship" "open"',
        ]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for term in search_terms:
                try:
                    encoded = term.replace(" ", "%20").replace('"', "%22")
                    url = f"https://nitter.net/search?q={encoded}&f=tweets"

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

                    for tweet in (
                        soup.select(".tweet-content")
                        or soup.select("div[class*='content']")
                        or soup.select("p")
                    ):
                        text = tweet.get_text(strip=True)
                        if not text or len(text) < 20:
                            continue
                        text_lower = text.lower()

                        if not any(
                            re.search(p, text_lower) for p in self.HIRING_PATTERNS
                        ):
                            continue

                        tweet_link = tweet.find_previous("a", href=True)
                        tweet_url = ""
                        handle = "Unknown"
                        if tweet_link:
                            href = tweet_link.get("href", "")
                            if "/" in href and len(href.split("/")) > 1:
                                handle = href.split("/")[1]
                            tweet_url = (
                                f"https://nitter.net{href}"
                                if href.startswith("/")
                                else href
                            )

                        urls_in_tweet = re.findall(r"https?://[^\s]+", text)
                        apply_link = urls_in_tweet[0] if urls_in_tweet else tweet_url

                        title = text[:150]

                        job = RawJob(
                            title=title,
                            company=f"@{handle}",
                            location="Remote",
                            remote_status="remote",
                            job_type="internship"
                            if "intern" in text_lower
                            else "fulltime",
                            paid=True,
                            description=text,
                            apply_link=apply_link,
                            source_platform="nitter_twitter",
                            source_url=tweet_url or url,
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs
