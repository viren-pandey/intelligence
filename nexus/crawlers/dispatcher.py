import asyncio
from core.logging import get_logger
from core.database import execute, fetch

from crawlers.base import CrawlSourceResult
from crawlers.sources.remoteok import RemoteOKCrawler
from crawlers.sources.yc_jobs import YCJobsCrawler
from crawlers.sources.weworkremotely import WeWorkRemotelyCrawler
from crawlers.sources.linkedin_public import LinkedInPublicCrawler
from crawlers.sources.github_hiring import GitHubHiringCrawler
from crawlers.sources.google_serp import GoogleSERPCrawler
from crawlers.sources.niche_boards import NicheBoardsCrawler
from crawlers.sources.career_pages import CareerPagesCrawler
from crawlers.sources.internshala_public import InternshalaPublicCrawler
from crawlers.sources.founder_posts import FounderPostsCrawler
from crawlers.sources.producthunt import ProductHuntCrawler
from crawlers.sources.nitter_twitter import NitterTwitterCrawler
from crawlers.sources.discord_jobs import DiscordJobsCrawler


class CrawlerDispatcher:
    ALL_CRAWLERS = {
        "remoteok": RemoteOKCrawler,
        "yc_jobs": YCJobsCrawler,
        "weworkremotely": WeWorkRemotelyCrawler,
        "linkedin_public": LinkedInPublicCrawler,
        "github_hiring": GitHubHiringCrawler,
        "google_serp": GoogleSERPCrawler,
        "niche_boards": NicheBoardsCrawler,
        "career_pages": CareerPagesCrawler,
        "internshala_public": InternshalaPublicCrawler,
        "founder_posts": FounderPostsCrawler,
        "producthunt": ProductHuntCrawler,
        "nitter_twitter": NitterTwitterCrawler,
        "discord_jobs": DiscordJobsCrawler,
    }

    async def get_enabled_crawlers(self) -> list:
        try:
            rows = await fetch("SELECT source_name, enabled FROM crawler_sources")
            enabled_map = {r["source_name"]: r["enabled"] for r in rows}
        except Exception:
            enabled_map = {}

        crawler_list = []
        for name, cls in self.ALL_CRAWLERS.items():
            if name in enabled_map and not enabled_map[name]:
                continue
            crawler_list.append(cls)
        return crawler_list

    async def update_source_health(
        self, source_name: str, success: bool, jobs_found: int, latency_ms: int
    ):
        try:
            if success:
                await execute(
                    """UPDATE crawler_sources
                       SET last_success_at = NOW(),
                           success_count_24h = success_count_24h + 1,
                           avg_jobs_per_crawl = (avg_jobs_per_crawl * 0.9) + ($2 * 0.1),
                           avg_latency_ms = (avg_latency_ms * 0.9) + ($3 * 0.1)
                       WHERE source_name = $1""",
                    source_name,
                    jobs_found,
                    latency_ms,
                )
            else:
                await execute(
                    """UPDATE crawler_sources
                       SET last_failure_at = NOW(),
                           failure_count_24h = failure_count_24h + 1
                       WHERE source_name = $1""",
                    source_name,
                )
        except Exception:
            pass

    async def dispatch(
        self, session_id: str, queries: list[str]
    ) -> list[CrawlSourceResult]:
        log = get_logger("crawler.dispatcher")

        crawler_classes = await self.get_enabled_crawlers()
        log.info(
            "dispatching_crawlers", session_id=session_id, count=len(crawler_classes)
        )

        tasks = [
            crawler_class().run(session_id, queries)
            for crawler_class in crawler_classes
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        for r in results:
            if isinstance(r, Exception):
                log.error("crawler_raised_unexpected", error=str(r))
                continue
            all_results.append(r)
            await self.update_source_health(
                r.source_name,
                r.status == "complete",
                r.jobs_found,
                int(r.duration_seconds * 1000),
            )

        succeeded = sum(1 for r in all_results if r.status == "complete")
        failed = sum(1 for r in all_results if r.status == "failed")
        total_jobs = sum(r.jobs_found for r in all_results)

        await execute(
            """UPDATE crawl_sessions
               SET completed_at = NOW(),
                   sources_succeeded = $2,
                   sources_failed = $3,
                   total_sources = $4,
                   total_jobs_found = $5,
                   status = CASE WHEN $6 = 0 THEN 'failed'::text ELSE 'complete'::text END
               WHERE session_id = $1::uuid""",
            session_id,
            succeeded,
            failed,
            len(all_results),
            total_jobs,
            succeeded,
        )

        log.info(
            "dispatch_complete",
            session_id=session_id,
            succeeded=succeeded,
            failed=failed,
            total_jobs=total_jobs,
        )

        return all_results


dispatcher = CrawlerDispatcher()
