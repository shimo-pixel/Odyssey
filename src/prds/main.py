import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from prds.api.routes.simulations import get_repo, router as simulations_router
from prds.config import get_settings
from prds.graph.neo4j_store import get_neo4j_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

NO_CACHE = "no-cache, no-store, must-revalidate"


class DevNoCacheMiddleware(BaseHTTPMiddleware):
    """Prevent 304 stale bundles while iterating on static frontend assets."""

    _SKIP = frozenset({b"if-none-match", b"if-modified-since"})

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            request.scope["headers"] = [
                (name, value)
                for name, value in request.scope["headers"]
                if name.lower() not in self._SKIP
            ]
        response = await call_next(request)
        if path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = NO_CACHE
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("PRDS starting with model=%s", settings.prds_llm_model)
    repo = get_repo()
    await repo.init_db()
    yield
    logger.info("PRDS shutdown")


app = FastAPI(
    title="PRDS - Parallel Reality Decision Simulator",
    description="Multi-agent world simulation and decision path discovery",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(DevNoCacheMiddleware)

app.include_router(simulations_router)


@app.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "default_agent_count": settings.prds_default_agent_count,
        "graphrag_enabled": settings.prds_use_graphrag,
        "neo4j_configured": settings.neo4j_enabled,
        "neo4j_connected": get_neo4j_store().verify() if settings.neo4j_enabled else False,
    }


@app.get("/domains")
async def list_domains() -> dict:
    from prds.domains.registry import get_domain_profile, list_domain_profiles

    profiles = []
    for item in list_domain_profiles():
        profile = get_domain_profile(item["id"])
        profiles.append(
            {
                **item,
                "default_resources": profile.default_resources,
                "default_success_metrics": profile.default_success_metrics,
                "default_market_info": profile.default_market_info,
            }
        )
    return {"domains": profiles}


@app.get("/config")
async def public_config() -> dict:
    settings = get_settings()
    return {
        "llm_model": settings.prds_llm_model,
        "llm_model_analysis": settings.prds_llm_model_analysis,
        "max_concurrent_llm": settings.prds_max_concurrent_llm,
        "default_agent_count": settings.prds_default_agent_count,
        "default_periods": settings.prds_default_periods,
        "checkpoint_interval": settings.prds_checkpoint_interval,
        "llm_configured": settings.llm_configured,
        "graphrag_enabled": settings.prds_use_graphrag,
        "neo4j_configured": settings.neo4j_enabled,
    }


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def ui() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": NO_CACHE, "Pragma": "no-cache", "Expires": "0"},
        )


def run() -> None:
    import uvicorn

    uvicorn.run("prds.main:app", host="0.0.0.0", port=8000, reload=True)
