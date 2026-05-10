from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import asyncio
import traceback

from models.job import RawJob
from core.database import execute, fetchrow
from core.logging import get_logger


@dataclass
class CrawlSourceResult:
    source_name: str
    session_id: str
    jobs: list[RawJob] = field(default_factory=list)
    pages_crawled: int = 0
    jobs_found: int = 0
    jobs_rejected: int = 0
    error_count: int = 0
    error_messages: list[str] = field(default_factory=list)
    status: str = "running"
    duration_seconds: float = 0.0


class BaseCrawler(ABC):
    source_name: str = "base"
    requires_js: bool = False
    rate_limit_per_second: float = 1.0

    @abstractmethod
    async def crawl(self, session_id: str, queries: list[str]) -> list[RawJob]: ...

    async def run(self, session_id: str, queries: list[str]) -> CrawlSourceResult:
        log = get_logger(f"crawler.{self.source_name}")
        result = CrawlSourceResult(
            source_name=self.source_name,
            session_id=session_id,
        )

        log_id = await self._log_start(session_id)

        start_time = datetime.now(timezone.utc)
        try:
            jobs = await self.crawl(session_id, queries)
            result.jobs = jobs
            result.jobs_found = len(jobs)
            result.pages_crawled = len(set(j.source_url for j in jobs)) if jobs else 0
            result.status = "complete"

            for job in jobs:
                try:
                    await self._save_job(job, session_id)
                except Exception as e:
                    result.jobs_rejected += 1
                    log.warning("failed_to_save_job", error=str(e), title=job.title)

        except Exception as e:
            result.status = "failed"
            result.error_count += 1
            error_msg = f"{type(e).__name__}: {str(e)}"
            result.error_messages.append(error_msg)
            log.error(
                "crawler_failed",
                source=self.source_name,
                error=error_msg,
                traceback=traceback.format_exc(),
            )

        end_time = datetime.now(timezone.utc)
        result.duration_seconds = (end_time - start_time).total_seconds()

        await self._log_complete(log_id, result)
        return result

    async def _log_start(self, session_id: str) -> str:
        row = await fetchrow(
            """INSERT INTO crawl_source_logs (session_id, source_name, status)
               VALUES ($1, $2, 'running')
               RETURNING id""",
            session_id,
            self.source_name,
        )
        return str(row["id"]) if row else ""

    async def _log_complete(self, log_id: str, result: CrawlSourceResult):
        await execute(
            """UPDATE crawl_source_logs
               SET completed_at = NOW(),
                   pages_crawled = $2,
                   jobs_found = $3,
                   jobs_rejected = $4,
                   error_count = $5,
                   error_messages = $6::jsonb,
                   status = $7
               WHERE id = $1::uuid""",
            log_id,
            result.pages_crawled,
            result.jobs_found,
            result.jobs_rejected,
            result.error_count,
            result.error_messages,
            result.status,
        )

    async def _save_job(self, job: RawJob, session_id: str):
        await execute(
            """INSERT INTO jobs
               (title, company, company_domain, location, remote_status, job_type,
                paid, stipend_inr, skills_required, description, apply_link,
                source_platform, source_url, posted_date, deadline, crawl_session_id,
                batch_eligible, duration, salary_range)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)""",
            job.title,
            job.company,
            job.company_domain,
            job.location,
            job.remote_status,
            job.job_type,
            job.paid,
            job.stipend_inr,
            job.skills_required,
            job.description,
            job.apply_link,
            job.source_platform,
            job.source_url,
            job.posted_date,
            job.deadline,
            session_id,
            job.batch_eligible,
            job.duration,
            job.salary_range,
        )
