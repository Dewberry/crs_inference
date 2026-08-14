"""Batch CRS inference for HEC-RAS geometry files staged in S3."""

import concurrent.futures
import glob
import json
import logging
import os
import time
import traceback
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psutil

from crs_inference import CRSInferenceEngine, RasParser, Target
from crs_inference.loaders.s3 import get_json_s3, search_s3, split_uri
from ops.db import Database

logging.basicConfig(
    filename="inference.log",
    filemode="a",
    format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
warnings.filterwarnings("ignore", category=RuntimeWarning, module="shapely")

logger = logging.getLogger(__name__)

# Configure these for each production run.
CSV_PATHS: list[str] = []

_engine = CRSInferenceEngine()
_target_cache: dict[str, Target] = {}


def _get_target(counties: list[str]) -> Target:
    """Return a cached Target for the given county list."""
    key = json.dumps(sorted(counties))
    if key not in _target_cache:
        _target_cache[key] = Target.from_county(counties if len(counties) > 1 else counties[0])
    return _target_cache[key]


def load_models_from_csv(csv_path: str, limit: int | None = None, db: Database | None = None) -> list[tuple[str, str]]:
    """Load (geometry_uri, county_json) pairs from a ras_bundles CSV file."""
    path = Path(csv_path)
    logger.info(f"Loading models from CSV: {path}")
    df = pd.read_csv(path, dtype=str)
    models = []
    for _, row in df.iterrows():
        if limit is not None and len(models) >= limit:
            break
        destination_prefix = row["destination_prefix"].rstrip("/") + "/"
        counties = [f.strip() for f in str(row["co_fips"]).split(",") if f.strip()]
        try:
            geometry_keys = search_s3(destination_prefix, r"\.g\d\d$")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not search {destination_prefix}: {e}")
            if db:
                db.log_no_geometry(destination_prefix, str(path), reason=str(e))
            continue
        if not geometry_keys:
            logger.warning(f"No geometry file found at {destination_prefix}")
            if db:
                db.log_no_geometry(destination_prefix, str(path))
            continue
        bucket, _ = split_uri(destination_prefix)
        geometry_uri = f"s3://{bucket}/{min(geometry_keys)}"
        models.append((geometry_uri, json.dumps(counties)))
    logger.info(f"Loaded {len(models)} models from {path.name}")
    return models

def _process_meta(meta_uri: str) -> tuple[str | None, str | None]:
    """Extract geometry URI and county from a MIP metadata file."""
    metadata = get_json_s3(meta_uri)
    counties = metadata.get("county")
    root = meta_uri.replace("mip_package_geolocation_metadata.json", "")
    geometry_keys = search_s3(root, r"\.g\d\d$")
    if not geometry_keys:
        return None, None
    bucket, _ = split_uri(meta_uri)
    geometry_uri = f"s3://{bucket}/{min(geometry_keys)}"
    return geometry_uri, json.dumps(counties)


def process_model(geom_uri: str, counties: list[str], db: Database) -> None:
    """Download, validate, and infer CRS for one model, then write results."""
    logger.info(f"Processing {geom_uri}")
    parser = RasParser.from_s3(geom_uri)
    parser.validate()
    target = _get_target(counties)
    result = _engine.infer(parser.parse(), target)
    db.log_crs(geom_uri, result.crs)
    if result.candidates is not None and len(result.candidates):
        candidates = result.candidates.copy()
        candidates["uri"] = geom_uri
        os.makedirs("runner_ups_tmp", exist_ok=True)
        candidates.to_file(f"runner_ups_tmp/runner_ups_{os.getpid()}.gpkg", mode="a")


def process_runner(geom_uri: str, counties: list[str], db: Database) -> str:
    """Run process_model with error handling and status logging."""
    try:
        db.log_status(geom_uri, "Processing")
        t1 = time.perf_counter()
        process_model(geom_uri, counties, db)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error on {geom_uri}")
        db.log_status(geom_uri, "Failure", str(e), traceback.format_exc())
    else:
        db.log_status(geom_uri, "Success")
    t2 = time.perf_counter()
    logger.info(f"finished {geom_uri} in {round(t2 - t1, 2)}s")
    logger.info(f"{round(psutil.virtual_memory()[2], 2)}% memory used")
    return geom_uri


def merge_runner_ups() -> None:
    """Merge per-worker runner_ups temp files into runner_ups.gpkg."""
    temp_files = glob.glob("runner_ups_tmp/runner_ups_*.gpkg")
    if not temp_files:
        return
    gdfs = []
    for f in temp_files:
        try:
            gdfs.append(gpd.read_file(f))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not read temp file {f}: {e}")
    if gdfs:
        merged = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)
        merged.to_file("runner_ups.gpkg", mode="a")
        logger.info(f"Merged {len(temp_files)} temp files ({len(merged)} rows)")
    for f in temp_files:
        os.remove(f)
    try:
        os.rmdir("runner_ups_tmp")
    except OSError:
        pass


def smoke_test(n: int = 3) -> None:
    """Run inference on a small sample to verify the pipeline end-to-end."""
    db_path = Path("smoke_test.db")
    runner_ups_path = "smoke_test_runner_ups.gpkg"
    print(f"=== Smoke test: {n} models ===")
    models: list = []
    db = Database(db_path)
    for csv_path in CSV_PATHS:
        remaining = n - len(models)
        models.extend(load_models_from_csv(csv_path, limit=remaining, db=db))
        if len(models) >= n:
            break
    models = models[:n]
    if not models:
        print("No models found — check CSV_PATHS")
        return
    db.log_models(models)
    for i, (geom_uri, counties) in enumerate(db.models, 1):
        print(f"\n[{i}/{n}] {geom_uri}")
        parser = RasParser.from_s3(geom_uri)
        parser.validate()
        print(f"  reaches  : {len(parser.reaches)}")
        target = _get_target(counties)
        result = _engine.infer(parser.parse(), target)
        print(f"  result   : {result.crs}  confidence={result.confidence:.3f}")
        db.log_crs(geom_uri, result.crs)
        db.log_status(geom_uri, "Success")
        if result.candidates is not None and len(result.candidates):
            cands = result.candidates.copy()
            cands["uri"] = geom_uri
            cands.to_file(runner_ups_path, mode="a")
    print(f"\n=== Done. Outputs: {db_path}, {runner_ups_path} ===")


def production() -> None:
    """Run inference across all CSV_PATHS using all available CPU cores."""
    merge_runner_ups()
    db = Database()
    if not db.models and not db.models_w_crs:
        for csv_path in CSV_PATHS:
            models = load_models_from_csv(csv_path, db=db)
            db.log_models(models)
    logger.info("Beginning CRS inference")
    workers = max(os.cpu_count() - 1, 1)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_runner, geom_uri, counties, db): geom_uri
            for geom_uri, counties in db.models
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                geom_uri = future.result()
                logger.info(f"Finished {geom_uri}")
            except Exception as exc:  # noqa: BLE001
                logger.error(str(exc))
    merge_runner_ups()
    logger.info("Finished Inferring CRS")


if __name__ == "__main__":
    production()
