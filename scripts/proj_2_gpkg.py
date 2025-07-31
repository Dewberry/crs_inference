import sqlite3
from pathlib import Path

import geopandas as gpd
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError
from shapely.geometry import box

proj_db_path = Path(__file__).parent.joinpath("data/proj.db")
proj_gpkg_path = Path(__file__).parent.joinpath("data/proj.gpkg")
with sqlite3.connect(proj_db_path) as con:
    cur = con.cursor()
    cur.execute("SELECT auth_name, code FROM crs_view")
    all_crs = cur.fetchall()

dicts = {"auth_name": [], "code": [], "geometry": [], "proj4": []}

for auth_name, code in all_crs:
    try:
        print(f"{auth_name}:{code}")
        crs = CRS.from_authority(auth_name, code)
        transform = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        geometry = crs.area_of_use
        geometry = box(geometry.west, geometry.south, geometry.east, geometry.north)
        dicts["auth_name"].append(auth_name)
        dicts["code"].append(code)
        dicts["proj4"].append(transform.to_proj4())
        dicts["geometry"].append(geometry)
    except (CRSError, ProjError) as e:
        print(e)


gpd.GeoDataFrame(dicts, crs="epsg:4326").to_file(proj_gpkg_path)
