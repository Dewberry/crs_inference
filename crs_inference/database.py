from functools import cached_property
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

_BUNDLED = Path(__file__).parent / "data" / "proj.gpkg"


class CRSDatabase:
    """Holds the set of candidate CRS and filters them by geographic area of use."""

    def __init__(self, path: Path = _BUNDLED):
        self._path = path

    @cached_property
    def _gdf(self) -> gpd.GeoDataFrame:
        return gpd.read_file(self._path)

    @classmethod
    def bundled(cls) -> "CRSDatabase":
        """Return the bundled default CRS database."""
        return cls(_BUNDLED)

    @classmethod
    def from_file(cls, path: Path) -> "CRSDatabase":
        """Return a CRS database loaded from path."""
        return cls(path)

    def candidates_for(self, geometry: BaseGeometry) -> tuple[list[str], list[str]]:
        """Return (local_crs, non_local_crs) EPSG/ESRI strings for the given geometry."""
        gdf = self._gdf
        local_mask = gdf.geometry.intersects(geometry)
        local = [f"{r.auth_name}:{r.code}" for _, r in gdf[local_mask].iterrows()]
        non_local = [f"{r.auth_name}:{r.code}" for _, r in gdf[~local_mask].iterrows()]
        return local, non_local

    def pipeline_for(self, crs: str) -> str | None:
        """Return the proj4 pipeline string for a given 'AUTH:CODE' identifier."""
        auth, code = crs.split(":", 1)
        row = self._gdf[(self._gdf["auth_name"] == auth) & (self._gdf["code"] == code)]
        if row.empty:
            return None
        val = row.iloc[0]["proj4"]
        return None if pd.isna(val) else val
