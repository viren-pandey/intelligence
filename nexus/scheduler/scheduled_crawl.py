import asyncio
from datetime import datetime, timezone

from core.celery_app import celery_app
from core.database import execute, fetchrow
from core.logging import get_logger
from crawlers.dispatcher import dispatcher


@celery_app.task(bind=True, max_retries=3)
def run_scheduled_crawl(self, triggered_by: str = "scheduled"):
    asyncio.run(_do_scheduled_crawl(triggered_by))


async def _do_scheduled_crawl(triggered_by: str):
    log = get_logger("scheduler.scheduled_crawl")
    log.info("scheduled_crawl_started", triggered_by=triggered_by)

    year_str = str(datetime.now(timezone.utc).year)
    broad_queries = [
        f'"intern" "{year_str}" "apply"',
        '"fresher" "software" "intern"',
        '"python" "internship" "remote"',
        f'"machine learning" "intern" "{year_str}"',
        '"backend" "intern" "apply"',
        '"frontend" "intern" "remote"',
        '"data science" "internship"',
        f'"devops" "intern" "{year_str}"',
        '"research" "intern" "AI"',
        '"software developer" "fresher"',
    ]

    row = await fetchrow(
        """INSERT INTO crawl_sessions (triggered_by, source_system, status)
           VALUES ($1, 'scheduled', 'running')
           RETURNING session_id""",
        triggered_by,
    )
    session_id = str(row["session_id"])

    try:
        results = await dispatcher.dispatch(session_id, broad_queries)
        total_jobs = sum(r.jobs_found for r in results)

        await execute(
            """UPDATE crawl_sessions
               SET completed_at = NOW(), total_jobs_saved = $2, status = 'complete'
               WHERE session_id = $1::uuid""",
            session_id,
            total_jobs,
        )

        log.info(
            "scheduled_crawl_complete", session_id=session_id, total_jobs=total_jobs
        )
    except Exception as e:
        await execute(
            "UPDATE crawl_sessions SET completed_at = NOW(), status = 'failed' WHERE session_id = $1::uuid",
            session_id,
        )
        log.error("scheduled_crawl_failed", session_id=session_id, error=str(e))
