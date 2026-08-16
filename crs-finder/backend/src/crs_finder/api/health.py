import sqlite3
from pathlib import Path

import crs_inference as _crs_pkg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["health"])

_COUNTIES_GPKG = Path(_crs_pkg.__file__).parent / "data" / "counties.gpkg"


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        with sqlite3.connect(_COUNTIES_GPKG) as conn:
            conn.execute("SELECT 1 FROM counties LIMIT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return HealthResponse(status="ok")
