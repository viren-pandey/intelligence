import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from core.redis_client import get_client
from core.config import settings
from ats.skill_normalizer import normalize_skills


def _profile_hash(
    skills: list[str], roles: list[str], locations: list[str], remote_pref: str
) -> str:
    normalized = sorted(normalize_skills(skills))
    roles_sorted = sorted(r.lower().strip() for r in roles)
    locs_sorted = sorted(l.lower().strip() for l in locations)
    raw = json.dumps(
        {
            "skills": normalized,
            "roles": roles_sorted,
            "locations": locs_sorted,
            "remote": remote_pref.lower().strip(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_result(
    skills: list[str], roles: list[str], locations: list[str], remote_pref: str
) -> Optional[dict]:
    key = f"nexus:results:{_profile_hash(skills, roles, locations, remote_pref)}"
    try:
        redis = get_client()
        cached = await redis.get(key)
        if cached:
            try:
                return json.loads(cached)
            except (json.JSONDecodeError, TypeError):
                return None
    except Exception:
        pass
    return None


async def set_cached_result(
    skills: list[str],
    roles: list[str],
    locations: list[str],
    remote_pref: str,
    result: dict,
):
    key = f"nexus:results:{_profile_hash(skills, roles, locations, remote_pref)}"
    try:
        redis = get_client()
        await redis.setex(key, settings.CACHE_TTL_SECONDS, json.dumps(result))
    except Exception:
        pass
