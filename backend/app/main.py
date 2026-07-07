from fastapi import FastAPI

from app.api.routes_health import router as health_router

app = FastAPI(title="Biology GraphRAG Tutor")
app.include_router(health_router)
