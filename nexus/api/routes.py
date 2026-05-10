import asyncio
import uuid
import json
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Form
from fastapi.responses import JSONResponse

from models.profile import AnalyzeRequest, AnalyzeOptions
from models.response import AnalyzeResponse, CrawlMetadata
from models.job import RawJob, EnrichedJob, ScoredJob, RankedJobResult
from core.config import settings
from core.database import execute, fetch, fetchrow, fetchval, get_pool
from core.logging import get_logger
from ats.analyzer import ATSAnalyzer
from crawlers.dispatcher import dispatcher
from intelligence.deduplicator import simhash_duplicates
from intelligence.trust_scorer import compute_trust_score
from intelligence.freshness_scorer import compute_freshness_score
from intelligence.niche_scorer import compute_niche_score
from intelligence.matcher import matcher as job_matcher
from intelligence.ranker import rank_jobs
from intelligence.result_cache import get_cached_result, set_cached_result
from intelligence.rate_limiter import check_rate_limit, get_client_limits, deduct_credit
from intelligence.dead_link_checker import validate_apply_links
from intelligence.webhook_delivery import deliver_webhook
from enrichment.company_profiler import CompanyProfiler
from enrichment.recruiter_extractor import RecruiterExtractor
from intelligence.groq_reranker import groq_rerank

router = APIRouter()
log = get_logger("api.routes")


def _serialize(r):
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, (uuid.UUID,)):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, bytes):
            d[k] = v.decode()
    return d


async def verify_api_key(api_key: str) -> dict:
    row = await fetchrow(
        "SELECT id, client_name, api_key, is_active, rate_limit_per_hour, max_results_cap, credits_remaining, webhook_url, contact_email, password_hash, created_at FROM api_clients WHERE api_key = $1",
        api_key,
    )
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return _serialize(row)


async def verify_admin_key(api_key: str) -> dict:
    client = await verify_api_key(api_key)
    if client.get("client_name") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return client


@router.post("/api/analyze")
async def analyze(
    request: AnalyzeRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    start_time = datetime.now(timezone.utc)
    client = await verify_api_key(x_api_key)
    client_id = str(client["id"])

    limits = await get_client_limits(client_id)
    if limits["credits_remaining"] is not None and limits["credits_remaining"] <= 0:
        return JSONResponse(
            status_code=402,
            content={
                "error": "No credits remaining. Contact admin to purchase more.",
                "request_id": request.request_id,
            },
        )

    allowed = await check_rate_limit(client_id, limits["rate_limit_per_hour"])
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded. Max requests per hour reached.",
                "request_id": request.request_id,
            },
        )

    await deduct_credit(client_id)

    max_results = min(request.options.max_results, limits.get("max_results_cap", 50))

    try:
        cached = await get_cached_result(
            request.student.skills,
            request.student.preferred_roles,
            request.student.preferred_location,
            request.student.remote_preference,
        )
        if cached:
            cached["request_id"] = request.request_id
            cached["cached"] = True
            cached["processing_time_ms"] = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            log.info("cache_hit", request_id=request.request_id)
            return cached
    except Exception:
        pass

    if request.options.mode == "async":
        webhook_url = request.options.webhook_url or client.get("webhook_url")
        if not webhook_url:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "webhook_url required for async mode",
                    "request_id": request.request_id,
                },
            )

        asyncio.create_task(
            _run_async_analyze(request, client_id, max_results, start_time, webhook_url)
        )

        return {
            "request_id": request.request_id,
            "status": "processing",
            "mode": "async",
            "webhook_url_used": webhook_url,
        }

    return await _run_sync_analyze(request, client_id, max_results, start_time)


async def _run_async_analyze(request, client_id, max_results, start_time, webhook_url):
    try:
        result = await _run_sync_analyze(request, client_id, max_results, start_time)
        await deliver_webhook(
            request.request_id,
            client_id,
            webhook_url,
            "crawl_complete",
            result,
        )
    except Exception as e:
        log.error("async_analyze_failed", request_id=request.request_id, error=str(e))
        await deliver_webhook(
            request.request_id,
            client_id,
            webhook_url,
            "crawl_failed",
            {"request_id": request.request_id, "error": str(e)},
        )


async def _run_sync_analyze(request, client_id, max_results, start_time):
    session_row = await fetchrow(
        """INSERT INTO crawl_sessions (triggered_by, source_system, status)
           VALUES ($1, $2, 'running')
           RETURNING session_id""",
        request.student.user_id,
        request.source,
    )
    crawl_session_id = str(session_row["session_id"])

    await execute(
        """INSERT INTO analyze_requests (request_id, api_client_id, status, created_at, user_id_from_client)
           VALUES ($1, $2, 'processing', NOW(), $3)
           ON CONFLICT (request_id) DO NOTHING""",
        request.request_id,
        client_id,
        request.student.user_id,
    )

    analyzer = ATSAnalyzer()
    ats_signals = analyzer.analyze(request.student)
    queries = ats_signals.search_queries

    pre_count = 0
    try:
        pre_count = await fetchval(
            "SELECT COUNT(*) FROM jobs WHERE is_expired = FALSE AND freshness_score > $1",
            settings.FRESHNESS_CUTOFF,
        )
    except Exception:
        pass

    use_db_only = (
        pre_count is not None and pre_count >= settings.MIN_JOBS_FOR_CACHED_RESPONSE
    )
    log.info("inventory_check", pre_count=pre_count, use_db_only=use_db_only)

    all_jobs = []
    total_raw = 0
    sources_ok = 0
    sources_fail = 0

    if use_db_only:
        db_jobs = await fetch(
            "SELECT * FROM jobs WHERE is_expired = FALSE ORDER BY trust_score DESC LIMIT 500",
        )
        for j in db_jobs:
            try:
                ej = EnrichedJob(
                    title=j["title"],
                    company=j["company"],
                    apply_link=j["apply_link"],
                    source_platform=j["source_platform"],
                    source_url=j["source_url"],
                    location=j["location"] or "Unknown",
                    remote_status=j["remote_status"] or "unknown",
                    job_type=j["job_type"] or "unknown",
                    job_id=str(j["job_id"]),
                    crawl_session_id=crawl_session_id,
                    trust_score=j["trust_score"] or 0.0,
                    freshness_score=j["freshness_score"] or 0.0,
                    niche_score=j["niche_score"] or 0.0,
                    is_niche=j["is_niche"] or False,
                    verified=j["verified"] or False,
                    is_expired=j["is_expired"] or False,
                    description=j["description"] or "",
                    skills_required=j["skills_required"] or [],
                    paid=j["paid"],
                    stipend_inr=j["stipend_inr"],
                    posted_date=j["posted_date"],
                    deadline=j["deadline"],
                )
                all_jobs.append(ej)
            except Exception:
                continue
        total_raw = len(all_jobs)

        if pre_count is None or pre_count < 200:
            asyncio.create_task(_background_crawl_refresh(crawl_session_id, queries))
    else:
        crawl_results = await dispatcher.dispatch(crawl_session_id, queries)
        total_raw = sum(r.jobs_found for r in crawl_results)
        sources_ok = sum(1 for r in crawl_results if r.status == "complete")
        sources_fail = sum(1 for r in crawl_results if r.status == "failed")
        for result in crawl_results:
            for raw in result.jobs:
                enriched = EnrichedJob(**raw.model_dump())
                enriched.crawl_session_id = crawl_session_id
                all_jobs.append(enriched)

    deduped = simhash_duplicates(all_jobs)
    duplicates_removed = len(all_jobs) - len(deduped) if all_jobs else 0

    comp_profiler = CompanyProfiler()
    scored_jobs = []
    expired_removed = 0
    low_trust_removed = 0

    async def process_job(job):
        nonlocal expired_removed, low_trust_removed
        freshness = compute_freshness_score(job)
        if freshness == 0.0:
            expired_removed += 1
            return None
        company_profile = await comp_profiler.build_profile(
            job.company, job.company_domain or ""
        )
        trust = await compute_trust_score(job, company_profile)
        if trust < 0.3:
            low_trust_removed += 1
            return None
        niche_score, is_niche = compute_niche_score(job)
        match_score, match_reason = job_matcher.score(ats_signals, job)
        job.ats_match_score = match_score
        job.match_reason = match_reason
        return job

    tasks = [process_job(job) for job in deduped]
    results = await asyncio.gather(*tasks)
    scored_jobs = [r for r in results if r is not None]

    if scored_jobs:
        top_100 = sorted(scored_jobs, key=lambda j: j.trust_score, reverse=True)[:100]
        links_to_check = [j.apply_link for j in top_100 if j.apply_link]
        link_status = await validate_apply_links(links_to_check)

        for job in top_100:
            if job.apply_link in link_status and not link_status[job.apply_link]:
                job.trust_score = 0.0
                scored_jobs.remove(job)
                low_trust_removed += 1

    ranked = rank_jobs(scored_jobs, max_results, request.options)

    ranked = await groq_rerank(
        request.student.model_dump(),
        {
            "skill_domains": ats_signals.skill_domains,
            "normalized_skills": ats_signals.normalized_skills,
        },
        ranked,
    )

    results_list = []
    for i, job in enumerate(ranked[:max_results]):
        days_until_deadline = None
        if job.deadline:
            dl = job.deadline
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            days_until_deadline = (dl - datetime.now(timezone.utc)).days

        matched_skills = list(
            set(ats_signals.normalized_skills)
            & set(s.lower() for s in job.skills_required)
        )
        missing_skills = list(
            set(s.lower() for s in job.skills_required)
            - set(ats_signals.normalized_skills)
        )

        result = RankedJobResult(
            job_id=str(uuid.uuid4()),
            rank=i + 1,
            ats_match_score=job.ats_match_score,
            match_reason=job.match_reason,
            niche_score=job.niche_score,
            title=job.title,
            company=job.company,
            company_about=job.company_about,
            industry=job.industry,
            company_size=job.company_size,
            funding_stage=job.funding_stage,
            location=job.location,
            remote_status=job.remote_status,
            job_type=job.job_type,
            duration=job.duration,
            paid=job.paid,
            stipend_inr=job.stipend_inr,
            salary_range=job.salary_range,
            skills_required=job.skills_required,
            skills_matched=matched_skills[:10],
            skills_missing=missing_skills[:10],
            batch_eligible=job.batch_eligible,
            posted_date=job.posted_date,
            deadline=job.deadline,
            days_until_deadline=days_until_deadline,
            apply_link=job.apply_link,
            source_platform=job.source_platform,
            source_url=job.source_url,
            recruiter_name=job.recruiter_name,
            recruiter_email=job.recruiter_email,
            recruiter_linkedin=job.recruiter_linkedin,
            trust_score=job.trust_score,
            freshness_score=job.freshness_score,
            verified=job.verified,
            is_niche=job.is_niche,
            nexus_job_id=job.job_id or "",
        )
        results_list.append(result)

    processing_time = int(
        (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    )

    await execute(
        """UPDATE analyze_requests SET status = 'complete', results_count = $2,
           processing_time_ms = $3, crawl_session_id = $4::uuid, completed_at = NOW()
           WHERE request_id = $1""",
        request.request_id,
        len(results_list),
        processing_time,
        crawl_session_id,
    )

    response = AnalyzeResponse(
        request_id=request.request_id,
        status="complete",
        crawl_session_id=crawl_session_id,
        total_discovered=max(total_raw, pre_count or 0),
        total_after_filter=len(results_list),
        processing_time_ms=processing_time,
        results=results_list,
        crawl_metadata=CrawlMetadata(
            sources_crawled=sources_ok,
            sources_failed=sources_fail,
            total_raw_jobs=total_raw,
            duplicates_removed=duplicates_removed,
            expired_removed=expired_removed,
            low_trust_removed=low_trust_removed,
            final_ranked=len(results_list),
        ),
    )

    try:
        await set_cached_result(
            request.student.skills,
            request.student.preferred_roles,
            request.student.preferred_location,
            request.student.remote_preference,
            json.loads(response.model_dump_json()),
        )
    except Exception:
        pass

    return response


async def _background_crawl_refresh(session_id: str, queries: list[str]):
    try:
        log.info("background_crawl_refresh", session_id=session_id)
        await dispatcher.quick_dispatch(session_id, queries)
    except Exception as e:
        log.warning("background_crawl_failed", session_id=session_id, error=str(e))


@router.get("/api/health")
async def health():
    db_ok = redis_ok = False
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        pass
    try:
        from core.redis_client import get_client

        await get_client().ping()
        redis_ok = True
    except Exception:
        pass
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": db_ok,
        "redis": redis_ok,
    }


@router.get("/api/jobs")
async def list_jobs(
    job_type: Optional[str] = Query(None),
    remote: Optional[bool] = Query(None),
    paid: Optional[bool] = Query(None),
    skills: Optional[str] = Query(None),
    min_trust_score: Optional[float] = Query(None),
    posted_after: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_api_key(x_api_key)
    conditions = ["is_expired = FALSE"]
    params = []
    idx = 1

    if job_type:
        conditions.append(f"job_type = ${idx}")
        params.append(job_type)
        idx += 1
    if remote is not None:
        if remote:
            conditions.append("remote_status = 'remote'")
        else:
            conditions.append("remote_status IN ('onsite', 'hybrid')")
    if paid is not None:
        conditions.append(f"paid = ${idx}")
        params.append(paid)
        idx += 1
    if skills:
        for skill in skills.split(","):
            conditions.append(f"skills_required::text ILIKE ${idx}")
            params.append(f"%{skill.strip().lower()}%")
            idx += 1
    if min_trust_score is not None:
        conditions.append(f"trust_score >= ${idx}")
        params.append(min_trust_score)
        idx += 1
    if posted_after:
        conditions.append(f"posted_date >= ${idx}::timestamptz")
        params.append(posted_after)
        idx += 1

    where = " AND ".join(conditions)
    count_row = await fetchrow(f"SELECT COUNT(*) FROM jobs WHERE {where}", *params)
    total = count_row["count"] if count_row else 0

    params.extend([limit, offset])
    rows = await fetch(
        f"SELECT job_id, title, company, location, remote_status, job_type, paid, stipend_inr, trust_score, apply_link, source_platform, deadline, posted_date FROM jobs WHERE {where} ORDER BY trust_score DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params,
    )
    jobs_list = []
    for row in rows:
        jobs_list.append(
            {
                "job_id": str(row["job_id"]),
                "title": row["title"],
                "company": row["company"],
                "location": row["location"],
                "remote_status": row["remote_status"],
                "job_type": row["job_type"],
                "paid": row["paid"],
                "stipend_inr": row["stipend_inr"],
                "trust_score": row["trust_score"],
                "apply_link": row["apply_link"],
                "source_platform": row["source_platform"],
                "deadline": row["deadline"].isoformat() if row["deadline"] else None,
                "posted_date": row["posted_date"].isoformat()
                if row["posted_date"]
                else None,
            }
        )
    return {"total": total, "limit": limit, "offset": offset, "jobs": jobs_list}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, x_api_key: str = Header(..., alias="X-API-Key")):
    await verify_api_key(x_api_key)
    row = await fetchrow("SELECT * FROM jobs WHERE job_id = $1::uuid", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@router.post("/api/jobs/{job_id}/report")
async def report_job(
    job_id: str,
    reason: str = Form(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_api_key(x_api_key)
    if reason not in ("fake", "expired", "spam"):
        raise HTTPException(
            status_code=400, detail="Invalid reason. Use: fake, expired, spam"
        )
    row = await fetchrow(
        "SELECT report_count FROM jobs WHERE job_id = $1::uuid", job_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    new_count = (row["report_count"] or 0) + 1
    await execute(
        "UPDATE jobs SET report_count = $2, trust_score = GREATEST(trust_score - 0.15, 0) WHERE job_id = $1::uuid",
        job_id,
        new_count,
    )
    if new_count >= 3:
        await execute(
            "UPDATE jobs SET is_expired = TRUE WHERE job_id = $1::uuid", job_id
        )
    return {"status": "reported", "job_id": job_id, "total_reports": new_count}


@router.get("/api/stats")
async def system_stats(x_api_key: str = Header(..., alias="X-API-Key")):
    await verify_api_key(x_api_key)
    active = await fetchval("SELECT COUNT(*) FROM jobs WHERE is_expired = FALSE") or 0
    by_source = await fetch(
        "SELECT source_platform, COUNT(*) as count FROM jobs WHERE is_expired = FALSE GROUP BY source_platform ORDER BY count DESC"
    )
    avg_trust = (
        await fetchval("SELECT AVG(trust_score) FROM jobs WHERE is_expired = FALSE")
        or 0
    )
    last_crawl = await fetchrow(
        "SELECT started_at FROM crawl_sessions ORDER BY started_at DESC LIMIT 1"
    )
    added_24h = (
        await fetchval(
            "SELECT COUNT(*) FROM jobs WHERE created_at > NOW() - INTERVAL '24 hours'"
        )
        or 0
    )
    return {
        "total_active_jobs": active,
        "jobs_by_source": [
            {"source": r["source_platform"], "count": r["count"]} for r in by_source
        ],
        "average_trust_score": round(float(avg_trust), 3),
        "last_crawl_at": last_crawl["started_at"].isoformat()
        if last_crawl and last_crawl["started_at"]
        else None,
        "jobs_added_24h": added_24h,
    }


@router.post("/api/webhook/register")
async def register_webhook(
    webhook_url: str = Form(...),
    events: str = Form("crawl_complete"),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    client = await verify_api_key(x_api_key)
    await execute(
        "UPDATE api_clients SET webhook_url = $2, webhook_events = $3::jsonb WHERE id = $1::uuid",
        client["id"],
        webhook_url,
        events.split(","),
    )
    return {
        "status": "registered",
        "webhook_url": webhook_url,
        "events": events.split(","),
    }


@router.post("/api/login")
async def api_login(
    client_name: str = Form(...),
    password: str = Form(...),
):
    row = await fetchrow(
        "SELECT id, api_key, password_hash, is_active FROM api_clients WHERE client_name = $1",
        client_name,
    )
    if not row or not row["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    stored_hash = row["password_hash"]
    if stored_hash:
        import hashlib

        input_hash = hashlib.sha256(password.encode()).hexdigest()
        if input_hash != stored_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "status": "authenticated",
        "api_key": row["api_key"],
        "client_id": str(row["id"]),
    }


@router.post("/api/register")
async def api_register(
    client_name: str = Form(...),
    password: str = Form(...),
    contact_email: str = Form(""),
):
    existing = await fetchrow(
        "SELECT id FROM api_clients WHERE client_name = $1", client_name
    )
    if existing:
        raise HTTPException(status_code=400, detail="Client name already taken")
    api_key = f"nexus-{secrets.token_hex(16)}"
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    await execute(
        """INSERT INTO api_clients (client_name, api_key, password_hash, contact_email,
           credits_remaining, rate_limit_per_hour, max_results_cap)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        client_name,
        api_key,
        pw_hash,
        contact_email or None,
        settings.DEFAULT_FREE_CREDITS,
        settings.DEFAULT_FREE_RATE_LIMIT,
        10,
    )
    row = await fetchrow("SELECT id FROM api_clients WHERE api_key = $1", api_key)
    return {
        "status": "ok",
        "api_key": api_key,
        "client_id": str(row["id"]),
        "credits": settings.DEFAULT_FREE_CREDITS,
    }


@router.get("/api/user/profile")
async def user_profile(x_api_key: str = Header(..., alias="X-API-Key")):
    c = await verify_api_key(x_api_key)
    return {
        "client_id": c["id"],
        "client_name": c["client_name"],
        "api_key": c["api_key"],
        "credits_remaining": c["credits_remaining"],
        "rate_limit_per_hour": c["rate_limit_per_hour"],
        "max_results_cap": c["max_results_cap"],
        "contact_email": c.get("contact_email") or "",
        "has_password": bool(c.get("password_hash")),
    }


@router.post("/api/user/contact")
async def user_contact(
    subject: str = Form(...),
    message: str = Form(...),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    c = await verify_api_key(x_api_key)
    await execute(
        """INSERT INTO contact_requests (client_id, client_name, contact_email, subject, message, request_type)
           VALUES ($1::uuid, $2, $3, $4, $5, 'user_message')""",
        c["id"],
        c.get("client_name"),
        c.get("contact_email"),
        subject,
        message,
    )
    return {"status": "sent"}


@router.post("/api/user/regenerate-key")
async def user_regenerate_key(x_api_key: str = Header(..., alias="X-API-Key")):
    c = await verify_api_key(x_api_key)
    new_key = f"nexus-{secrets.token_hex(16)}"
    await execute(
        "UPDATE api_clients SET api_key = $2 WHERE id = $1::uuid", c["id"], new_key
    )
    return {"status": "ok", "api_key": new_key}


@router.get("/api/admin/clients")
async def admin_list_clients(x_api_key: str = Header(..., alias="X-API-Key")):
    await verify_admin_key(x_api_key)
    rows = await fetch("SELECT * FROM api_clients ORDER BY created_at DESC")
    return {"clients": [_serialize(r) for r in rows]}


@router.post("/api/admin/clients")
async def admin_create_client(
    client_name: str = Form(...),
    credits: int = Form(50),
    rate_limit: int = Form(50),
    max_results: int = Form(50),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_admin_key(x_api_key)
    existing = await fetchrow(
        "SELECT id FROM api_clients WHERE client_name = $1", client_name
    )
    if existing:
        raise HTTPException(status_code=400, detail="Client name already exists")
    api_key = f"nexus-{secrets.token_hex(16)}"
    await execute(
        """INSERT INTO api_clients (client_name, api_key, credits_remaining, rate_limit_per_hour, max_results_cap)
           VALUES ($1, $2, $3, $4, $5)""",
        client_name,
        api_key,
        credits,
        rate_limit,
        max_results,
    )
    return {"status": "created", "api_key": api_key, "client_name": client_name}


@router.delete("/api/admin/clients/{client_id}")
async def admin_delete_client(
    client_id: str, x_api_key: str = Header(..., alias="X-API-Key")
):
    await verify_admin_key(x_api_key)
    await execute(
        "DELETE FROM api_clients WHERE id = $1::uuid AND client_name != 'admin'",
        client_id,
    )
    return {"status": "deleted"}


@router.patch("/api/admin/clients/{client_id}")
async def admin_update_client(
    client_id: str,
    credits: Optional[int] = Form(None),
    rate_limit: Optional[int] = Form(None),
    max_results: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_admin_key(x_api_key)
    sets = []
    params = [client_id]
    idx = 2
    if credits is not None:
        sets.append(f"credits_remaining = ${idx}")
        params.append(credits)
        idx += 1
    if rate_limit is not None:
        sets.append(f"rate_limit_per_hour = ${idx}")
        params.append(rate_limit)
        idx += 1
    if max_results is not None:
        sets.append(f"max_results_cap = ${idx}")
        params.append(max_results)
        idx += 1
    if is_active is not None:
        sets.append(f"is_active = ${idx}")
        params.append(is_active)
        idx += 1
    if sets:
        await execute(
            f"UPDATE api_clients SET {', '.join(sets)} WHERE id = $1::uuid", *params
        )
    return {"status": "updated"}


@router.get("/api/admin/messages")
async def admin_list_messages(
    status: str = Query("pending"),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_admin_key(x_api_key)
    if status == "all":
        rows = await fetch(
            "SELECT * FROM contact_requests ORDER BY created_at DESC LIMIT 100"
        )
    else:
        rows = await fetch(
            "SELECT * FROM contact_requests WHERE status = $1 ORDER BY created_at DESC LIMIT 100",
            status,
        )
    return {"messages": [_serialize(r) for r in rows]}


@router.post("/api/admin/messages/{message_id}/resolve")
async def admin_resolve_message(
    message_id: str,
    credits: int = Form(0),
    notes: str = Form(""),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_admin_key(x_api_key)
    row = await fetchrow(
        "SELECT * FROM contact_requests WHERE id = $1::uuid", message_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    if credits > 0 and row["client_id"]:
        await execute(
            "UPDATE api_clients SET credits_remaining = credits_remaining + $2 WHERE id = $1::uuid",
            row["client_id"],
            credits,
        )
    await execute(
        "UPDATE contact_requests SET status = 'resolved', admin_notes = $2, resolved_at = NOW() WHERE id = $1::uuid",
        message_id,
        notes,
    )
    return {"status": "resolved", "credits_added": credits}


@router.post("/api/admin/crawl/trigger")
async def admin_trigger_crawl(x_api_key: str = Header(..., alias="X-API-Key")):
    await verify_admin_key(x_api_key)
    row = await fetchrow(
        "INSERT INTO crawl_sessions (triggered_by, source_system, status) VALUES ('admin_api', 'admin', 'running') RETURNING session_id",
    )
    session_id = str(row["session_id"])
    broad_queries = [
        '"intern" "2025" "apply"',
        '"fresher" "software" "intern"',
        '"python" "internship" "remote"',
        '"machine learning" "intern"',
        '"backend" "intern" "apply"',
    ]
    asyncio.create_task(dispatcher.dispatch(session_id, broad_queries))
    return {"status": "triggered", "session_id": session_id}


@router.get("/api/admin/sessions")
async def admin_list_sessions(
    limit: int = Query(20), x_api_key: str = Header(..., alias="X-API-Key")
):
    await verify_admin_key(x_api_key)
    rows = await fetch(
        "SELECT * FROM crawl_sessions ORDER BY started_at DESC LIMIT $1", limit
    )
    return {"sessions": [_serialize(r) for r in rows]}


@router.get("/api/admin/sessions/{session_id}")
async def admin_session_detail(
    session_id: str, x_api_key: str = Header(..., alias="X-API-Key")
):
    await verify_admin_key(x_api_key)
    session = await fetchrow(
        "SELECT * FROM crawl_sessions WHERE session_id = $1::uuid", session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    sources = await fetch(
        "SELECT * FROM crawl_source_logs WHERE session_id = $1::uuid ORDER BY started_at",
        session_id,
    )
    return {
        "session": _serialize(session),
        "sources": [_serialize(s) for s in sources],
    }


@router.get("/api/admin/clients/{client_id}")
async def admin_client_detail(
    client_id: str, x_api_key: str = Header(..., alias="X-API-Key")
):
    await verify_admin_key(x_api_key)
    row = await fetchrow("SELECT * FROM api_clients WHERE id = $1::uuid", client_id)
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    req_count = (
        await fetchval(
            "SELECT COUNT(*) FROM analyze_requests WHERE api_client_id = $1::uuid",
            client_id,
        )
        or 0
    )
    recent_reqs = await fetch(
        "SELECT request_id, status, results_count, created_at, processing_time_ms FROM analyze_requests WHERE api_client_id = $1::uuid ORDER BY created_at DESC LIMIT 10",
        client_id,
    )
    notes_count = (
        await fetchval(
            "SELECT COUNT(*) FROM notifications WHERE client_id = $1::uuid AND is_read = FALSE",
            client_id,
        )
        or 0
    )
    data = _serialize(row)
    data["total_requests"] = req_count
    data["recent_requests"] = [_serialize(r) for r in recent_reqs]
    data["unread_notifications"] = notes_count
    return data


@router.post("/api/admin/clients/{client_id}/message")
async def admin_send_message(
    client_id: str,
    message: str = Form(...),
    title: str = Form("New message from admin"),
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    await verify_admin_key(x_api_key)
    await execute(
        "INSERT INTO notifications (client_id, title, message) VALUES ($1::uuid, $2, $3)",
        client_id,
        title,
        message,
    )
    return {"status": "sent"}


@router.get("/api/admin/jobs-summary")
async def admin_jobs_summary(x_api_key: str = Header(..., alias="X-API-Key")):
    await verify_admin_key(x_api_key)
    total = await fetchval("SELECT COUNT(*) FROM jobs") or 0
    active = await fetchval("SELECT COUNT(*) FROM jobs WHERE is_expired = FALSE") or 0
    by_source = await fetch(
        "SELECT source_platform, COUNT(*) as cnt FROM jobs WHERE is_expired = FALSE GROUP BY source_platform ORDER BY cnt DESC"
    )
    recent = await fetch(
        "SELECT job_id, title, company, trust_score, source_platform, created_at FROM jobs WHERE is_expired = FALSE ORDER BY created_at DESC LIMIT 20"
    )
    return {
        "total": total,
        "active": active,
        "by_source": [
            {"source": r["source_platform"], "count": r["cnt"]} for r in by_source
        ],
        "recent": [_serialize(r) for r in recent],
    }


@router.get("/api/user/notifications")
async def user_notifications(x_api_key: str = Header(..., alias="X-API-Key")):
    c = await verify_api_key(x_api_key)
    rows = await fetch(
        "SELECT * FROM notifications WHERE client_id = $1::uuid ORDER BY created_at DESC LIMIT 50",
        c["id"],
    )
    return {"notifications": [_serialize(r) for r in rows]}


@router.post("/api/user/notifications/{note_id}/read")
async def mark_notification_read(
    note_id: str, x_api_key: str = Header(..., alias="X-API-Key")
):
    c = await verify_api_key(x_api_key)
    await execute(
        "UPDATE notifications SET is_read = TRUE WHERE id = $1::uuid AND client_id = $2::uuid",
        note_id,
        c["id"],
    )
    return {"status": "ok"}


@router.get("/api/user/requests")
async def user_requests(x_api_key: str = Header(..., alias="X-API-Key")):
    c = await verify_api_key(x_api_key)
    rows = await fetch(
        "SELECT * FROM contact_requests WHERE client_id = $1::uuid ORDER BY created_at DESC LIMIT 50",
        c["id"],
    )
    return {"requests": [_serialize(r) for r in rows]}
