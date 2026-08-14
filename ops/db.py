"""SQLite state management for batch CRS inference runs."""

import json
import sqlite3
from pathlib import Path

import pandas as pd


class Database:
    """SQLite-backed state store for inference runs. Does not hold a persistent connection."""

    def __init__(self, db_path: Path = Path("inference.db")):
        self.db_path = db_path
        self._create_schema()

    def _create_schema(self) -> None:
        """Initialize tables if they don't exist."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("CREATE TABLE IF NOT EXISTS models (uri TEXT PRIMARY KEY, county TEXT, crs TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS run_status (uri TEXT PRIMARY KEY, status TEXT, err TEXT, tb TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS no_geometry (prefix TEXT PRIMARY KEY, csv TEXT, reason TEXT)")

    @property
    def models(self) -> list[tuple[str, list]]:
        """Return all models without an inferred CRS."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county FROM models WHERE crs IS NULL")
            res = cur.fetchall()
        return [(uri, json.loads(county)) for uri, county in res]

    def get_pending_model(self) -> list[tuple[str, list]]:
        """Return one model that has no CRS and no run_status entry."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute(
                "SELECT m.uri, m.county FROM models m "
                "LEFT JOIN run_status s ON s.uri = m.uri "
                "WHERE m.crs IS NULL AND s.status IS NULL LIMIT 1"
            )
            res = cur.fetchall()
        return [(uri, json.loads(county)) for uri, county in res]

    @property
    def models_w_crs(self) -> list[tuple[str, list, str]]:
        """Return all models that have an inferred CRS."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute("SELECT uri, county, crs FROM models WHERE crs IS NOT NULL")
            res = cur.fetchall()
        return [(uri, json.loads(county), crs) for uri, county, crs in res]

    def log_models(self, models: list[tuple[str, str]]) -> None:
        """Insert (uri, county_json) pairs, ignoring duplicates."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.executemany("INSERT OR IGNORE INTO models (uri, county) VALUES (?, ?)", models)

    def log_crs(self, model_uri: str, crs: str) -> None:
        """Set the inferred CRS for a model."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute("UPDATE models SET crs = ? WHERE uri = ?", (crs, model_uri))

    def log_overlaps(self, df: pd.DataFrame) -> None:
        """Append overlap rows to the overlaps table."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            df.to_sql("overlaps", con, if_exists="append", index=False)

    def log_status(self, uri: str, status: str, error: str = "", tb: str = "") -> None:
        """Record the processing status for a model."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO run_status (uri, status, err, tb) VALUES (?, ?, ?, ?)",
                (uri, status, error, tb),
            )

    def log_no_geometry(self, prefix: str, csv: str, reason: str = "not found") -> None:
        """Record a prefix that had no geometry file."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO no_geometry (prefix, csv, reason) VALUES (?, ?, ?)",
                (prefix, csv, reason),
            )

    def get_counties(self, uri: str) -> list:
        """Return the county list for a model URI."""
        with sqlite3.connect(self.db_path, timeout=30) as con:
            cur = con.cursor()
            cur.execute("SELECT county FROM models WHERE uri = ? LIMIT 1", (uri,))
            res = cur.fetchone()
        if res is None:
            raise KeyError(f"uri not found: {uri}")
        return json.loads(res[0])
