from datetime import datetime, timezone

from models.job import EnrichedJob


def compute_freshness_score(
    job: EnrichedJob, crawl_date: datetime | None = None
) -> float:
    if crawl_date is None:
        crawl_date = datetime.now(timezone.utc)

    if job.deadline:
        deadline = job.deadline
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline < crawl_date:
            job.freshness_score = 0.0
            job.is_expired = True
            return 0.0

    if not job.posted_date:
        job.freshness_score = 0.3
        return 0.3

    posted = job.posted_date
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)

    days_old = (crawl_date - posted).days

    if days_old <= 3:
        score = 1.0
    elif days_old <= 7:
        score = 0.9
    elif days_old <= 14:
        score = 0.75
    elif days_old <= 21:
        score = 0.65
    elif days_old <= 30:
        score = 0.5
    elif days_old <= 60:
        score = 0.2
    else:
        score = 0.05

    job.freshness_score = score
    return score
