from pydantic import BaseModel
from typing import Optional
from models.job import RankedJobResult


class CrawlMetadata(BaseModel):
    sources_crawled: int = 0
    sources_failed: int = 0
    total_raw_jobs: int = 0
    duplicates_removed: int = 0
    expired_removed: int = 0
    low_trust_removed: int = 0
    final_ranked: int = 0


class AnalyzeResponse(BaseModel):
    request_id: str
    status: str = "complete"
    crawl_session_id: str
    total_discovered: int = 0
    total_after_filter: int = 0
    processing_time_ms: int = 0
    results: list[RankedJobResult] = []
    crawl_metadata: CrawlMetadata = CrawlMetadata()
