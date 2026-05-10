import dns.resolver
import asyncio


async def validate_mx(email: str) -> bool:
    try:
        domain = email.split("@")[1]
        loop = asyncio.get_event_loop()
        records = await loop.run_in_executor(
            None, lambda: dns.resolver.resolve(domain, "MX")
        )
        return len(records) > 0
    except Exception:
        return False
