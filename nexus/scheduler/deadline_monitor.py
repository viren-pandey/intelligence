import asyncio
from datetime import datetime, timezone

from core.celery_app import celery_app
from core.database import fetch, execute
from core.logging import get_logger


@celery_app.task(bind=True, max_retries=3)
def run_deadline_monitor(self):
    asyncio.run(_do_deadline_monitor())


async def _do_deadline_monitor():
    log = get_logger("scheduler.deadline_monitor")
    log.info("deadline_monitor_started")

    try:
        expired = await fetch(
            """SELECT job_id, title, company, location, remote_status, job_type,
                      paid, stipend_inr, skills_required, apply_link, source_platform,
                      posted_date, deadline
               FROM jobs
               WHERE deadline < NOW() AND is_expired = FALSE"""
        )

        expired_count = len(expired)
        log.info("found_expired_jobs", count=expired_count)

        for row in expired:
            try:
                await execute(
                    """INSERT INTO deleted_jobs
                       (job_id, title, company, location, remote_status, job_type,
                        paid, stipend_inr, skills_required, apply_link, source_platform,
                        posted_date, original_deadline, deleted_reason, deleted_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,'deadline_passed',NOW())""",
                    row["job_id"],
                    row["title"],
                    row["company"],
                    row["location"],
                    row["remote_status"],
                    row["job_type"],
                    row["paid"],
                    row["stipend_inr"],
                    row["skills_required"] or [],
                    row["apply_link"],
                    row["source_platform"],
                    row["posted_date"],
                    row["deadline"],
                )

                await execute("DELETE FROM jobs WHERE job_id = $1::uuid", row["job_id"])
            except Exception as e:
                log.error(
                    "failed_to_expire_job", job_id=str(row["job_id"]), error=str(e)
                )

        no_deadline_old = await fetch(
            """SELECT job_id, title, company, posted_date
               FROM jobs
               WHERE deadline IS NULL
                 AND posted_date < NOW() - INTERVAL '60 days'
                 AND is_expired = FALSE"""
        )

        for row in no_deadline_old:
            await execute(
                "UPDATE jobs SET is_expired = TRUE WHERE job_id = $1::uuid",
                row["job_id"],
            )

        log.info(
            "deadline_monitor_complete",
            expired_moved=expired_count,
            likely_expired=len(no_deadline_old),
        )

    except Exception as e:
        log.error("deadline_monitor_failed", error=str(e))
