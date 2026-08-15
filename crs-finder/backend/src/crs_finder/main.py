from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crs_finder.api.health import router as health_router
from crs_finder.api.infer import router as infer_router

app = FastAPI(
    title="CRS Finder",
    version="0.1.0",
    description="Identify the CRS that best places a geometry into a target dataset.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Allow the Vite dev server to reach the API during local development.
# In production the Nginx proxy handles routing so CORS is not needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(infer_router, prefix="/api")
