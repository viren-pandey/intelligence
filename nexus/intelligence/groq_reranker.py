import json
import httpx
from core.config import settings
from core.logging import get_logger

log = get_logger("intelligence.groq_reranker")

RERANK_SYSTEM_PROMPT = """You are a recruitment AI that analyzes job listings and ranks them by fit for a specific candidate profile.

For each job, evaluate:
1. SKILLS FIT (0-100): How well the candidate's skills match the job requirements
2. ROLE FIT (0-100): How well the job title/role matches the candidate's target roles
3. COMPANY FIT (0-100): Is the company legitimate? Does it match the candidate's preferences?
4. FRESHNESS (0-100): Is the posting recent and still open?
5. COMPENSATION (0-100): Does the pay match expectations?

Return JSON array: [{"index":0,"score":<0-100>,"reason":"..."}]
Score 0-100 overall fit. Reason must be 1 sentence explaining the match."""


async def groq_rerank(profile_dict: dict, ats_signals_dict: dict, jobs: list) -> list:
    if not settings.GROQ_API_KEY or not jobs:
        return jobs

    try:
        profile_text = _build_profile_text(profile_dict, ats_signals_dict)
        jobs_text = _build_jobs_text(jobs)

        if not jobs_text.strip():
            return jobs

        prompt = f"Candidate Profile:\n{profile_text}\n\nJobs to rank:\n{jobs_text}\n\nReturn JSON array of {{index, score, reason}} for each job."

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
            )
            if resp.status_code != 200:
                log.warning("groq_api_error", status=resp.status_code)
                return jobs

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
                content = content.rsplit("```", 1)[0]
            content = content.strip()

            rerank_results = json.loads(content)
            if not isinstance(rerank_results, list):
                return jobs

            score_map = {}
            for item in rerank_results:
                idx = item.get("index")
                score = item.get("score", 50)
                reason = item.get("reason", "")
                if idx is not None and 0 <= idx < len(jobs):
                    score_map[idx] = (score, reason)

            for idx, (score, reason) in score_map.items():
                if score < 30:
                    jobs[idx].trust_score = max(jobs[idx].trust_score * 0.3, 0)
                    jobs[idx].match_reason = f"[GROQ] Low fit: {reason}"
                else:
                    groq_factor = score / 100.0
                    jobs[idx].ats_match_score = (
                        jobs[idx].ats_match_score * 0.5 + groq_factor * 0.5
                    )
                    jobs[idx].match_reason = f"[GROQ] {reason}"

            ranked = sorted(
                jobs,
                key=lambda j: (
                    j.ats_match_score * 0.4
                    + j.trust_score * 0.3
                    + j.freshness_score * 0.2
                    + j.niche_score * 0.1
                ),
                reverse=True,
            )
            log.info("groq_rerank_complete", total=len(jobs), reranked=len(score_map))
            return ranked

    except Exception as e:
        log.warning("groq_rerank_failed", error=str(e))
        return jobs


def _build_profile_text(profile: dict, signals: dict) -> str:
    parts = []
    if profile.get("full_name"):
        parts.append(f"Name: {profile['full_name']}")
    if profile.get("college"):
        parts.append(f"College: {profile['college']}")
    if profile.get("degree"):
        parts.append(f"Degree: {profile['degree']}")
    if profile.get("graduation_year"):
        parts.append(f"Graduation Year: {profile['graduation_year']}")
    if profile.get("branch"):
        parts.append(f"Branch: {profile['branch']}")
    if profile.get("skills"):
        parts.append(f"Skills: {', '.join(profile['skills'])}")
    if profile.get("preferred_roles"):
        parts.append(f"Target Roles: {', '.join(profile['preferred_roles'])}")
    if profile.get("preferred_location"):
        parts.append(f"Location: {', '.join(profile['preferred_location'])}")
    if profile.get("profile_summary"):
        parts.append(f"Summary: {profile['profile_summary']}")
    if signals.get("skill_domains"):
        parts.append(f"Domains: {', '.join(signals['skill_domains'].keys())}")
    return "\n".join(parts)


def _build_jobs_text(jobs: list) -> str:
    lines = []
    for i, j in enumerate(jobs):
        lines.append(
            f"[{i}] {j.title} at {j.company} | {j.location} | {j.job_type} | "
            f"Skills: {', '.join(j.skills_required[:8])} | "
            f"Paid: {j.paid} | Stipend: {j.stipend_inr} | Remote: {j.remote_status} | "
            f"Deadline: {j.deadline}"
        )
    return "\n".join(lines[:50])
