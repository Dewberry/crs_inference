import sqlite3

import geopandas as gpd
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError
from shapely.geometry import box

with sqlite3.connect("crs_inference/data/proj.db") as con:
    cur = con.cursor()
    cur.execute("SELECT auth_name, code FROM crs_view")
    all_crs = cur.fetchall()

dicts = {"auth_name": [], "code": [], "geometry": []}

for auth_name, code in all_crs:
    try:
        crs = CRS.from_authority(auth_name, code)
        Transformer.from_crs(crs, "EPSG:4326", always_xy=True)  # Ensure transform is valid
        geometry = crs.area_of_use
        geometry = box(geometry.west, geometry.south, geometry.east, geometry.north)
        dicts["auth_name"].append(auth_name)
        dicts["code"].append(code)
        dicts["geometry"].append(geometry)
    except (CRSError, ProjError) as e:
        print(e)


gpd.GeoDataFrame(dicts, crs="epsg:4326").to_file("crs_inference/data/proj.gpkg")
