"""Classes for various package processes."""

import json
from functools import cached_property

import geopandas as gpd
import pandas as pd
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import MultiLineString, Polygon
from shapely.geometry.base import BaseGeometry

from crs_inference.errors import EmptyGeometryError, HTMLDownloadError
from crs_inference.ras import Reach, search_contents
from crs_inference.utils import get_ras_crs, get_s3_content


class Target:
    """Class representing some geometry with which another geometry falls."""

    def __init__(self, geometry: Polygon, crs: CRS):
        self.crs = CRS("EPSG:4326")
        if crs != self.crs:
            transformer = Transformer.from_crs(crs, self.crs, always_xy=True)
            geometry = shapely.ops.transform(transformer.transform, self.geometry)
        self.geometry = geometry
        self.intersect_df = self.intersect_crs()

    def intersect_crs(self):
        """Find crs that are applicable in this area."""
        ras_crs = get_ras_crs()
        ras_crs["local"] = ras_crs.geometry.intersects(self.geometry)
        return ras_crs

    @property
    def local_projections(self) -> list[CRS]:
        """Get CRS with area of use containing the geometry."""
        local_projections = self.intersect_df[self.intersect_df["local"]][["auth_name", "code"]].values
        return [CRS.from_authority(i, j) for i, j in local_projections]

    @property
    def non_local_projections(self) -> list[CRS]:
        """Get CRS with area of use containing the geometry."""
        non_local_projections = self.intersect_df[~self.intersect_df["local"]][["auth_name", "code"]].values
        return [CRS.from_authority(i, j) for i, j in non_local_projections]


class Geometry:
    """Class representing some geospatial geometry for which the CRS should be identified."""

    def __init__(self, geometry):
        self.geometry = geometry

    def infer_crs(self, target: Target) -> str:
        """Find the crs leading to most overlap between geometry and target."""
        best_crs, overlap = self.find_most_overlap(target, target.local_projections)
        if best_crs is not None:
            return best_crs
        best_crs, overlap = self.find_most_overlap(target, target.non_local_projections)
        return best_crs

    def reproject(self, from_crs: CRS, to_crs: CRS) -> BaseGeometry:
        """Reproject the geometry from one crs to another."""
        transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
        return shapely.ops.transform(transformer.transform, self.geometry)

    def find_most_overlap(self, target: Target, crs_list: list[CRS]) -> tuple:
        """Find the CRS that yields the most overlap between geometry and target."""
        overlap_pcts = []
        authorities = []
        codes = []
        for crs in crs_list:
            projected_geom = self.reproject(crs, target.crs)
            if projected_geom.is_valid:
                overlap = projected_geom.intersection(target.geometry).length / projected_geom.length
                overlap_pcts.append(overlap)
                authorities.append(crs.to_authority()[0])
                codes.append(crs.to_authority()[1])
        overlap_df = pd.DataFrame({"authority": authorities, "code": codes, "overlap_pct": overlap_pcts})
        overlap_df["overlap_pct"] = overlap_df["overlap_pct"].round(3)
        overlap_df = overlap_df.sort_values(["overlap_pct", "code"], ascending=[False, True])

        best_crs = overlap_df.iloc[0]
        if best_crs.overlap_pct < 0.0011:  # 0.1%
            return None, 0
        else:
            return f"{best_crs.authority}:{best_crs.code}", best_crs.overlap_pct


class RasGeometry(Geometry):
    """Stripped down class for HEC-RAS geometry."""

    def __init__(self, contents: str):
        self.contents = contents.splitlines()

    @classmethod
    def from_s3(cls, href: str):
        """Load a geometry file from AWS S3."""
        contents = get_s3_content(href)
        return cls(contents)

    @classmethod
    def from_file(cls, href: str):
        """Load a geometry file from a local file."""
        with open(href) as f:
            contents = f.read().splitlines()

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
            if any(["<html>" in i for i in self.contents.lower]):
                raise HTMLDownloadError()
        else:
            raise EmptyGeometryError()


class CountyTargetCache:
    """A class to cache county Target classes for speed and reusability."""

    _instance = None

    def __init__(self):
        raise RuntimeError("Call instance() instead")

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls.gdf = gpd.read_file("crs_inference/data/counties.gpkg", layer="counties")
            cls.cache = {}
        return cls._instance

    def create_target(self, county: str | list) -> Target:
        """Load a target from a county boundary."""
        if isinstance(county, list):
            geom = self.gdf[self.gdf["GEOID"].isin(county)].union_all()
        elif isinstance(county, str):
            geom = self.gdf[self.gdf["GEOID"] == county].geometry.iloc[0]
        else:
            raise ValueError(f"county should be list or str, but got {type(county)}")

        return Target(geom, self.gdf.crs)

    def get_county_target(self, county: str | list):
        """Get or create a Target for a county."""
        if isinstance(county, list):
            idx_str = json.dumps(county)
        elif isinstance(county, str):
            idx_str = county
        else:
            raise ValueError(f"county should be list or str, but got {type(county)}")

        if idx_str not in self.cache:
            self.cache[idx_str] = self.create_target(county)

        return self.cache[idx_str]
