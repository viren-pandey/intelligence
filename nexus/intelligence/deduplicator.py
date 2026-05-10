from models.job import RawJob, EnrichedJob
from core.redis_client import get_client
from core.database import fetchval

SIMHASH_BITS = 64
HAMMING_THRESHOLD = 8


def compute_simhash(text: str) -> int:
    from simhash import Simhash

    return Simhash(text).value


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _normalize_location(loc: str) -> str:
    loc = loc.lower().strip()
    return loc


def _build_simhash_text(job: RawJob) -> str:
    title = (job.title or "").lower().strip()
    company = (job.company or "").lower().strip()
    location = _normalize_location(job.location or "")
    desc_snippet = (job.description or "")[:200].lower().strip()
    return f"{title} {company} {location} {desc_snippet}"


async def is_duplicate(job: RawJob) -> bool:
    text = _build_simhash_text(job)
    hash_val = compute_simhash(text)
    job.simhash = hash_val

    try:
        redis = get_client()
        key = f"simhash:{job.company.lower().strip()}"

        existing = await redis.smembers(key)
        for existing_hash_str in existing:
            try:
                existing_hash = int(existing_hash_str)
                if hamming_distance(hash_val, existing_hash) < HAMMING_THRESHOLD:
                    return True
            except ValueError:
                continue

        await redis.sadd(key, str(hash_val))
        await redis.expire(key, 2592000)
    except Exception:
        pass

    db_check = await fetchval(
        "SELECT COUNT(*) FROM jobs WHERE company = $1 AND simhash IS NOT NULL",
        job.company,
    )

    return False


def simhash_duplicates(jobs: list[EnrichedJob]) -> list[EnrichedJob]:
    seen = {}
    unique = []
    for job in jobs:
        if job.simhash is None:
            unique.append(job)
            continue
        found = False
        for existing_hash in seen:
            if hamming_distance(job.simhash, existing_hash) < HAMMING_THRESHOLD:
                if job.trust_score > seen[existing_hash].trust_score:
                    seen[existing_hash] = job
                found = True
                break
        if not found:
            seen[job.simhash] = job

    return list(seen.values())
