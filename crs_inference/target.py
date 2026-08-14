from pathlib import Path

import geopandas as gpd
import shapely.ops
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from crs_inference.consts import LATENT_CRS
from crs_inference.database import CRSDatabase

_COUNTIES = Path(__file__).parent / "data" / "counties.gpkg"


class Target:
    """A geographic boundary within which CRS inference is constrained."""

    def __init__(self, geometry: BaseGeometry, database: CRSDatabase | None = None):
        self.geometry = geometry
        self._db = database or CRSDatabase.bundled()
        self.local_projections, self.non_local_projections = self._db.candidates_for(geometry)

    @classmethod
    def from_geometry(
        cls,
        geometry: BaseGeometry,
        crs: str = LATENT_CRS,
        database: CRSDatabase | None = None,
    ) -> "Target":
        """Build a Target from any shapely geometry, reprojecting to EPSG:4326 if needed."""
        if crs != LATENT_CRS:
            t = Transformer.from_crs(crs, LATENT_CRS, always_xy=True)
            geometry = shapely.ops.transform(t.transform, geometry)
        return cls(geometry, database)

    @classmethod
    def from_bbox(
        cls,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
        crs: str = LATENT_CRS,
        database: CRSDatabase | None = None,
    ) -> "Target":
        """Build a Target from a bounding box."""
        return cls.from_geometry(box(minx, miny, maxx, maxy), crs=crs, database=database)

    @classmethod
    def from_county(cls, fips: str | list[str], database: CRSDatabase | None = None) -> "Target":
        """Build a Target from a US county FIPS code or list of FIPS codes."""
        gdf = gpd.read_file(_COUNTIES, layer="counties")
        if isinstance(fips, list):
            geom = gdf[gdf["GEOID"].isin(fips)].union_all()
        else:
            geom = gdf[gdf["GEOID"] == fips].geometry.iloc[0]
        assert gdf.crs is not None
        crs_str = f"EPSG:{gdf.crs.to_epsg()}"
        return cls.from_geometry(geom, crs=crs_str, database=database)

    @classmethod
    def from_geodataframe(cls, gdf: gpd.GeoDataFrame, database: CRSDatabase | None = None) -> "Target":
        """Build a Target from the union of all geometries in a GeoDataFrame."""
        assert gdf.crs is not None
        return cls.from_geometry(gdf.union_all(), crs=gdf.crs.to_string(), database=database)
