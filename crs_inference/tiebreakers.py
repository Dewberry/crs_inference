from pathlib import Path
from typing import Protocol

import geopandas as gpd


class Tiebreaker(Protocol):
    """Score CRS candidates for sorting. Add a '_tb_score' column; higher is better."""

    def score(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...


class SmallestCodeTiebreaker:
    """Always-available fallback: prefer the numerically smallest authority code."""

    def score(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        candidates = candidates.copy()
        # negate so smaller code sorts higher
        candidates["_tb_score"] = -candidates["code"].astype(int)
        return candidates


class NHDTiebreaker:
    """Count NHD flowline intersections. Requires the national NHD GeoPackage."""

    def __init__(self, nhd_path: Path | None = None):
        from crs_inference.consts import NHD_GPKG_PATH

        resolved = nhd_path or NHD_GPKG_PATH
        if resolved is None:
            raise ValueError("nhd_path must be provided or NHD_GPKG_PATH must be set in the environment")
        self.nhd_path = Path(resolved)

    def score(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        candidates = candidates.copy()
        in_4269 = candidates.to_crs("EPSG:4269")
        candidates["_tb_score"] = in_4269.geometry.map(self._count)
        return candidates

    def _count(self, geom) -> int:
        """Count distinct NHD flowline segments intersecting geom."""
        rows = gpd.read_file(self.nhd_path, layer="NHDFlowline", mask=geom)
        if len(rows) == 0:
            return 0
        return len(rows.intersection(geom).explode())
