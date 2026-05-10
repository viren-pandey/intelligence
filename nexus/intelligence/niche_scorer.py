from models.job import EnrichedJob

MAINSTREAM_PLATFORMS = {"linkedin_public", "internshala_public", "naukri", "indeed"}
NICHE_PLATFORMS = {"niche_boards", "founder_posts", "github_hiring", "career_pages"}


def is_founder_hiring(job: EnrichedJob) -> bool:
    founder_indicators = [
        "founder",
        "ceo",
        "co-founder",
        "direct hire",
        "dm me",
        "reach out",
        "we're a small team",
    ]
    text = f"{job.title} {job.description}".lower()
    return any(indicator in text for indicator in founder_indicators)


def company_size_is_small(company_size: str | None) -> bool:
    if not company_size:
        return False
    small_sizes = ["1-10", "11-50", "1-50", "self-employed", "startup"]
    return any(s in company_size.lower() for s in small_sizes)


def compute_niche_score(job: EnrichedJob) -> tuple[float, bool]:
    score = 0.0

    if job.source_platform not in MAINSTREAM_PLATFORMS:
        score += 0.3

    if job.source_platform in NICHE_PLATFORMS:
        score += 0.3

    if company_size_is_small(job.company_size):
        score += 0.2

    if is_founder_hiring(job):
        score += 0.2

    is_niche = score >= 0.5
    final_score = min(score, 1.0)

    job.niche_score = final_score
    job.is_niche = is_niche
    return final_score, is_niche
