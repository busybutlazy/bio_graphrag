from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_curation import router as curation_router
from app.api.routes_eval import router as eval_router
from app.api.routes_health import router as health_router
from app.api.routes_library import router as library_router
from app.api.routes_nodes import router as nodes_router
from app.api.routes_query import router as query_router

app = FastAPI(title="Biology GraphRAG Tutor")
app.include_router(health_router)
app.include_router(nodes_router)
app.include_router(query_router)
app.include_router(library_router)
app.include_router(curation_router)
app.include_router(eval_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


# Static demo UI (本草 HONZŌ styling over the real API). Mounted last so it only
# catches paths the API routers didn't claim.
_frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
if _frontend_dir.is_dir():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="app")
