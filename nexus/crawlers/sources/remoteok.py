import httpx
from datetime import datetime, timezone

from crawlers.base import BaseCrawler, RawJob


class RemoteOKCrawler(BaseCrawler):
    source_name = "remoteok"
    requires_js = False
    rate_limit_per_second = 2.0

    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]:
        jobs = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://remoteok.com/api",
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; NEXUS/1.0)",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code != 200:
                    return jobs

                data = resp.json()
                query_tags = set()
                for q in queries:
                    for word in q.lower().replace('"', "").split():
                        query_tags.add(word)

                for item in data:
                    if not isinstance(item, dict) or "id" not in item:
                        continue

                    title = item.get("position", "") or item.get("title", "")
                    tags = [t.lower() for t in item.get("tags", [])]
                    desc = item.get("description", "").lower()

                    if query_tags:
                        relevance = sum(1 for t in tags if t in query_tags)
                        if relevance == 0 and not any(w in desc for w in query_tags):
                            continue

                    company = item.get("company", "Unknown")
                    url = item.get("url", "")
                    apply = item.get("apply_url", "") or url

                    try:
                        salary_min = item.get("salary_min")
                        salary_max = item.get("salary_max")
                        salary_range = None
                        stipend_inr = None
                        if salary_min and salary_max:
                            salary_range = f"{salary_min}-{salary_max}"
                        if salary_min:
                            usd_to_inr = 83
                            stipend_inr = int(float(salary_min) * usd_to_inr)
                    except (ValueError, TypeError):
                        salary_range = None
                        stipend_inr = None

                    job = RawJob(
                        title=title.strip(),
                        company=company.strip(),
                        location=item.get("location", "Remote"),
                        remote_status="remote",
                        job_type="internship"
                        if "intern" in title.lower()
                        else "fulltime",
                        paid=True,
                        stipend_inr=stipend_inr,
                        salary_range=salary_range,
                        skills_required=tags,
                        description=item.get("description", ""),
                        apply_link=apply,
                        source_platform="remoteok",
                        source_url=url,
                        posted_date=datetime.now(timezone.utc),
                    )
                    jobs.append(job)

        except Exception:
            pass

        return jobs
