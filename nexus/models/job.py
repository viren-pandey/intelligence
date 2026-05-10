from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class RawJob(BaseModel):
    title: str
    company: str
    company_domain: Optional[str] = None
    company_about: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    funding_stage: Optional[str] = None
    location: str = "Unknown"
    remote_status: str = "unknown"
    job_type: str = "unknown"
    duration: Optional[str] = None
    paid: Optional[bool] = None
    stipend_inr: Optional[int] = None
    salary_range: Optional[str] = None
    skills_required: list[str] = []
    description: str = ""
    eligibility: Optional[str] = None
    batch_eligible: Optional[str] = None
    apply_link: str
    source_platform: str
    source_url: str
    posted_date: Optional[datetime] = None
    deadline: Optional[datetime] = None


class EnrichedJob(RawJob):
    job_id: str = ""
    crawl_session_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    trust_score: float = 0.0
    freshness_score: float = 0.0
    niche_score: float = 0.0
    is_niche: bool = False
    verified: bool = False
    is_expired: bool = False
    simhash: Optional[int] = None
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_linkedin: Optional[str] = None


class ScoredJob(EnrichedJob):
    ats_match_score: float = 0.0
    match_reason: str = ""
    rank_score: float = 0.0


class RankedJobResult(BaseModel):
    job_id: str
    rank: int
    ats_match_score: float
    match_reason: str
    niche_score: float
    title: str
    company: str
    company_about: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    funding_stage: Optional[str] = None
    location: str
    remote_status: str
    job_type: str
    duration: Optional[str] = None
    paid: Optional[bool] = None
    stipend_inr: Optional[int] = None
    salary_range: Optional[str] = None
    skills_required: list[str] = []
    skills_matched: list[str] = []
    skills_missing: list[str] = []
    batch_eligible: Optional[str] = None
    posted_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    days_until_deadline: Optional[int] = None
    apply_link: str
    source_platform: str
    source_url: str
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_linkedin: Optional[str] = None
    trust_score: float
    freshness_score: float
    verified: bool
    is_niche: bool
    nexus_job_id: str
