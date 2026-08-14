"""Classes for various package processes."""

import json
import logging
import os
import sys
import warnings
from functools import cached_property

import geopandas as gpd
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import MultiLineString, Polygon
from shapely.geometry.base import BaseGeometry

from crs_inference.consts import LATENT_CRS
from crs_inference.errors import EmptyGeometryError, HTMLDownloadError, OutOfMemoryError
from crs_inference.ras import Reach, search_contents
from crs_inference.utils import count_intersections, get_ras_crs, get_s3_content

warnings.filterwarnings("ignore", module="pyogrio")

logger = logging.getLogger(__name__)


class Target:
    """Class representing some geometry with which another geometry falls."""

    def __init__(self, geometry: Polygon, crs: CRS):
        self.crs = LATENT_CRS
        if crs != self.crs:
            transformer = Transformer.from_crs(crs, self.crs, always_xy=True)
            geometry = shapely.ops.transform(transformer.transform, geometry)
        self.geometry = geometry
        # Compute projection lists once and discard the GDF to avoid holding a
        # 2.6 MB copy per cached county.
        ras_crs = get_ras_crs().copy()
        ras_crs["local"] = ras_crs.geometry.intersects(self.geometry)
        local = ras_crs[ras_crs["local"]][["auth_name", "code"]].values
        non_local = ras_crs[~ras_crs["local"]][["auth_name", "code"]].values
        self._local_projections: list[str] = [f"{a}:{c}" for a, c in local]
        self._non_local_projections: list[str] = [f"{a}:{c}" for a, c in non_local]

    @property
    def local_projections(self) -> list[CRS]:
        """Get CRS with area of use containing the geometry."""
        return self._local_projections

    @property
    def non_local_projections(self) -> list[CRS]:
        """Get CRS with area of use containing the geometry."""
        return self._non_local_projections


class Geometry:
    """Class representing some geospatial geometry for which the CRS should be identified."""

    def __init__(self, geometry):
        self.geometry = geometry

    def infer_crs(self, target: Target) -> str:
        """Find the crs leading to most overlap between geometry and target."""
        logger.info(f"Inferring CRS on process ID {os.getpid()}")
        best_crs, _, overlap_df = self.find_most_overlap(target, target.local_projections)
        if best_crs is not None:
            logger.info(f"Selected CRS {best_crs} on process ID {os.getpid()}")
            return best_crs, overlap_df
        logger.info(f"Trying backup CRS on process ID {os.getpid()}")
        best_crs, _, overlap_df = self.find_most_overlap(target, target.non_local_projections)
        if best_crs is not None:
            logger.info(f"Selected CRS {best_crs} on process ID {os.getpid()}")
        else:
            logger.info(f"No valid CRS found on process ID {os.getpid()}")
        return best_crs, overlap_df

    def reproject(self, from_crs: CRS, to_crs: CRS) -> BaseGeometry:
        """Reproject the geometry from one crs to another."""
        transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
        return shapely.ops.transform(transformer.transform, self.geometry)

    def find_most_overlap(self, target: Target, crs_list: list[str]) -> tuple:
        """Find the CRS that yields the most overlap between geometry and target."""
        overlap_pcts = []
        authorities = []
        codes = []
        geoms = []
        transform_caches = TransformerCache()
        for ind, crs in enumerate(crs_list):
            projected_geom = transform_caches.transform(self.geometry, crs)
            if projected_geom.is_valid:
                overlap = projected_geom.intersection(target.geometry).length / projected_geom.length
                overlap_pcts.append(overlap)
                authorities.append(crs.split(":")[0])
                codes.append(crs.split(":")[1])
                geoms.append(projected_geom)
        overlap_df = gpd.GeoDataFrame(
            {"authority": authorities, "code": codes, "overlap_pct": overlap_pcts, "geometry": geoms}, crs=LATENT_CRS
        )
        overlap_df["overlap_pct"] = overlap_df["overlap_pct"].round(3)
        overlap_df = overlap_df.sort_values(["overlap_pct", "code"], ascending=[False, True])
        best_crs = overlap_df[
            (overlap_df["overlap_pct"] == overlap_df["overlap_pct"].max()) & (overlap_df["overlap_pct"] != 0)
        ].copy()
        if len(best_crs) == 0:
            return None, 0, overlap_df[overlap_df["overlap_pct"] > 0].copy()
        if len(best_crs) > 1:  # tie break
            best_crs["intersections"] = best_crs.to_crs("EPSG:4269").geometry.map(lambda r: count_intersections(r))
            best_crs = best_crs[best_crs["intersections"] == best_crs["intersections"].max()].copy()
            if len(best_crs) > 1:
                best_crs["code_num"] = best_crs["code"].apply(lambda x: int(x.split(":")[-1]))
                best_crs = best_crs[best_crs["code_num"] == best_crs["code_num"].min()].copy()

        best_crs = best_crs.iloc[0]
        if best_crs.overlap_pct < 0.0011:  # 0.1%
            return None, 0, overlap_df[overlap_df["overlap_pct"] > 0].copy()
        else:
            return (
                f"{best_crs.authority}:{best_crs.code}",
                best_crs.overlap_pct,
                overlap_df[overlap_df["overlap_pct"] > 0].copy(),
            )


class RasGeometry(Geometry):
    """Stripped down class for HEC-RAS geometry."""

    def __init__(self, contents: str):
        self.contents = contents.splitlines()

    @classmethod
    def from_s3(cls, href: str):
        """Load a geometry file from AWS S3."""
        logger.info(f"Loading RAS geometry at {href}")
        contents = get_s3_content(href)
        return cls(contents)

    @classmethod
    def from_file(cls, href: str):
        """Load a geometry file from a local file."""
        logger.info(f"Loading RAS geometry at {href}")
        with open(href) as f:
            contents = f.read()

        return cls(contents)

    @cached_property
    def reaches(self) -> dict:
        """A dictionary of the reaches contained in the HEC-RAS geometry file."""
        river_reaches = search_contents(self.contents, "River Reach", expect_one=False)
        reaches = []
        for river_reach in river_reaches:
            reaches.append(Reach(self.contents, river_reach))
        return reaches

    @cached_property
    def geometry(self) -> MultiLineString:
        """Geometry of the ras centerline."""
        return MultiLineString([r.linestring for r in self.reaches])

    @property
    def invalid_geometry(self) -> bool:
        """Check if geometry is valid."""
        return self.geometry.is_empty

    def validate(self):
        """Check if geometry is valid and raise informative error."""
        if self.invalid_geometry:
            if any(["<html>" in i.lower() for i in self.contents]):
                raise HTMLDownloadError()
            else:
                raise EmptyGeometryError()
        if sys.getsizeof(self.contents) > 1e10:
            raise OutOfMemoryError(sys.getsizeof(self.contents))


class CountyTargetCache:
    """A class to cache county Target classes for speed and reusability."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.gdf = gpd.read_file("crs_inference/data/counties.gpkg", layer="counties")
            cls._instance.cache = {}
        return cls._instance

    def create_target(self, county: str | list) -> Target:
        """Load a target from a county boundary."""
        logger.info(f"Creating new target for {str(county)}")
        if isinstance(county, list):
            geom = self.gdf[self.gdf["GEOID"].isin(county)].union_all()
        elif isinstance(county, str):
            geom = self.gdf[self.gdf["GEOID"] == county].geometry.iloc[0]
        else:
            raise ValueError(f"county should be list or str, but got {type(county)}")

        return Target(geom, self.gdf.crs)

    def get_county_target(self, county: str | list) -> Target:
        """Get or create a Target for a county."""
        if isinstance(county, list):
            idx_str = json.dumps(sorted(county))
        elif isinstance(county, str):
            idx_str = county
        else:
            raise ValueError(f"county should be list or str, but got {type(county)}")

        if idx_str not in self.cache:
            self.cache[idx_str] = self.create_target(county)
            logging.info(f"Target cache has size {len(self.cache)}")

        return self.cache[idx_str]


class TransformerCache:
    """Cache all the CRS transformers."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            crs_gdf = get_ras_crs()
            cls.transformers = {}
            cls.pipelines = {}
            for ind, r in crs_gdf.iterrows():
                name = f"{r.auth_name}:{r.code}"
                cls.pipelines[name] = r.proj4
        return cls._instance

    def transform(self, geometry: BaseGeometry, crs: str) -> BaseGeometry:
        """Use a cached transform to transform a geometry."""
        if crs not in self.transformers:
            pipeline = self.pipelines[crs]
            if pipeline is None or pipeline == "+proj=noop":
                return geometry
            self.transformers[crs] = Transformer.from_pipeline(pipeline)
        return shapely.ops.transform(self.transformers[crs].transform, geometry)
