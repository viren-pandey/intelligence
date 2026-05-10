import re
import httpx
from dataclasses import dataclass, field
from typing import Optional

from core.database import execute, fetchrow
from core.logging import get_logger


@dataclass
class RecruiterData:
    company_domain: str
    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None
    recruiter_phone: Optional[str] = None
    recruiter_linkedin: Optional[str] = None
    hr_name: Optional[str] = None
    hr_email: Optional[str] = None
    source_url: str = ""


class RecruiterExtractor:
    EMAIL_PATTERNS = [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        r"[a-zA-Z0-9._%+-]+\s*\[at\]\s*[a-zA-Z0-9.-]+\s*\[dot\]\s*[a-zA-Z]{2,}",
    ]

    PHONE_PATTERNS = [
        r"\+?91[-\s]?[6-9]\d{9}",
        r"\+?1[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{4}",
        r"\+?44[-\s]?\d{4}[-\s]?\d{6}",
    ]

    async def extract_from_page(
        self, url: str, company_domain: str
    ) -> Optional[RecruiterData]:
        log = get_logger("recruiter_extractor")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    },
                )
                if resp.status_code != 200:
                    return None

                html = resp.text
                data = RecruiterData(company_domain=company_domain, source_url=url)

                for pattern in self.EMAIL_PATTERNS:
                    emails = re.findall(pattern, html)
                    for email in emails:
                        email_clean = (
                            email.replace("[at]", "@")
                            .replace("[dot]", ".")
                            .replace(" ", "")
                        )
                        if (
                            company_domain
                            and company_domain in email_clean.split("@")[-1]
                        ):
                            data.recruiter_email = email_clean
                            break
                    if data.recruiter_email:
                        break

                linkedin_urls = re.findall(
                    r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+", html
                )
                if linkedin_urls:
                    data.recruiter_linkedin = linkedin_urls[0]

                for pattern in self.PHONE_PATTERNS:
                    phones = re.findall(pattern, html)
                    if phones:
                        data.recruiter_phone = (
                            phones[0].replace(" ", "").replace("-", "")
                        )
                        break

                name_patterns = [
                    r'<meta[^>]+name="author"[^>]+content="([^"]+)"',
                    r'"name":\s*"([^"]+)"',
                    r'"recruiter":\s*"([^"]+)"',
                ]
                for pattern in name_patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        data.recruiter_name = match.group(1).strip()
                        break

                if data.recruiter_email or data.recruiter_linkedin:
                    await self._save_to_db(data)
                    return data

        except Exception as e:
            log.warning("extract_failed", url=url, error=str(e))

        return None

    def infer_email_candidates(self, name: str, domain: str) -> list[str]:
        if not name or not domain:
            return []
        parts = name.lower().strip().split()
        if len(parts) == 1:
            return [f"{parts[0]}@{domain}"]
        first = parts[0]
        last = parts[-1]
        return [
            f"{first}.{last}@{domain}",
            f"{first}@{domain}",
            f"{last}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first}{last}@{domain}",
        ]

    async def _save_to_db(self, data: RecruiterData):
        await execute(
            """INSERT INTO recruiter_intelligence
               (company_domain, recruiter_name, recruiter_email, recruiter_phone, recruiter_linkedin, source_url)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (company_domain, recruiter_email) WHERE recruiter_email IS NOT NULL
               DO UPDATE SET recruiter_name = EXCLUDED.recruiter_name,
                             recruiter_linkedin = EXCLUDED.recruiter_linkedin,
                             extracted_at = NOW()""",
            data.company_domain,
            data.recruiter_name,
            data.recruiter_email,
            data.recruiter_phone,
            data.recruiter_linkedin,
            data.source_url,
        )
