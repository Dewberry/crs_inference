"""Infer the CRS for all HEC-RAS geometry files in an S3 bucket+prefix."""

import concurrent
import json
import logging
import os
import sqlite3
import time
import traceback
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pandas as pd
import psutil
from pyproj import CRS

from crs_inference.data_models import CountyTargetCache, RasGeometry
from crs_inference.utils import (
    find_metadata,
    get_json_boto3,
    search_s3_boto3,
    split_uri,
)

logging.basicConfig(
    filename="inference.log",
    filemode="a",
    format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
warnings.filterwarnings("ignore", category=RuntimeWarning, module="shapely")


class Database:
    """Simple OOP representation of database (will not persist connection)."""

    def __init__(self):
        self.db_path = Path("inference.db")
        self.create_schema()

    def create_schema(self):
        """Initialize tables."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS models (uri TEXT PRIMARY KEY, county TEXT, crs TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS run_status (uri TEXT PRIMARY KEY, status TEXT, err TEXT, tb TEXT)")

    @property
    def models(self):
        """Retrieve model information."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county FROM models WHERE crs IS NULL")
            res = cur.fetchall()
        res = [(i, json.loads(j)) for i, j in res]
        return res

    def get_model(self):
        """Retrieve one model information."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute(
                "SELECT m.uri, m.county FROM models m LEFT JOIN run_status s ON s.uri = m.uri WHERE m.crs IS NULL AND s.status IS NULL LIMIT 1"
            )
            res = cur.fetchall()
        res = [(i, json.loads(j)) for i, j in res]
        return res

    @property
    def models_w_crs(self):
        """Retrieve model information where CRS is available."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county, crs FROM models WHERE crs IS NOT NULL")
            res = cur.fetchall()
        res = [(i, json.loads(j), k) for i, j, k in res]
        return res

    def log_models(self, models: list):
        """Log models and counties to db."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.executemany("INSERT OR IGNORE INTO models (uri, county) VALUES (?, ?)", models)

    def log_crs(self, model_uri: str, crs: str):
        """Log crs for a model to db."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("UPDATE models SET crs = ? WHERE uri = ?", (crs, model_uri))

    def log_overlaps(self, df: pd.DataFrame):
        """Log crs for a model to db."""
        with sqlite3.connect(self.db_path) as con:
            df.to_sql("overlaps", con, if_exists="append", index=False)

    def log_status(self, uri: str, status: str, error: str = "", tb: str = ""):
        """Log the status of a model to database."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO run_status (uri, status, err, tb) VALUES (?, ?, ?, ?)",
                (uri, status, error, tb),
            )

    def get_geom_counties(self, uri: str) -> list:
        """Get the counties for a geometry."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county, crs FROM models WHERE uri = ? LIMIT 1", (uri,))
            res = cur.fetchall()
        res = [(i, json.loads(j), k) for i, j, k in res]
        return res[0][1]


def identify_models(uri: str):
    """Identify all models and their counties in an S3 prefix."""
    logging.info(f"Identifying models for {uri}")
    meta_packages = find_metadata(uri)
    models = []
    for i in meta_packages:
        try:
            model = process_path(i)
            if model[0] is not None:
                models.append(model)
        except Exception as e:
            print(e)  # TODO: improve
    return models


def process_path(meta_uri: str):
    """Get county and geometry file for a uri."""
    # Get county
    metadata = get_json_boto3(meta_uri)
    counties = metadata.get("county")

    # find geometry
    root = meta_uri.replace("mip_package_geolocation_metadata.json", "")
    geometry_paths = search_s3_boto3(root, r"\.g\d\d$")
    if len(geometry_paths) > 0:
        geometry_uri = sorted(geometry_paths)[0]
    else:
        return None, None

    bucket, _ = split_uri(meta_uri)
    geometry_uri = f"s3://{bucket}/{geometry_uri}"
    return (geometry_uri, json.dumps(counties))


def process_wrapper(func):
    """Single-use wrapper for process_model function."""

    def wrap(geom_uri: str, counties: str, db: Database):
        try:
            res = func(geom_uri, counties, db)
        except Exception as e:
            logging.error(f"Error on {geom_uri}")
            db.log_status(geom_uri, "Failure", str(e), traceback.format_exc())
            return None
        db.log_status(geom_uri, "Success")
        return res

    return wrap


def process_model(geom_uri: str, counties: str, db: Database, debug: bool = False):
    """Infer the CRS for a model."""
    logging.info(f"Processing geometry at {geom_uri}")
    # Load geom
    geom = RasGeometry.from_s3(geom_uri)
    geom.validate()

    # Load target
    target = CountyTargetCache().create_target(counties)

    # Infer CRS
    logging.info(f"Inferring CRS for geometry at {geom_uri}")
    crs, crs_df = geom.infer_crs(target)

    # Log results
    if not debug:
        db.log_crs(geom_uri, crs)
        crs_df["uri"] = geom_uri
        crs_df.to_file("runner_ups.gpkg", mode="a")
    else:
        all_crs = target.local_projections + target.non_local_projections
        _, _, crs_df = geom.find_most_overlap(target, all_crs)
        crs_df.to_file("debug_projections.gpkg", mode="a")
        print(f"{geom_uri}-{crs}")


def process_runner(geom_uri: str, counties: str, db: Database):
    """Catch errors on process_model."""
    try:
        res = process_model(geom_uri, counties, db)
    except Exception as e:
        logging.error(f"Error on {geom_uri}")
        db.log_status(geom_uri, "Failure", str(e), traceback.format_exc())
        return None
    db.log_status(geom_uri, "Success")


def main(uri: str):
    """Top-level controller for process."""
    logging.info("Beginning CRS inference")
    db = Database()
    models = identify_models(uri)
    db.log_models(models)
    for geom_uri, counties in db.models:
        process_runner(geom_uri, counties, db)
    logging.info("Finished Inferring CRS")


def debug_single(geom_uri: str):
    """Debug a single model."""
    db = Database()
    counties = db.get_geom_counties(geom_uri)
    print(f"COUNTIES: {counties}")
    target = CountyTargetCache.instance().get_county_target(counties)
    # process_model(geom_uri, counties, db, debug=True)
    geom = RasGeometry.from_s3(geom_uri)
    geom.validate()
    gdf = gpd.GeoDataFrame({"geometry": [geom.geometry]}, geometry="geometry")
    crs = target.local_projections  # + target.non_local_projections
    all_gdf = []
    for c in crs:
        print(c)
        tmp_gdf = gdf.copy().set_crs(c)
        tmp_gdf = tmp_gdf.to_crs("EPSG:4326")
        tmp_gdf["crs"] = c
        all_gdf.append(tmp_gdf)
    all_gdf = gpd.GeoDataFrame(pd.concat(all_gdf), crs="EPSG:4326")
    all_gdf.to_file("debug_projections.gpkg")
    print(f"COUNTIES: {counties}")


def generate_qc():
    """Make a QC layer for results."""
    db = Database()
    geom_uris = []
    crss = []
    geoms = []
    for geom_uri, counties, crs in db.models_w_crs:
        geom = RasGeometry.from_s3(geom_uri)
        from_crs = CRS(crs)
        to_crs = CRS("EPSG:4326")
        projected = geom.reproject(from_crs, to_crs)
        geom_uris.append(geom_uri)
        crss.append(crs)
        geoms.append(projected)
    gpd.GeoDataFrame({"geom_uri": geom_uris, "CRS": crss, "geometry": geoms}, crs="EPSG:4326").to_file(
        "inference_qc.gpkg"
    )


def worker_system_stats(idx: str, geom_uri: str):
    """Print out some system level stats for logging."""
    logging.info(f"{idx} working on {geom_uri}")
    logging.info(psutil.cpu_percent())
    logging.info(psutil.virtual_memory())
    logging.info(f"{round(psutil.virtual_memory()[2], 2)}% memory used")


def production_worker():
    """Queue processing."""
    idx = str(uuid4())
    logging.info("Starting new worker")
    db = Database()
    i = db.get_model()
    while len(i) != 0:
        geom_uri, counties = i[0]
        db.log_status(geom_uri, "Processing")
        worker_system_stats(idx, geom_uri)
        t1 = time.perf_counter()
        process_runner(geom_uri, counties, db)
        t2 = time.perf_counter()
        logging.info(f"finished {geom_uri} in {round(t2 - t1, 2)} seconds")
        i = db.get_model()


def production():
    """Run pipeline."""
    logging.info("Logging model URIs")
    if not os.path.exists("inference.db"):
        db = Database()
        models = identify_models("s3://fim/mip_30/source_models/")
        db.log_models(models)
        models = identify_models("s3://fim/mip_70/source_models/")
        db.log_models(models)

    logging.info("Beginning CRS inference")
    workers = 6
    with ProcessPoolExecutor(max_workers=workers) as executor:
        results = []
        for i in range(workers):
            results.append(executor.submit(production_worker))
            time.sleep(1)
        for future in concurrent.futures.as_completed(results):
            try:
                data = future.result()
            except Exception as exc:
                logging.error(str(exc))
            else:
                logging.info("Worker finished queue")
    logging.info("Finished Inferring CRS")


# generate_qc()
# debug_single("s3://fim/mip_70/source_models/15-07-0898S_4dec2ac1d197847a2e0e16752e477022568642d7/07100008001847.g01")
if __name__ == "__main__":
    # uri = sys.argv[1]
    # main(uri)
    production()
