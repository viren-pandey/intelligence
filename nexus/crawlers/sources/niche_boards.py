import httpx
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class NicheBoardsCrawler(BaseCrawler):
    source_name = "niche_boards"
    requires_js = False
    rate_limit_per_second = 0.5

    NICHE_SOURCES = [
        {
            "name": "climatebase",
            "url": "https://climatebase.org/jobs?l=Remote&q=intern",
            "static": True,
        },
        {
            "name": "80000hours",
            "url": "https://jobs.80000hours.org/?refinementList%5Btags_area%5D%5B0%5D=Tech",
            "static": True,
        },
        {
            "name": "outreachy",
            "url": "https://www.outreachy.org/apply/project-selection/",
            "static": True,
        },
        {
            "name": "lfx_mentorship",
            "url": "https://mentorship.lfx.linuxfoundation.org/",
            "static": True,
        },
    ]

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for source in self.NICHE_SOURCES:
                try:
                    resp = await client.get(
                        source["url"],
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                    )
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")

                    for card in soup.select(
                        "article, .job-card, [class*='job'], [class*='listing'], tr"
                    ):
                        title_el = (
                            card.select_one("h3")
                            or card.select_one("h2")
                            or card.select_one(".title")
                            or card.select_one("a")
                        )
                        company_el = (
                            card.select_one(".company")
                            or card.select_one(".org")
                            or card.select_one(".employer")
                        )
                        desc_el = card.select_one(".description") or card.select_one(
                            "p"
                        )
                        link_el = card.select_one("a[href]")

                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        if not title or len(title) < 5:
                            continue

                        company = (
                            company_el.get_text(strip=True) if company_el else "Unknown"
                        )
                        description = desc_el.get_text(strip=True) if desc_el else ""

                        href = ""
                        if link_el:
                            href = link_el.get("href", "")
                            if href and not href.startswith("http"):
                                base = source["url"].rstrip("/")
                                href = (
                                    base + href
                                    if href.startswith("/")
                                    else f"{base}/{href}"
                                )

                        job = RawJob(
                            title=title,
                            company=company,
                            location="Remote",
                            remote_status="remote",
                            job_type="internship"
                            if "intern" in title.lower()
                            else "fulltime",
                            skills_required=self._extract_skills(
                                description + " " + title.lower()
                            ),
                            description=description,
                            apply_link=href or source["url"],
                            source_platform=f"niche_{source['name']}",
                            source_url=source["url"],
                            posted_date=datetime.now(timezone.utc),
                        )
                        jobs.append(job)

                except Exception:
                    continue

        return jobs

    def _extract_skills(self, text: str) -> list[str]:
        known_skills = [
            "python",
            "javascript",
            "typescript",
            "react",
            "angular",
            "vue",
            "node",
            "fastapi",
            "django",
            "flask",
            "rust",
            "golang",
            "java",
            "kotlin",
            "swift",
            "machine learning",
            "deep learning",
            "nlp",
            "computer vision",
            "tensorflow",
            "pytorch",
            "docker",
            "kubernetes",
            "aws",
            "gcp",
            "azure",
            "terraform",
            "sql",
            "postgresql",
            "mongodb",
            "redis",
            "graphql",
            "grpc",
            "linux",
            "bash",
            "git",
            "ci/cd",
            "github actions",
        ]
        text_lower = text.lower()
        return [s for s in known_skills if s in text_lower]
