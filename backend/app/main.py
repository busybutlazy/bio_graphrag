from fastapi import FastAPI

from app.api.routes_curation import router as curation_router
from app.api.routes_health import router as health_router
from app.api.routes_nodes import router as nodes_router

app = FastAPI(title="Biology GraphRAG Tutor")
app.include_router(health_router)
app.include_router(nodes_router)
app.include_router(curation_router)
