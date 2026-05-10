import asyncio
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException, Query, Depends, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from core.database import fetch, fetchrow, execute
from core.logging import get_logger
from core.config import settings

router = APIRouter()

ADMIN_PASSWORD_HASH = hashlib.sha256(settings.ADMIN_API_KEY.encode()).hexdigest()
ADMIN_USERNAME = "admin"


templates = Jinja2Templates(directory="admin/templates")
log = get_logger("admin.routes")


async def _get_stats():
    stats = {}
    row = await fetchrow("SELECT COUNT(*) AS count FROM jobs")
    stats["total_jobs"] = row["count"] if row else 0
    row = await fetchrow("SELECT COUNT(*) AS count FROM jobs WHERE is_expired = FALSE")
    stats["active_jobs"] = row["count"] if row else 0
    row = await fetchrow(
        "SELECT COUNT(*) AS count FROM deleted_jobs WHERE deleted_at > NOW() - INTERVAL '24 hours'"
    )
    stats["expired_24h"] = row["count"] if row else 0
    row = await fetchrow(
        "SELECT COUNT(*) AS count FROM crawl_sessions WHERE started_at > NOW() - INTERVAL '24 hours'"
    )
    stats["crawls_today"] = row["count"] if row else 0
    row = await fetchrow(
        "SELECT started_at, status FROM crawl_sessions ORDER BY started_at DESC LIMIT 1"
    )
    stats["last_crawl_at"] = (
        row["started_at"].strftime("%Y-%m-%d %H:%M:%S")
        if row and row["started_at"]
        else "Never"
    )
    stats["last_crawl_status"] = row["status"] if row else "N/A"
    row = await fetchrow("SELECT COUNT(*) AS count FROM deleted_jobs")
    stats["total_deleted"] = row["count"] if row else 0
    row = await fetchrow("SELECT COUNT(*) AS count FROM recruiter_intelligence")
    stats["recruiter_count"] = row["count"] if row else 0
    row = await fetchrow(
        "SELECT COUNT(*) AS count FROM contact_requests WHERE status = 'pending'"
    )
    stats["pending_requests"] = row["count"] if row else 0
    row = await fetchrow("SELECT COUNT(*) AS count FROM api_clients")
    stats["total_clients"] = row["count"] if row else 0
    row = await fetchrow(
        "SELECT COUNT(*) AS count FROM crawler_sources WHERE enabled = TRUE"
    )
    stats["active_sources"] = row["count"] if row else 0
    row = await fetchrow("SELECT COUNT(*) FROM crawler_sources WHERE enabled = FALSE")
    stats["disabled_sources"] = row["count"] if row else 0
    return stats


@router.get("/admin")
async def dashboard(request: Request):
    stats = await _get_stats()
    pending = await fetch(
        "SELECT id, client_name, subject, created_at FROM contact_requests WHERE status = 'pending' ORDER BY created_at DESC LIMIT 10"
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "pending_requests": pending},
    )


@router.get("/admin/crawls")
async def crawls(request: Request, page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    rows = await fetch(
        """SELECT session_id, triggered_by, started_at, completed_at,
                  total_sources, sources_succeeded, sources_failed,
                  total_jobs_found, status
           FROM crawl_sessions ORDER BY started_at DESC LIMIT $1 OFFSET $2""",
        per_page,
        offset,
    )
    row = await fetchrow("SELECT COUNT(*) FROM crawl_sessions")
    total = row["count"] if row else 0
    sessions = []
    for r in rows:
        total_src = r["total_sources"] or (r["sources_succeeded"] or 0) + (
            r["sources_failed"] or 0
        )
        sessions.append(
            {
                "session_id": str(r["session_id"])[:8] + "...",
                "session_id_full": str(r["session_id"]),
                "triggered_by": r["triggered_by"],
                "started_at": r["started_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["started_at"]
                else "",
                "duration": _duration_str(r["started_at"], r["completed_at"]),
                "sources_succeeded": r["sources_succeeded"] or 0,
                "sources_failed": r["sources_failed"] or 0,
                "sources_total": total_src,
                "total_jobs_found": r["total_jobs_found"] or 0,
                "status": r["status"],
                "session_id_raw": str(r["session_id"]),
            }
        )
    return templates.TemplateResponse(
        "crawls.html",
        {
            "request": request,
            "sessions": sessions,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/admin/crawls/{session_id}")
async def crawl_detail(request: Request, session_id: str):
    session = await fetchrow(
        "SELECT * FROM crawl_sessions WHERE session_id = $1::uuid", session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    sources = await fetch(
        "SELECT * FROM crawl_source_logs WHERE session_id = $1::uuid ORDER BY started_at",
        session_id,
    )
    source_list = []
    for s in sources:
        source_list.append(
            {
                "source_name": s["source_name"],
                "pages_crawled": s["pages_crawled"],
                "jobs_found": s["jobs_found"],
                "jobs_rejected": s["jobs_rejected"],
                "error_count": s["error_count"],
                "duration": _duration_str(s["started_at"], s["completed_at"]),
                "status": s["status"],
            }
        )
    return templates.TemplateResponse(
        "crawl_detail.html",
        {"request": request, "session": session, "sources": source_list},
    )


@router.get("/admin/crawl/live")
async def crawl_live_index(request: Request):
    running = await fetch(
        "SELECT session_id, started_at, total_jobs_found, total_sources, status FROM crawl_sessions WHERE status = 'running' ORDER BY started_at DESC LIMIT 5"
    )
    recent = await fetch(
        "SELECT session_id, started_at, total_jobs_found, status FROM crawl_sessions ORDER BY started_at DESC LIMIT 10"
    )
    return templates.TemplateResponse(
        "crawl_live_index.html",
        {
            "request": request,
            "running": running,
            "recent": recent,
        },
    )


@router.get("/admin/crawl/live/{session_id}")
async def crawl_live(request: Request, session_id: str):
    session = await fetchrow(
        "SELECT * FROM crawl_sessions WHERE session_id = $1::uuid", session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Not found")
    sources = await fetch(
        "SELECT * FROM crawl_source_logs WHERE session_id = $1::uuid ORDER BY started_at",
        session_id,
    )
    running = sum(1 for s in sources if s["status"] == "running")
    done = sum(1 for s in sources if s["status"] == "complete")
    failed = sum(1 for s in sources if s["status"] == "failed")
    total_found = sum(s["jobs_found"] or 0 for s in sources)

    source_list = []
    for s in sources:
        source_list.append(
            {
                "source_name": s["source_name"],
                "status": s["status"],
                "jobs_found": s["jobs_found"] or 0,
                "error_count": s["error_count"] or 0,
                "duration": _duration_str(s["started_at"], s["completed_at"]),
            }
        )

    is_done = session["status"] in ("complete", "failed", "partial")

    return templates.TemplateResponse(
        "crawl_live.html",
        {
            "request": request,
            "session": session,
            "sources": source_list,
            "running": running,
            "done": done,
            "failed": failed,
            "total_found": total_found,
            "is_done": is_done,
        },
    )


@router.get("/admin/sources")
async def source_health(request: Request):
    rows = await fetch("SELECT * FROM crawler_sources ORDER BY source_name")
    sources = []
    for r in rows:
        is_failing = (r["failure_count_24h"] or 0) > 3
        sources.append(
            {
                "source_name": r["source_name"],
                "enabled": r["enabled"],
                "last_success_at": r["last_success_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["last_success_at"]
                else "Never",
                "failure_count_24h": r["failure_count_24h"] or 0,
                "success_count_24h": r["success_count_24h"] or 0,
                "avg_jobs_per_crawl": round(r["avg_jobs_per_crawl"] or 0, 1),
                "avg_latency_ms": r["avg_latency_ms"] or 0,
                "notes": r["notes"] or "",
                "is_failing": is_failing,
            }
        )
    return templates.TemplateResponse(
        "sources.html", {"request": request, "sources": sources}
    )


@router.post("/admin/sources/{source_name}/toggle")
async def toggle_source(source_name: str):
    row = await fetchrow(
        "SELECT enabled FROM crawler_sources WHERE source_name = $1", source_name
    )
    if not row:
        raise HTTPException(status_code=404, detail="Source not found")
    await execute(
        "UPDATE crawler_sources SET enabled = NOT enabled WHERE source_name = $1",
        source_name,
    )
    return RedirectResponse(url="/admin/sources", status_code=303)


@router.get("/admin/jobs")
async def jobs(
    request: Request,
    filter: str = "all",
    search: str = "",
    page: int = 1,
    per_page: int = 50,
):
    conditions = ["is_expired = FALSE"]
    params = []
    idx = 1
    if filter == "internship":
        conditions.append(f"job_type = ${idx}")
        params.append("internship")
        idx += 1
    elif filter == "fulltime":
        conditions.append(f"job_type = ${idx}")
        params.append("fulltime")
        idx += 1
    elif filter == "remote":
        conditions.append(f"remote_status = ${idx}")
        params.append("remote")
        idx += 1
    elif filter == "paid":
        conditions.append(f"paid = ${idx}")
        params.append(True)
        idx += 1
    elif filter == "unpaid":
        conditions.append(f"paid = ${idx}")
        params.append(False)
        idx += 1
    elif filter == "niche":
        conditions.append("is_niche = TRUE")
    elif filter == "reported":
        conditions.append("report_count > 0")
    if search:
        conditions.append(
            f"(title ILIKE ${idx} OR company ILIKE ${idx} OR description ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    count_params = params[:]
    row = await fetchrow(f"SELECT COUNT(*) FROM jobs WHERE {where}", *count_params)
    total = row["count"] if row else 0

    params.extend([per_page, offset])
    rows = await fetch(
        f"SELECT * FROM jobs WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params,
    )
    row_all = await fetchrow("SELECT COUNT(*) FROM jobs WHERE is_expired = FALSE")
    total_all = row_all["count"] if row_all else 0

    job_list = []
    for r in rows:
        job_list.append(
            {
                "job_id": str(r["job_id"]),
                "title": r["title"],
                "company": r["company"],
                "job_type": r["job_type"],
                "paid": r["paid"],
                "deadline": r["deadline"].strftime("%Y-%m-%d") if r["deadline"] else "",
                "trust_score": r["trust_score"],
                "location": r["location"] or "",
                "report_count": r["report_count"] or 0,
            }
        )

    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "jobs": job_list,
            "filter": filter,
            "search": search,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_all": total_all,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/admin/jobs/search")
async def job_search(request: Request, q: str = "", page: int = 1, per_page: int = 50):
    results = []
    total = 0
    if q:
        offset = (page - 1) * per_page
        row = await fetchrow(
            "SELECT COUNT(*) FROM jobs WHERE is_expired = FALSE AND (title ILIKE $1 OR company ILIKE $1 OR description ILIKE $1)",
            f"%{q}%",
        )
        total = row["count"] if row else 0
        rows = await fetch(
            "SELECT * FROM jobs WHERE is_expired = FALSE AND (title ILIKE $1 OR company ILIKE $1 OR description ILIKE $1) ORDER BY trust_score DESC LIMIT $2 OFFSET $3",
            f"%{q}%",
            per_page,
            offset,
        )
        for r in rows:
            results.append(
                {
                    "job_id": str(r["job_id"]),
                    "title": r["title"],
                    "company": r["company"],
                    "location": r["location"] or "",
                    "trust_score": r["trust_score"],
                    "deadline": r["deadline"].strftime("%Y-%m-%d")
                    if r["deadline"]
                    else "",
                }
            )
    return templates.TemplateResponse(
        "job_search.html",
        {
            "request": request,
            "results": results,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/admin/jobs/{job_id}")
async def job_detail(request: Request, job_id: str):
    job = await fetchrow("SELECT * FROM jobs WHERE job_id = $1::uuid", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    fields = {k: str(v) if v is not None else "" for k, v in dict(job).items()}
    return templates.TemplateResponse(
        "job_detail.html", {"request": request, "job": fields}
    )


@router.post("/admin/jobs/{job_id}/expire")
async def expire_job(job_id: str):
    job = await fetchrow("SELECT * FROM jobs WHERE job_id = $1::uuid", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await execute(
        """INSERT INTO deleted_jobs (job_id, title, company, location, remote_status, job_type, paid, stipend_inr,
           skills_required, apply_link, source_platform, posted_date, original_deadline, deleted_reason)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,'manual')""",
        job_id,
        job["title"],
        job["company"],
        job["location"],
        job["remote_status"],
        job["job_type"],
        job["paid"],
        job["stipend_inr"],
        job["skills_required"] or [],
        job["apply_link"],
        job["source_platform"],
        job["posted_date"],
        job["deadline"],
    )
    await execute("DELETE FROM jobs WHERE job_id = $1::uuid", job_id)
    return RedirectResponse(url="/admin/jobs", status_code=303)


@router.get("/admin/deletions")
async def deletions(
    request: Request, reason: str = "all", page: int = 1, per_page: int = 50
):
    conditions = []
    params = []
    idx = 1
    if reason != "all":
        conditions.append(f"deleted_reason = ${idx}")
        params.append(reason)
        idx += 1
    where = " AND ".join(conditions) if conditions else "TRUE"
    offset = (page - 1) * per_page
    count_params = params[:]
    row = await fetchrow(
        f"SELECT COUNT(*) FROM deleted_jobs WHERE {where}", *count_params
    )
    total = row["count"] if row else 0
    params.extend([per_page, offset])
    rows = await fetch(
        f"SELECT * FROM deleted_jobs WHERE {where} ORDER BY deleted_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params,
    )
    deletion_list = []
    for r in rows:
        deletion_list.append(
            {
                "job_id": str(r["job_id"])[:8] + "...",
                "title": r["title"] or "Unknown",
                "company": r["company"] or "Unknown",
                "deleted_at": r["deleted_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["deleted_at"]
                else "",
                "deleted_reason": r["deleted_reason"] or "",
                "original_deadline": r["original_deadline"].strftime("%Y-%m-%d")
                if r["original_deadline"]
                else "-",
            }
        )
    return templates.TemplateResponse(
        "deletions.html",
        {
            "request": request,
            "deletions": deletion_list,
            "reason": reason,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/admin/recruiters")
async def recruiters(request: Request, page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    rows = await fetch(
        "SELECT * FROM recruiter_intelligence ORDER BY extracted_at DESC LIMIT $1 OFFSET $2",
        per_page,
        offset,
    )
    row = await fetchrow("SELECT COUNT(*) FROM recruiter_intelligence")
    total = row["count"] if row else 0
    recruiter_list = []
    for r in rows:
        recruiter_list.append(
            {
                "company_domain": r["company_domain"],
                "recruiter_name": r["recruiter_name"] or "-",
                "recruiter_email": r["recruiter_email"] or "-",
                "recruiter_linkedin": r["recruiter_linkedin"] or "-",
                "email_verified": "YES" if r["email_verified"] else "NO",
            }
        )
    return templates.TemplateResponse(
        "recruiters.html",
        {
            "request": request,
            "recruiters": recruiter_list,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.get("/admin/clients")
async def clients(request: Request):
    rows = await fetch("SELECT * FROM api_clients ORDER BY created_at DESC")
    client_list = []
    for r in rows:
        client_list.append(
            {
                "id": str(r["id"]),
                "client_name": r["client_name"],
                "api_key": str(r["api_key"])[:12] + "...",
                "is_active": r["is_active"],
                "rate_limit_per_hour": r["rate_limit_per_hour"],
                "max_results_cap": r["max_results_cap"],
                "credits_remaining": r["credits_remaining"],
                "webhook_url": r["webhook_url"] or "",
                "contact_email": r["contact_email"] or "",
                "last_used_at": r["last_used_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["last_used_at"]
                else "Never",
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["created_at"]
                else "",
            }
        )
    return templates.TemplateResponse(
        "clients.html", {"request": request, "clients": client_list}
    )


@router.post("/admin/clients/create")
async def create_client(
    client_name: str = Form(...),
    rate_limit: int = Form(50),
    max_results: int = Form(50),
    credits: int = Form(50),
    webhook_url: str = Form(""),
    contact_email: str = Form(""),
):
    api_key = f"nexus-{secrets.token_hex(16)}"
    await execute(
        """INSERT INTO api_clients (client_name, api_key, rate_limit_per_hour, max_results_cap, credits_remaining, webhook_url, contact_email)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        client_name,
        api_key,
        rate_limit,
        max_results,
        credits,
        webhook_url or None,
        contact_email or None,
    )
    return RedirectResponse(url="/admin/clients", status_code=303)


@router.post("/admin/clients/{client_id}/update")
async def update_client(
    client_id: str,
    rate_limit: int = Form(...),
    max_results: int = Form(...),
    credits: int = Form(...),
    is_active: str = Form("off"),
):
    active = is_active == "on"
    await execute(
        """UPDATE api_clients SET rate_limit_per_hour = $2, max_results_cap = $3,
           credits_remaining = $4, is_active = $5 WHERE id = $1::uuid""",
        client_id,
        rate_limit,
        max_results,
        credits,
        active,
    )
    return RedirectResponse(url="/admin/clients", status_code=303)


@router.post("/admin/clients/{client_id}/delete")
async def delete_client(client_id: str):
    await execute("DELETE FROM api_clients WHERE id = $1::uuid", client_id)
    return RedirectResponse(url="/admin/clients", status_code=303)


@router.get("/admin/webhooks")
async def webhook_log(request: Request, page: int = 1, per_page: int = 50):
    offset = (page - 1) * per_page
    rows = await fetch(
        "SELECT w.*, c.client_name FROM webhook_deliveries w LEFT JOIN api_clients c ON w.client_id = c.id ORDER BY w.delivered_at DESC LIMIT $1 OFFSET $2",
        per_page,
        offset,
    )
    row = await fetchrow("SELECT COUNT(*) FROM webhook_deliveries")
    total = row["count"] if row else 0
    deliveries = []
    for r in rows:
        deliveries.append(
            {
                "id": str(r["id"])[:8] + "...",
                "request_id": r["request_id"] or "",
                "client_name": r["client_name"] or "Unknown",
                "webhook_url": r["webhook_url"] or "",
                "event_type": r["event_type"] or "",
                "http_status": r["http_status"],
                "retry_count": r["retry_count"],
                "delivered_at": r["delivered_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["delivered_at"]
                else "",
            }
        )
    return templates.TemplateResponse(
        "webhooks.html",
        {
            "request": request,
            "deliveries": deliveries,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.post("/admin/webhooks/{delivery_id}/retry")
async def retry_webhook(delivery_id: str):
    row = await fetchrow(
        "SELECT * FROM webhook_deliveries WHERE id = $1::uuid", delivery_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    from intelligence.webhook_delivery import deliver_webhook
    from core.database import fetchrow as fr

    client = await fr("SELECT * FROM api_clients WHERE id = $1::uuid", row["client_id"])
    if client:
        await deliver_webhook(
            row["request_id"] or "",
            str(row["client_id"]),
            row["webhook_url"] or client["webhook_url"] or "",
            row["event_type"] or "retry",
            {"status": "retry", "request_id": row["request_id"]},
        )
    return RedirectResponse(url="/admin/webhooks", status_code=303)


@router.get("/admin/contact")
async def contact_requests(
    request: Request, status: str = "all", page: int = 1, per_page: int = 50
):
    conditions = []
    params = []
    idx = 1
    if status != "all":
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    where = " AND ".join(conditions) if conditions else "TRUE"
    offset = (page - 1) * per_page
    count_params = params[:]
    row = await fetchrow(
        f"SELECT COUNT(*) FROM contact_requests WHERE {where}", *count_params
    )
    total = row["count"] if row else 0
    params.extend([per_page, offset])
    rows = await fetch(
        f"SELECT * FROM contact_requests WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params,
    )
    requests_list = []
    for r in rows:
        requests_list.append(
            {
                "id": str(r["id"]),
                "client_name": r["client_name"] or "",
                "contact_email": r["contact_email"] or "",
                "subject": r["subject"] or "",
                "message": (r["message"] or "")[:200],
                "request_type": r["request_type"],
                "new_limit_requested": r["new_limit_requested"],
                "status": r["status"],
                "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                if r["created_at"]
                else "",
            }
        )
    return templates.TemplateResponse(
        "contact_requests.html",
        {
            "request": request,
            "requests": requests_list,
            "status": status,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@router.post("/admin/contact/{request_id}/resolve")
async def resolve_contact(
    request_id: str, credits: int = Form(0), admin_notes: str = Form("")
):
    row = await fetchrow(
        "SELECT * FROM contact_requests WHERE id = $1::uuid", request_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if credits > 0 and row["client_id"]:
        await execute(
            "UPDATE api_clients SET credits_remaining = credits_remaining + $2 WHERE id = $1::uuid",
            row["client_id"],
            credits,
        )
    await execute(
        "UPDATE contact_requests SET status = 'resolved', admin_notes = $2, resolved_at = NOW() WHERE id = $1::uuid",
        request_id,
        admin_notes,
    )
    return RedirectResponse(url="/admin/contact", status_code=303)


@router.get("/admin/requests")
async def request_manager(request: Request, page: int = 1, per_page: int = 50):
    return await contact_requests(request, "all", page, per_page)


@router.post("/admin/crawl/trigger")
async def trigger_crawl():
    row = await fetchrow(
        "INSERT INTO crawl_sessions (triggered_by, source_system, status) VALUES ('manual_admin', 'admin', 'running') RETURNING session_id",
    )
    session_id = str(row["session_id"])
    from crawlers.dispatcher import dispatcher

    year_str = str(datetime.now(timezone.utc).year)
    broad_queries = [
        f'"intern" "{year_str}" "apply"',
        '"fresher" "software" "intern"',
        '"python" "internship" "remote"',
        '"machine learning" "intern"',
        '"backend" "intern" "apply"',
    ]
    asyncio.create_task(dispatcher.dispatch(session_id, broad_queries))
    return RedirectResponse(url=f"/admin/crawl/live/{session_id}", status_code=303)


@router.get("/contact")
async def contact_page(request: Request, submitted: bool = False):
    return templates.TemplateResponse(
        "contact_submit.html", {"request": request, "submitted": submitted}
    )


@router.post("/contact")
async def contact_submit(
    request: Request,
    client_name: str = Form(...),
    contact_email: str = Form(...),
    subject: str = Form(...),
    request_type: str = Form("credit_increase"),
    new_limit: int = Form(0),
    message: str = Form(...),
):
    try:
        client = await fetchrow(
            "SELECT id FROM api_clients WHERE client_name = $1 OR contact_email = $2",
            client_name,
            contact_email,
        )
        client_id = str(client["id"]) if client else None
        await execute(
            """INSERT INTO contact_requests (client_id, client_name, contact_email, subject, message, request_type, new_limit_requested)
               VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)""",
            client_id,
            client_name,
            contact_email,
            subject,
            message,
            request_type,
            new_limit if new_limit > 0 else None,
        )
        return templates.TemplateResponse(
            "contact_submit.html", {"request": request, "submitted": True}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "contact_submit.html", {"request": request, "error": str(e)}
        )


def _duration_str(start, end) -> str:
    if not start or not end:
        return "-"
    delta = (end - start).total_seconds()
    return f"{delta:.0f}s"
