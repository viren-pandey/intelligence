from pydantic import BaseModel, Field
from typing import Optional


class IncomingProfile(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    college: Optional[str] = None
    degree: Optional[str] = None
    graduation_year: Optional[int] = None
    branch: Optional[str] = None
    skills: list[str] = []
    certifications: list[str] = []
    projects: list[str] = []
    internships: list[str] = []
    experience_months: int = 0
    preferred_roles: list[str] = []
    preferred_location: list[str] = []
    remote_preference: str = "any"
    salary_expectation_inr: Optional[int] = None
    companies_of_interest: list[str] = []
    profile_summary: Optional[str] = None


class AnalyzeOptions(BaseModel):
    max_results: int = 50
    include_unpaid: bool = True
    include_niche: bool = True
    freshness_days: int = 30
    mode: str = "sync"
    webhook_url: Optional[str] = None


class AnalyzeRequest(BaseModel):
    request_id: str
    source: str = "internhunt"
    student: IncomingProfile
    options: AnalyzeOptions = AnalyzeOptions()
