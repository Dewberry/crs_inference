import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

import geopandas as gpd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from shapely.geometry import mapping

import crs_inference as _crs_pkg
from crs_inference import CRSInferenceEngine, RasParser, Target
from shapely.geometry.base import BaseGeometry

router = APIRouter(tags=["inference"])

_logger = logging.getLogger(__name__)
_engine = CRSInferenceEngine()
_MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))

# HEC-RAS geometry file extensions (.g00 – .g12)
_RAS_SUFFIXES = {f".g{i:02d}" for i in range(13)}
_GEO_SUFFIXES = {".geojson", ".json", ".gpkg"}


def _parse_geometry(filename: str, data: bytes) -> BaseGeometry:
    """Dispatch to RAS or geopandas parser based on file extension."""
    suffix = Path(filename).suffix.lower()

    if suffix in _RAS_SUFFIXES:
        parser = RasParser.from_string(data.decode("utf-8", errors="replace"))
        parser.validate()
        return parser.parse()

    if suffix in _GEO_SUFFIXES:
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            # Read raw coordinates — do NOT reproject; CRS is what we're inferring
            gdf = gpd.read_file(tmp_path)
            return gdf.geometry.union_all()
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    raise ValueError(
        f"Unsupported geometry file type '{suffix}'. "
        "Expected a HEC-RAS .g## file or a .geojson / .json / .gpkg file."
    )

# Counties GeoPackage is bundled inside the crs_inference package
_COUNTIES_GPKG = Path(_crs_pkg.__file__).parent / "data" / "counties.gpkg"

_FIPS_TO_STATE: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
    "72": "PR", "78": "VI",
}


@router.get("/counties/{geoid}")
async def get_county(geoid: str) -> JSONResponse:
    """Return county name and state abbreviation for an exact 5-digit FIPS GEOID."""
    if len(geoid) != 5 or not geoid.isdigit():
        raise HTTPException(status_code=422, detail="GEOID must be exactly 5 digits.")
    with sqlite3.connect(_COUNTIES_GPKG) as conn:
        row = conn.execute(
            "SELECT GEOID, NAME, STATEFP FROM counties WHERE GEOID = ?",
            (geoid,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"County GEOID '{geoid}' not found.")
    geoid_val, name, statefp = row
    return JSONResponse({"geoid": geoid_val, "name": name, "state": _FIPS_TO_STATE.get(statefp, statefp)})


@router.post("/infer")
async def infer(
    geometry_file: UploadFile = File(..., description="HEC-RAS .g## or GeoJSON/GeoPackage geometry file"),
    target_file: UploadFile | None = File(default=None, description="Target boundary (GeoJSON or GeoPackage)"),
    county_fips: str | None = Form(default=None, description="5-digit county FIPS code"),
) -> JSONResponse:
    if target_file is None and county_fips is None:
        raise HTTPException(status_code=422, detail="Provide either target_file or county_fips.")

    geom_bytes = await geometry_file.read()
    if len(geom_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Geometry file exceeds the {_MAX_UPLOAD_BYTES // 1024 // 1024} MB limit.")
    filename = geometry_file.filename or "geometry"
    _logger.info("Inference request: file=%s size=%d target=%s", filename, len(geom_bytes), "county" if county_fips else "file")

    try:
        geometry = _parse_geometry(filename, geom_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if county_fips is not None:
        fips_list = [f.strip() for f in county_fips.split(",") if f.strip()]
        try:
            target = Target.from_county(fips_list if len(fips_list) > 1 else fips_list[0])
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not build target from FIPS '{county_fips}': {exc}") from exc
    else:
        assert target_file is not None
        target_bytes = await target_file.read()
        if len(target_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"Target file exceeds the {_MAX_UPLOAD_BYTES // 1024 // 1024} MB limit.")
        suffix = Path(target_file.filename or "target.geojson").suffix.lower() or ".geojson"
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(target_bytes)
                tmp_path = Path(tmp.name)
            target_gdf = gpd.read_file(tmp_path)
            target_geom = target_gdf.union_all()
            target_crs_str = f"EPSG:{target_gdf.crs.to_epsg()}" if target_gdf.crs else "EPSG:4326"
            target = Target.from_geometry(target_geom, crs=target_crs_str)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not parse target file: {exc}") from exc
        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)

    try:
        result = _engine.infer(geometry, target)
    except Exception as exc:
        _logger.error("Inference failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}") from exc

    _logger.info("Inference result: crs=%s confidence=%.3f method=%s", result.crs, result.confidence, result.method)

    candidates_geojson = None
    if not result.candidates.empty:
        gdf = result.candidates.copy()
        gdf["crs"] = gdf["authority"] + ":" + gdf["code"]
        gdf["is_best"] = gdf["crs"] == result.crs
        candidates_geojson = json.loads(
            gdf[["crs", "overlap_pct", "is_best", "geometry"]].to_json()
        )

    return JSONResponse({
        "crs": result.crs,
        "confidence": result.confidence,
        "method": result.method,
        "candidates": candidates_geojson,
        "target": mapping(target.geometry),
        "geometry": mapping(geometry),
    })
