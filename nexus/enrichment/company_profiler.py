import httpx
import whois
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from core.database import execute, fetchrow
from core.logging import get_logger


@dataclass
class CompanyProfile:
    company_domain: str
    company_name: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    funding_stage: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    tech_stack: list[str] = field(default_factory=list)
    domain_age_days: Optional[int] = None


class CompanyProfiler:
    async def build_profile(self, company_name: str, domain: str) -> CompanyProfile:
        log = get_logger("company_profiler")
        profile = CompanyProfile(company_domain=domain, company_name=company_name)

        cached = await self._get_cached(domain)
        if cached:
            return cached

        try:
            domain_age = await self._get_domain_age(domain)
            if domain_age is not None:
                profile.domain_age_days = domain_age
        except Exception as e:
            log.debug("domain_age_failed", domain=domain, error=str(e))

        try:
            await self._scrape_crunchbase(profile)
        except Exception as e:
            log.debug("crunchbase_failed", domain=domain, error=str(e))

        try:
            https_ok = await self._check_https(domain)
        except Exception:
            https_ok = False

        await self._cache_profile(profile)
        return profile

    async def _get_domain_age(self, domain: str) -> Optional[int]:
        try:
            loop = asyncio.get_event_loop()
            w = await loop.run_in_executor(None, lambda: whois.whois(domain))
            if w.creation_date:
                if isinstance(w.creation_date, list):
                    creation = w.creation_date[0]
                else:
                    creation = w.creation_date
                if isinstance(creation, datetime):
                    delta = datetime.now(timezone.utc) - creation.replace(
                        tzinfo=timezone.utc
                    )
                    return delta.days
        except Exception:
            pass
        return None

    async def _check_https(self, domain: str) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=False
            ) as client:
                resp = await client.get(f"https://{domain}")
                return resp.status_code < 400
        except Exception:
            return False

    async def _scrape_crunchbase(self, profile: CompanyProfile):
        search_url = f"https://www.crunchbase.com/organization/{profile.company_domain.split('.')[0]}"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                resp = await client.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                )
                if resp.status_code == 200:
                    html = resp.text.lower()
                    if "series a" in html or "series b" in html:
                        for stage in [
                            "series a",
                            "series b",
                            "series c",
                            "series d",
                            "seed",
                            "ipo",
                            "acquired",
                        ]:
                            if stage in html:
                                profile.funding_stage = stage.title()
                                break
                    size_keywords = {
                        "1-10": "1-10",
                        "11-50": "11-50",
                        "51-200": "51-200",
                        "201-500": "201-500",
                        "501-1000": "501-1000",
                        "1001+": "1001+",
                    }
                    for size_key, size_val in size_keywords.items():
                        if size_key in html:
                            profile.company_size = size_val
                            break
            except Exception:
                pass

    async def _get_cached(self, domain: str) -> Optional[CompanyProfile]:
        row = await fetchrow(
            "SELECT * FROM company_intelligence WHERE company_domain = $1",
            domain,
        )
        if row and row["last_refreshed"]:
            age = (
                datetime.now(timezone.utc)
                - row["last_refreshed"].replace(tzinfo=timezone.utc)
            ).days
            if age < 7:
                return CompanyProfile(
                    company_domain=row["company_domain"],
                    company_name=row["company_name"],
                    company_size=row["company_size"],
                    industry=row["industry"],
                    funding_stage=row["funding_stage"],
                    founded_year=row["founded_year"],
                    headquarters=row["headquarters"],
                    tech_stack=row["tech_stack"] or [],
                    domain_age_days=row["domain_age_days"],
                )
        return None

    async def _cache_profile(self, profile: CompanyProfile):
        await execute(
            """INSERT INTO company_intelligence
               (company_domain, company_name, company_size, industry, funding_stage,
                founded_year, headquarters, tech_stack, domain_age_days)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
               ON CONFLICT (company_domain)
               DO UPDATE SET company_name = EXCLUDED.company_name,
                             company_size = EXCLUDED.company_size,
                             industry = EXCLUDED.industry,
                             funding_stage = EXCLUDED.funding_stage,
                             domain_age_days = EXCLUDED.domain_age_days,
                             last_refreshed = NOW()""",
            profile.company_domain,
            profile.company_name,
            profile.company_size,
            profile.industry,
            profile.funding_stage,
            profile.founded_year,
            profile.headquarters,
            profile.tech_stack,
            profile.domain_age_days,
        )
