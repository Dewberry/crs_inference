"""Infer the CRS for all HEC-RAS geometry files in an S3 bucket+prefix."""

import json
import sqlite3
import sys
import traceback
from pathlib import Path

from crs_inference.data_models import CountyTargetCache, RasGeometry
from crs_inference.utils import (
    find_metadata,
    get_json_boto3,
    search_s3_boto3,
    split_uri,
)


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
            cur.execute(
                "CREATE TABLE IF NOT EXISTS status (uri TEXT PRIMARY KEY, status TEXT, error TEXT, tb TEXT, FOREIGN KEY(uri) REFERENCES models(uri))"
            )
        con.close()

    @property
    def models(self):
        """Retrieve model information."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county FROM models WHERE crs IS NULL")
            res = cur.fetchall()
        con.close()
        res = [(i, json.loads(j)) for i, j in res]
        return res

    def log_models(self, models: list):
        """Log models and counties to db."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.executemany("INSERT OR IGNORE INTO models (uri, county) VALUES (?, ?)", models)
        con.close()

    def log_crs(self, model_uri: str, crs: str):
        """Log crs for a model to db."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute("UPDATE models SET crs = ? WHERE uri = ?", (crs, model_uri))
        con.close()

    def log_status(self, uri: str, status: str, error: str = "", tb: str = ""):
        """Log the status of a model to database."""
        with sqlite3.connect(self.db_path) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO status(uri, status, error, tb) VALUES(?, ?, ?, ?)", (uri, status, error, tb)
            )
        con.close()


def identify_models(uri: str):
    """Identify all models and their counties in an S3 prefix."""
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
            db.log_status(geom_uri, "Failure", str(e), traceback.format_exc())
            return None
        db.log_status(geom_uri, "Success")
        return res

    return wrap


@process_wrapper
def process_model(geom_uri: str, counties: str, db: Database):
    """Infer the CRS for a model."""
    # Load geom
    geom = RasGeometry.from_s3(geom_uri)
    geom.validate()

    # Load target
    target = CountyTargetCache.instance().get_county_target(counties)

    # Infer CRS
    crs = geom.infer_crs(target)
    db.log_crs(geom_uri, crs)


def main(uri: str):
    """Top-level controller for process."""
    db = Database()
    # models = identify_models(uri)
    # db.log_models(models)
    for geom_uri, counties in db.models:
        process_model(geom_uri, counties, db)


if __name__ == "__main__":
    uri = sys.argv[1]
    main(uri)
