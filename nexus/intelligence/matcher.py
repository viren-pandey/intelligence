from typing import Optional

from models.job import EnrichedJob
from ats.analyzer import ATSSignals
from ats.skill_normalizer import jaccard_similarity, normalize_skills
from ats.role_taxonomy import taxonomy_overlap


class JobMatcher:
    WEIGHTS = {
        "skills_overlap": 0.35,
        "role_match": 0.25,
        "location_match": 0.15,
        "batch_eligibility": 0.10,
        "compensation_match": 0.10,
        "company_preference": 0.05,
    }

    def score(self, ats_signals: ATSSignals, job: EnrichedJob) -> tuple[float, str]:
        scores = {}

        profile_skills = set(ats_signals.normalized_skills)
        job_skills = set(normalize_skills(job.skills_required))
        scores["skills_overlap"] = jaccard_similarity(profile_skills, job_skills)

        scores["role_match"] = taxonomy_overlap(ats_signals.role_taxonomy, job.title)

        scores["location_match"] = self._location_score(ats_signals, job)

        scores["batch_eligibility"] = self._batch_score(
            ats_signals.graduation_year, job.batch_eligible
        )

        scores["compensation_match"] = self._compensation_score(
            ats_signals.compensation_floor_inr, job.stipend_inr
        )

        scores["company_preference"] = self._company_pref_score(ats_signals, job)

        final = sum(scores[k] * self.WEIGHTS[k] for k in self.WEIGHTS)
        reason = self._generate_reason(scores, ats_signals, job)
        return round(final, 4), reason

    def _location_score(self, signals: ATSSignals, job: EnrichedJob) -> float:
        if signals.remote_required and job.remote_status == "remote":
            return 1.0
        if not signals.location_preference:
            return 0.5
        job_loc = (job.location or "").lower().strip()
        for pref in signals.location_preference:
            if pref == "remote" and job.remote_status == "remote":
                return 1.0
            if pref in job_loc or job_loc in pref:
                return 1.0
        return 0.0

    def _batch_score(
        self, graduation_year: Optional[int], batch_eligible: Optional[str]
    ) -> float:
        if not graduation_year or not batch_eligible:
            return 0.5
        year_str = str(graduation_year)
        if year_str in batch_eligible:
            return 1.0
        try:
            for part in batch_eligible.replace(" ", "").split(","):
                if part.strip() == year_str:
                    return 1.0
            parts = [p.strip() for p in batch_eligible.split(",")]
            for p in parts:
                if p.isdigit() and abs(int(p) - graduation_year) <= 1:
                    return 0.8
        except Exception:
            pass
        return 0.3

    def _compensation_score(self, expected: int, offered: Optional[int]) -> float:
        if expected is None or expected == 0:
            return 0.5
        if offered is None or offered == 0:
            return 0.3
        if offered >= expected:
            return 1.0
        ratio = offered / expected
        if ratio >= 0.75:
            return 0.7
        if ratio >= 0.5:
            return 0.4
        return 0.2

    def _company_pref_score(self, signals: ATSSignals, job: EnrichedJob) -> float:
        if not signals.companies_of_interest:
            return 0.5
        job_company = (job.company or "").lower().strip()
        for pref in signals.companies_of_interest:
            if pref in job_company or job_company in pref:
                return 1.0
        return 0.0

    def _generate_reason(
        self, scores: dict, signals: ATSSignals, job: EnrichedJob
    ) -> str:
        parts = []
        if scores.get("skills_overlap", 0) > 0.4:
            profile_skills = set(signals.normalized_skills)
            job_skills = set(s.lower() for s in job.skills_required)
            matched = list(profile_skills & job_skills)[:3]
            if matched:
                parts.append(f"Matches your {' + '.join(matched)} skills")
        if scores.get("location_match", 0) > 0.5:
            if job.remote_status == "remote":
                parts.append("Remote")
            else:
                parts.append(f"In {job.location}")
        if scores.get("batch_eligibility", 0) > 0.5 and signals.graduation_year:
            parts.append(f"{signals.graduation_year} batch eligible")
        if job.paid and job.stipend_inr:
            parts.append(f"Paid — ₹{job.stipend_inr:,}/month")
        if job.is_niche:
            parts.append("Rare opportunity, not on mainstream boards")
        return ". ".join(parts) if parts else "Matches your profile."


matcher = JobMatcher()
