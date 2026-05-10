from datetime import datetime, timezone

from core.redis_client import get_client
from core.database import fetchval


async def check_rate_limit(client_id: str, max_per_hour: int) -> bool:
    now = datetime.now(timezone.utc)
    window_start = now.replace(minute=0, second=0, microsecond=0)

    try:
        redis = get_client()
        key = f"nexus:ratelimit:{client_id}:{window_start.isoformat()}"

        current = await redis.get(key)
        if current is None:
            await redis.setex(key, 3600, 1)
            return True

        count = int(current)
        if count >= max_per_hour:
            return False

        await redis.incr(key)
        return True
    except Exception:
        return True


async def get_remaining_credits(client_id: str) -> int:
    row = await fetchval(
        "SELECT credits_remaining FROM api_clients WHERE id = $1::uuid",
        client_id,
    )
    return row or 0


async def deduct_credit(client_id: str) -> bool:
    from core.database import execute

    row = await execute(
        "UPDATE api_clients SET credits_remaining = credits_remaining - 1 WHERE id = $1::uuid AND credits_remaining > 0",
        client_id,
    )
    return "UPDATE 1" in row if row else False


async def get_client_limits(client_id: str):
    from core.database import fetchrow

    row = await fetchrow(
        "SELECT rate_limit_per_hour, max_results_cap, credits_remaining FROM api_clients WHERE id = $1::uuid",
        client_id,
    )
    if row:
        return {
            "rate_limit_per_hour": row["rate_limit_per_hour"],
            "max_results_cap": row["max_results_cap"],
            "credits_remaining": row["credits_remaining"],
        }
    return {"rate_limit_per_hour": 10, "max_results_cap": 10, "credits_remaining": 0}
