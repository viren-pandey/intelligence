import random
import time
from typing import Optional

from core.config import settings


class ProxyPool:
    def __init__(self):
        self._proxies: list[str] = list(settings.PROXY_LIST)
        self._banned: dict[str, float] = {}
        self._ban_duration_seconds = 3600

    def get_proxy(self, domain: str = "") -> Optional[str]:
        now = time.time()
        self._banned = {
            ip: ban_until for ip, ban_until in self._banned.items() if ban_until > now
        }

        available = [p for p in self._proxies if p not in self._banned]
        if not available:
            return None

        return random.choice(available)

    def ban_proxy(self, ip: str):
        self._banned[ip] = time.time() + self._ban_duration_seconds

    def add_proxy(self, proxy: str):
        if proxy not in self._proxies:
            self._proxies.append(proxy)

    @property
    def count(self) -> int:
        return len(self._proxies)

    @property
    def banned_count(self) -> int:
        now = time.time()
        return sum(1 for v in self._banned.values() if v > now)


proxy_pool = ProxyPool()
