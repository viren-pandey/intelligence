import asyncio
import httpx
from typing import Optional

from core.config import settings
from core.logging import get_logger


async def check_link(url: str) -> tuple[str, bool]:
    try:
        async with httpx.AsyncClient(
            timeout=settings.DEAD_LINK_CHECK_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.head(url)
            return url, resp.status_code < 400
    except Exception:
        return url, False


async def validate_apply_links(urls: list[str]) -> dict[str, bool]:
    log = get_logger("dead_link_checker")
    if not urls:
        return {}

    tasks = [check_link(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    status_map = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        url, alive = r
        status_map[url] = alive

    dead = sum(1 for v in status_map.values() if not v)
    if dead:
        log.info("dead_links_found", dead_count=dead, total=len(urls))

    return status_map
