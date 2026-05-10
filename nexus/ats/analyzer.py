from dataclasses import dataclass, field
from typing import Optional
from models.profile import IncomingProfile
from ats.skill_normalizer import normalize_skills, get_skill_domains
from ats.role_taxonomy import map_roles_to_taxonomy
from ats.query_builder import build_search_queries


@dataclass
class ATSSignals:
    normalized_skills: list[str] = field(default_factory=list)
    skill_domains: dict = field(default_factory=dict)
    role_taxonomy: set = field(default_factory=set)
    seniority: str = "fresher"
    location_preference: list[str] = field(default_factory=list)
    remote_required: bool = False
    compensation_floor_inr: int = 0
    interest_clusters: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    profile_completeness_score: float = 0.0
    graduation_year: Optional[int] = None
    companies_of_interest: list[str] = field(default_factory=list)


class ATSAnalyzer:
    def analyze(self, profile: IncomingProfile) -> ATSSignals:
        normalized_skills = normalize_skills(profile.skills)
        skill_domains = get_skill_domains(normalized_skills)
        role_taxonomy = map_roles_to_taxonomy(profile.preferred_roles)
        seniority = self._compute_seniority(profile)
        location_pref = self._build_location_preference(profile)
        remote_required = profile.remote_preference.lower() == "remote"
        interest_clusters = self._extract_interest_clusters(profile)
        completeness = self._compute_profile_completeness(profile)

        signals = ATSSignals(
            normalized_skills=normalized_skills,
            skill_domains=skill_domains,
            role_taxonomy=role_taxonomy,
            seniority=seniority,
            location_preference=location_pref,
            remote_required=remote_required,
            compensation_floor_inr=profile.salary_expectation_inr or 0,
            interest_clusters=interest_clusters,
            profile_completeness_score=completeness,
            graduation_year=profile.graduation_year,
            companies_of_interest=[
                c.lower().strip() for c in profile.companies_of_interest
            ],
        )

        signals.search_queries = build_search_queries(
            {
                "normalized_skills": normalized_skills,
                "role_taxonomy": list(role_taxonomy),
                "location_preference": location_pref,
                "remote_required": remote_required,
                "graduation_year": profile.graduation_year,
                "companies_of_interest": profile.companies_of_interest,
            }
        )

        return signals

    def _compute_seniority(self, profile: IncomingProfile) -> str:
        if profile.experience_months >= 24:
            return "mid"
        if profile.experience_months >= 6:
            return "junior"
        if len(profile.internships) >= 2:
            return "junior"
        return "fresher"

    def _build_location_preference(self, profile: IncomingProfile) -> list[str]:
        pref = [loc.lower().strip() for loc in profile.preferred_location if loc]
        if profile.remote_preference.lower() == "remote":
            pref.insert(0, "remote")
        return pref

    def _extract_interest_clusters(self, profile: IncomingProfile) -> list[str]:
        clusters = []
        text = " ".join(
            [
                profile.profile_summary or "",
                " ".join(profile.projects),
                " ".join(profile.preferred_roles),
                " ".join(profile.companies_of_interest),
            ]
        ).lower()

        cluster_keywords = {
            "ml": [
                "machine learning",
                "deep learning",
                "ai",
                "neural network",
                "llm",
                "nlp",
                "computer vision",
            ],
            "fintech": [
                "fintech",
                "finance",
                "banking",
                "payment",
                "blockchain",
                "crypto",
            ],
            "space": ["space", "satellite", "aerospace", "rocket", "orbital"],
            "climate": [
                "climate",
                "environment",
                "sustainability",
                "green",
                "clean energy",
            ],
            "gaming": ["gaming", "game dev", "unity", "unreal", "game design"],
            "health": ["health", "biotech", "healthcare", "medical", "bio"],
            "developer_tools": [
                "developer tools",
                "devtools",
                "api",
                "sdk",
                "open source",
            ],
            "security": ["security", "cyber", "encryption", "privacy", "zero trust"],
        }

        for cluster, keywords in cluster_keywords.items():
            if any(kw in text for kw in keywords):
                clusters.append(cluster)

        return clusters

    def _compute_profile_completeness(self, profile: IncomingProfile) -> float:
        weights = {
            "full_name": 0.05,
            "college": 0.10,
            "degree": 0.10,
            "graduation_year": 0.10,
            "branch": 0.05,
            "skills": 0.20,
            "projects": 0.15,
            "internships": 0.10,
            "preferred_roles": 0.10,
            "preferred_location": 0.05,
        }
        score = 0.0

        if profile.full_name:
            score += weights["full_name"]
        if profile.college:
            score += weights["college"]
        if profile.degree:
            score += weights["degree"]
        if profile.graduation_year:
            score += weights["graduation_year"]
        if profile.branch:
            score += weights["branch"]
        if len(profile.skills) >= 3:
            score += weights["skills"]
        elif len(profile.skills) >= 1:
            score += weights["skills"] * 0.5
        if len(profile.projects) >= 2:
            score += weights["projects"]
        elif len(profile.projects) >= 1:
            score += weights["projects"] * 0.5
        if len(profile.internships) >= 1:
            score += weights["internships"]
        if len(profile.preferred_roles) >= 1:
            score += weights["preferred_roles"]
        if len(profile.preferred_location) >= 1:
            score += weights["preferred_location"]

        return min(score, 1.0)
