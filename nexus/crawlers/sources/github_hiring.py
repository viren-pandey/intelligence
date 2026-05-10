import httpx
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from crawlers.base import BaseCrawler, RawJob


class GitHubHiringCrawler(BaseCrawler):
    source_name = "github_hiring"
    requires_js = False
    rate_limit_per_second = 0.5

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        hiring_keywords = [
            "hiring",
            "open position",
            "we're looking for",
            "we are looking for",
            "join our team",
            "careers",
            "job opening",
            "intern",
        ]

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    "https://api.github.com/search/users?q=hiring+type:org&per_page=30",
                    headers={
                        "User-Agent": "NEXUS/1.0",
                        "Accept": "application/vnd.github.v3+json",
                    },
                )
                if resp.status_code != 200:
                    return jobs

                data = resp.json()
                orgs = data.get("items", [])

                for org in orgs[:20]:
                    org_login = org.get("login", "")
                    if not org_login:
                        continue

                    try:
                        repo_resp = await client.get(
                            f"https://api.github.com/repos/{org_login}/{org_login}/readme",
                            headers={
                                "User-Agent": "NEXUS/1.0",
                                "Accept": "application/vnd.github.v3.raw",
                            },
                        )
                        if repo_resp.status_code != 200:
                            repo_resp = await client.get(
                                f"https://api.github.com/repos/{org_login}/.github/readme",
                                headers={
                                    "User-Agent": "NEXUS/1.0",
                                    "Accept": "application/vnd.github.v3.raw",
                                },
                            )
                        if repo_resp.status_code != 200:
                            continue

                        content = repo_resp.text
                        content_lower = content.lower()

                        if not any(kw in content_lower for kw in hiring_keywords):
                            continue

                        org_url = f"https://github.com/{org_login}"
                        org_about = org.get("description", "")

                        sections = re.split(r"#{2,}\s*", content)
                        for section in sections:
                            section_lower = section.lower()
                            if not any(kw in section_lower for kw in hiring_keywords):
                                continue

                            lines = section.strip().split("\n")
                            for line in lines[:20]:
                                line = line.strip()
                                if (
                                    not line
                                    or line.startswith("#")
                                    or line.startswith("!")
                                ):
                                    continue
                                if len(line) < 10 or len(line) > 200:
                                    continue
                                if any(
                                    kw in line.lower()
                                    for kw in ["http", "email", "apply", "contact"]
                                ):
                                    job = RawJob(
                                        title=line[:100].strip(),
                                        company=org_login,
                                        company_domain=f"{org_login}.com",
                                        company_about=org_about,
                                        location="Remote",
                                        remote_status="remote",
                                        job_type="internship"
                                        if "intern" in line.lower()
                                        else "fulltime",
                                        apply_link=org_url,
                                        source_platform="github_hiring",
                                        source_url=org_url,
                                        posted_date=datetime.now(timezone.utc),
                                    )
                                    jobs.append(job)
                                    break

                    except Exception:
                        continue

            except Exception:
                pass

        return jobs
