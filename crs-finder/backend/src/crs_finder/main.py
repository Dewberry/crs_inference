import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crs_finder.api.health import router as health_router
from crs_finder.api.infer import router as infer_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="CRS Finder",
    version="0.1.0",
    description="Identify the CRS that best places a geometry into a target dataset.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ALLOWED_ORIGINS: comma-separated list of origins. Defaults to Vite dev server.
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(infer_router, prefix="/api")
