from pathlib import Path
from typing import Protocol

import geopandas as gpd


class Tiebreaker(Protocol):
    """Rank tied CRS candidates. Return the GeoDataFrame filtered to the winner(s)."""

    def rank(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...


class SmallestCodeTiebreaker:
    """Always-available fallback: prefer the numerically smallest authority code."""

    def rank(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Return candidates filtered to the row with the smallest numeric code."""
        candidates = candidates.copy()
        candidates["_code_num"] = candidates["code"].astype(int)
        return candidates[candidates["_code_num"] == candidates["_code_num"].min()]  # type: ignore[return-value]


class NHDTiebreaker:
    """Count NHD flowline intersections. Requires the national NHD GeoPackage."""

    def __init__(self, nhd_path: Path | None = None):
        from crs_inference.consts import NHD_GPKG_PATH

        resolved = nhd_path or NHD_GPKG_PATH
        if resolved is None:
            raise ValueError("nhd_path must be provided or NHD_GPKG_PATH must be set in the environment")
        self.nhd_path = Path(resolved)

    def rank(self, candidates: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Return candidates filtered to the row with the most NHD flowline intersections."""
        candidates = candidates.copy()
        in_4269 = candidates.to_crs("EPSG:4269")
        candidates["_nhd_count"] = in_4269.geometry.map(self._count)
        return candidates[candidates["_nhd_count"] == candidates["_nhd_count"].max()]  # type: ignore[return-value]

    def _count(self, geom) -> int:
        """Count distinct NHD flowline segments intersecting geom."""
        rows = gpd.read_file(self.nhd_path, layer="NHDFlowline", mask=geom)
        if len(rows) == 0:
            return 0
        return len(rows.intersection(geom).explode())
