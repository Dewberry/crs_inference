# Developer Guide

## Running Tests

```bash
# Run the full suite
pytest

# With coverage
pytest --cov=crs_inference

# Verbose output for a single module
pytest tests/test_engine.py -v
```

The end-to-end test in `tests/test_e2e_winooski.py` is the highest-value smoke test. It parses a real HEC-RAS model of the Winooski River (Chittenden County, VT, FIPS `50007`) and asserts the result is `EPSG:5646` (Vermont Transverse Mercator). If that test passes, the parser, database, engine, and tiebreakers are all working together correctly.

Test fixtures live in `tests/fixtures/` (minimal synthetic files) and `tests/winooski/` (real model files).

---

## Bundled Data Files

Two GeoPackages ship with the library under `crs_inference/data/`. Both are checked into the repository and must be regenerated whenever their upstream sources change.

### `proj.gpkg` — CRS Database

This file contains one row per projected CRS, covering all EPSG and ESRI codes that PROJ knows about. Each row stores the authority name, numeric code, the area-of-use bounding box in EPSG:4326, and a pre-computed pyproj pipeline string for transforming from EPSG:4326 into that CRS.

The pipeline string is the performance-critical artifact: it lets the engine construct a `pyproj.Transformer` from a plain string at runtime without any authority database lookup.

**Rebuilding `proj.gpkg`**

The build script is `scripts/proj_2_gpkg.py`. It requires a local PROJ SQLite database (`proj.db`), which ships with every pyproj installation.

```bash
python scripts/proj_2_gpkg.py
```

The script:
1. Opens `crs_inference/data/proj.db` and queries `crs_view` for all `(auth_name, code)` pairs.
2. For each pair, constructs a `pyproj.CRS` from the authority and code.
3. Builds a `Transformer` from that CRS to EPSG:4326 and serializes it as a proj4 pipeline string.
4. Reads the CRS area-of-use and converts it to a Shapely bounding box.
5. Writes the result to `crs_inference/data/proj.gpkg` via GeoPandas.

Entries where PROJ raises `CRSError` or `ProjError` (malformed or unsupported CRS definitions) are skipped and logged. The output CRS of the GeoPackage is EPSG:4326.

> After rebuilding, run the full test suite to confirm the new database does not break any known inference results.

---

### `counties.gpkg` — US County Boundaries

This file is a filtered extract of US Census TIGER county boundaries. It contains one polygon per county with a `GEOID` column holding the 5-digit FIPS code. The native CRS is EPSG:4269 (NAD83 geographic).

`Target.from_county()` reads this file, filters by GEOID, and reprojects the selected polygon(s) to EPSG:4326 before using them as a target boundary.

**Rebuilding `counties.gpkg`**

Download the county shapefile from the US Census Bureau TIGER/Line archive:

```bash
curl -O https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip
unzip tl_2023_us_county.zip
```

Then convert and filter to only the columns the library uses:

```python
import geopandas as gpd

gdf = gpd.read_file("tl_2023_us_county.shp")[["GEOID", "geometry"]]
gdf.to_file("crs_inference/data/counties.gpkg", layer="counties")
```

> The TIGER shapefile includes territories (Puerto Rico, USVI, etc.). These are valid inputs to `from_county()` and should be retained.

---

## NHD GeoPackage (optional)

The `NHDTiebreaker` requires the National Hydrography Dataset national GeoPackage (`NHD_H_National_GPKG.gpkg`). This file is ~5 GB and is **not** bundled. Download it from the USGS:

```
https://www.usgs.gov/national-hydrography/access-national-hydrography-products
```

Point the library at it via environment variable:

```bash
export NHD_GPKG_PATH=/path/to/NHD_H_National_GPKG.gpkg
```

The tiebreaker only reads the `NHDFlowline` layer using a bounding-box spatial filter, so the full file must be present but only a small portion is read per call.
