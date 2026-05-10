import re
import httpx
from datetime import datetime, timezone
from typing import Optional

from models.job import EnrichedJob
from enrichment.company_profiler import CompanyProfile
from core.database import fetchval

PAYMENT_PATTERNS = [
    r"registration\s*fee",
    r"pay\s*to\s*apply",
    r"deposit",
    r"processing\s*fee",
    r"application\s*fee",
    r"joining\s*fee",
    r"security\s*deposit",
    r"money\s*back",
    r"refundable\s*deposit",
    r"pay\s*us",
    r"send\s*us\s*(rs|inr|\$|€|£)",
]


async def compute_trust_score(
    job: EnrichedJob, company_profile: Optional[CompanyProfile] = None
) -> float:
    scores = {}
    text_to_check = f"{job.title} {job.description} {job.eligibility or ''}".lower()

    for pattern in PAYMENT_PATTERNS:
        if re.search(pattern, text_to_check):
            job.verified = False
            return 0.0

    domain = job.company_domain or ""
    if domain:
        apply_link_alive = await _check_apply_link(job.apply_link)
        if not apply_link_alive:
            job.verified = False
            return 0.0
        scores["apply_link_alive"] = 1.0 if apply_link_alive else 0.0
    else:
        scores["apply_link_alive"] = 0.5

    if company_profile and company_profile.domain_age_days is not None:
        age = company_profile.domain_age_days
        if age < 90:
            scores["domain_age"] = 0.0
        elif age < 365:
            scores["domain_age"] = 0.3
        elif age < 730:
            scores["domain_age"] = 0.7
        else:
            scores["domain_age"] = 1.0
    else:
        scores["domain_age"] = 0.3

    scores["https"] = 1.0 if job.apply_link.startswith("https://") else 0.3

    has_schema = bool(
        job.description
        and (
            "description" in job.description.lower()
            or "qualification" in job.description.lower()
        )
    )
    scores["schema_org_present"] = 1.0 if has_schema else 0.3

    company_footprint = await _check_company_footprint(job.company)
    scores["company_footprint"] = company_footprint

    posting_history = await _check_posting_history(job.company)
    scores["posting_history"] = 0.2 if posting_history else 0.0

    weights = {
        "domain_age": 0.15,
        "https": 0.05,
        "schema_org_present": 0.20,
        "company_footprint": 0.20,
        "apply_link_alive": 0.30,
        "posting_history": 0.10,
    }

    final = sum(scores.get(k, 0.0) * v for k, v in weights.items())
    job.trust_score = round(final, 4)
    job.verified = job.trust_score > 0.6
    return job.trust_score


async def _check_apply_link(apply_link: str) -> bool:
    if not apply_link:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.head(apply_link)
            return resp.status_code < 400
    except Exception:
        return False


async def _check_company_footprint(company: str) -> float:
    if not company:
        return 0.0
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            search_url = (
                f"https://www.google.com/search?q={company}+linkedin+crunchbase"
            )
            resp = await client.get(
                search_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
            )
            if resp.status_code == 200:
                has_linkedin = "linkedin.com/company" in resp.text.lower()
                has_crunchbase = "crunchbase.com" in resp.text.lower()
                score = 0.0
                if has_linkedin:
                    score += 0.6
                if has_crunchbase:
                    score += 0.4
                return score
    except Exception:
        pass
    return 0.2


async def _check_posting_history(company: str) -> bool:
    try:
        count = await fetchval(
            "SELECT COUNT(*) FROM jobs WHERE company = $1 AND trust_score > 0.5",
            company,
        )
        return count > 0
    except Exception:
        return False
