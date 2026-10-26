import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prds.api.routes.chat import router as chat_router
from prds.api.routes.llm_models import router as llm_models_router
from prds.api.routes.llm_settings import router as llm_settings_router
from prds.api.routes.simulations import get_repo, router as simulations_router
from prds.config import get_settings, set_runtime_llm_overrides
from prds.simulation.tasks import get_tasks
from prds.kb.proxy import router as lightrag_proxy_router
from prds.kb.routes import router as kb_router
from prds.kb.settings_store import apply_default_model_runtime, load_llm_overrides

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_tasks().shutting_down = False
    settings = get_settings()
    logger.info("PRDS starting with model=%s", settings.prds_llm_model)
    repo = get_repo()
    await repo.init_db()
    await repo.interrupt_active_runs()
    overrides = await load_llm_overrides()
    if overrides:
        set_runtime_llm_overrides(overrides)
        logger.info("Loaded runtime LLM overrides (model=%s)", overrides.get("model"))
    try:
        await apply_default_model_runtime()
    except Exception as exc:
        logger.warning("Model catalog bootstrap skipped: %s", exc)
    app.state.lightrag_http = httpx.AsyncClient(timeout=120.0)
    try:
        yield
    finally:
        await get_tasks().shutdown()
        await app.state.lightrag_http.aclose()
        await repo.engine.dispose()
    logger.info("PRDS shutdown")


app = FastAPI(
    title="PRDS - Parallel Reality Decision Simulator",
    description="Multi-agent world simulation and decision path discovery",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(simulations_router, prefix="/api")
app.include_router(kb_router, prefix="/api")
app.include_router(llm_settings_router, prefix="/api")
app.include_router(llm_models_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(lightrag_proxy_router)


@app.get("/")
async def root() -> dict:
    return {"service": "prds", "docs": "/docs", "api": "/api", "lightrag_proxy": "/lightrag"}


@app.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_configured": settings.llm_configured,
        "default_agent_count": settings.prds_default_agent_count,
        "default_max_events": settings.prds_default_max_events,
        "lightrag_url": settings.prds_lightrag_url,
    }


@app.get("/api/config")
async def public_config() -> dict:
    settings = get_settings()
    # Embed URL goes through Odyssey proxy for same-origin iframe
    return {
        "llm_model": settings.prds_llm_model,
        "llm_model_analysis": settings.prds_llm_model_analysis,
        "max_concurrent_llm": settings.prds_max_concurrent_llm,
        "default_agent_count": settings.prds_default_agent_count,
        "default_max_events": settings.prds_default_max_events,
        "llm_configured": settings.llm_configured,
        "max_steps": settings.prds_kbsim_max_steps,
        "lightrag_url": settings.prds_lightrag_url,
        # LightRAG chromeless graph embed (HashRouter under WebUI)
        "lightrag_embed_path": "/lightrag/webui/index.html#/embed/graph",
    }


def run() -> None:
    import uvicorn

    uvicorn.run("prds.main:app", host="127.0.0.1", port=8000, reload=False)
