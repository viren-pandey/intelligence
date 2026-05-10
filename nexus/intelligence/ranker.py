from models.job import ScoredJob
from models.profile import AnalyzeOptions


def compute_rank_score(
    match: float, freshness: float, trust: float, niche: float
) -> float:
    return (0.45 * match) + (0.25 * freshness) + (0.20 * trust) + (0.10 * niche)


def rank_jobs(
    jobs: list[ScoredJob], max_results: int, options: AnalyzeOptions
) -> list[ScoredJob]:
    filtered = []

    for job in jobs:
        if job.trust_score < 0.3:
            continue
        if job.freshness_score == 0.0:
            continue
        if not options.include_unpaid and job.paid is not None and not job.paid:
            continue
        if not options.include_niche == False and job.is_niche:
            if not options.include_niche:
                continue
        filtered.append(job)

    for job in filtered:
        job.rank_score = compute_rank_score(
            job.ats_match_score,
            job.freshness_score,
            job.trust_score,
            job.niche_score,
        )

    filtered.sort(key=lambda j: j.rank_score, reverse=True)

    company_count = {}
    diverse = []
    for job in filtered:
        company = job.company.lower().strip()
        if company_count.get(company, 0) >= 3:
            continue
        diverse.append(job)
        company_count[company] = company_count.get(company, 0) + 1

    return diverse[:max_results]
