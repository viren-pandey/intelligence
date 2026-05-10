import os
import hashlib
import base64
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from core.database import init_db_pool, close_db_pool, get_pool
from core.redis_client import init_redis, close_redis
from core.logging import setup_logging, get_logger
from core.config import settings
from api.routes import router as api_router
from admin.routes import router as admin_router

ADMIN_PASSWORD_HASH = hashlib.sha256(settings.ADMIN_API_KEY.encode()).hexdigest()
ADMIN_USERNAME = "admin"


async def run_migrations():
    log = get_logger("migrations")
    migration_dir = os.path.join(os.path.dirname(__file__), "migrations")
    if not os.path.isdir(migration_dir):
        log.warning("migrations directory not found")
        return
    files = sorted(f for f in os.listdir(migration_dir) if f.endswith(".sql"))
    if not files:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        for filename in files:
            filepath = os.path.join(migration_dir, filename)
            log.info("running_migration", file=filename)
            try:
                with open(filepath, "r") as f:
                    sql = f.read()
                await conn.execute(sql)
                log.info("migration_complete", file=filename)
            except Exception as e:
                if "already exists" in str(e) or "duplicate" in str(e).lower():
                    log.info(
                        "migration_skipped", file=filename, reason="already applied"
                    )
                else:
                    log.warning("migration_warning", file=filename, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db_pool()
    await run_migrations()
    await init_redis()
    yield
    await close_db_pool()
    await close_redis()


app = FastAPI(
    title="NEXUS",
    description="Intelligent Recruitment Middleware",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/admin/") or request.url.path == "/admin":
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                username, password = decoded.split(":", 1)
                pw_hash = hashlib.sha256(password.encode()).hexdigest()
                if username == ADMIN_USERNAME and pw_hash == ADMIN_PASSWORD_HASH:
                    return await call_next(request)
            except Exception:
                pass

        return Response(
            content="<h1>NEXUS Admin</h1><p>Authentication required.</p>",
            media_type="text/html",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="NEXUS Admin"'},
        )

    return await call_next(request)


frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static/frontend", StaticFiles(directory=frontend_dir), name="frontend")

    @app.get("/")
    async def serve_frontend():
        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return Response(content=f.read(), media_type="text/html")
        return Response(content="Frontend not found", media_type="text/plain")


if os.path.isdir(frontend_dir):
    from fastapi.responses import HTMLResponse

    @app.get("/admin-panel")
    async def serve_admin_panel():
        path = os.path.join(frontend_dir, "admin.html")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return Response("Not found", status_code=404)

    @app.get("/playground")
    async def serve_playground():
        path = os.path.join(frontend_dir, "playground.html")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return Response("Not found", status_code=404)


app.include_router(api_router)
app.include_router(admin_router)
