# CRS Inference — How It Works

This document is a detailed technical walkthrough of how the library infers a CRS from a geometry. It is intended for anyone who wants to understand the mechanics rather than just the API.

## Table of Contents

1. [The Core Problem](#the-core-problem)
2. [Step 1 — Parsing Model Geometry](#step-1--parsing-model-geometry)
3. [Step 2 — Building a Target](#step-2--building-a-target)
4. [Step 3 — Selecting CRS Candidates](#step-3--selecting-crs-candidates)
5. [Step 4 — Scoring Each Candidate](#step-4--scoring-each-candidate)
6. [Step 5 — Resolving Ties](#step-5--resolving-ties)
7. [Step 6 — The Result](#step-6--the-result)
8. [Thread Safety and Caching](#thread-safety-and-caching)
9. [Configuration](#configuration)


---

## The Core Problem

HEC-RAS hydraulic model files store geometry as raw coordinate pairs with no embedded CRS. The coordinates are real-world survey values — meters or feet in some projected space — but the file gives no indication of which space. The goal is to figure out which projected coordinate system those numbers belong to.

The insight the library exploits is that a correct CRS transformation will place the geometry where it physically belongs on Earth. If you transform a river centerline into the right CRS and then intersect it with a known county boundary, you get high overlap. Transform it into the wrong CRS and the resulting coordinates land somewhere else — possibly in the ocean — producing near-zero overlap. This is the scoring signal.

---

## Step 1 — Parsing the Model Geometry

A HEC-RAS geometry file (`.g01`, `.g02`, etc.) is a plain-text format. `RasParser` reads it and extracts the centerline of every river reach in the model.

The file is structured as a sequence of reach blocks. Each block begins with a `River Reach=RiverName,ReachName` header. Downstream, a `Reach XY= N` line announces that N coordinate pairs follow. The coordinates are stored in fixed-width 16-character fields — x and y alternating on successive lines — with no delimiter other than whitespace. The parser reads N pairs exactly, which means it must handle the variable amount of whitespace the RAS exporter uses around the `=` sign (some versions emit `Reach XY=42`, others `Reach XY= 42`).

Each reach becomes a Shapely `LineString`. All reaches are combined into a `MultiLineString` that represents the entire spatial footprint of the model. This is the geometry that gets scored.

Before any scoring happens, `validate()` applies three guards: it rejects files larger than `RAS_SIZE_LIMIT` (default 10 GB) to prevent memory exhaustion, rejects content that begins with `<html>` because that indicates an S3 access-denied error page was returned instead of the actual file, and rejects geometries where every reach parsed to zero coordinates.

---

## Step 2 — Building a Target

A `Target` has two jobs: it holds a geographic boundary that the model is expected to fall inside, and it holds the pre-computed list of CRS candidates that are plausible for that area.

The boundary is always stored internally in EPSG:4326 (WGS84 geographic). If you construct a target from a county FIPS code, the library loads the county polygon from the bundled `counties.gpkg`, reprojects it from its native CRS (EPSG:4269, NAD83) to EPSG:4326, and uses that polygon. If you provide a bounding box or an arbitrary Shapely geometry, the same reprojection step happens. This normalization ensures that all spatial comparisons against the CRS database happen in a consistent coordinate space.

Once the boundary geometry exists, `CRSDatabase.candidates_for()` performs a spatial intersection against the area-of-use polygons in `proj.gpkg`. Every CRS whose area of use intersects the target boundary becomes a **local** candidate. Everything else becomes a **non-local** candidate. Local candidates are the high-confidence pool — they are CRS definitions that PROJ itself says are valid for this region. Non-local candidates are the fallback pool, used only if the local search fails entirely.

---

## Step 3 — The CRS Database

`proj.gpkg` is a GeoPackage derived from the PROJ SQLite database. Each row represents one projected CRS and contains four things: the authority name (`EPSG` or `ESRI`), the numeric code, the area-of-use boundary as a box polygon in EPSG:4326, and a pyproj pipeline string that transforms coordinates from EPSG:4326 into that CRS.

The pipeline string is the key artifact. It was pre-computed at build time by constructing a `Transformer` from the CRS to EPSG:4326, inverting it, and serializing it as a proj4 string. This means at inference time, the library never needs to call `Transformer.from_crs()` — which requires a network lookup or authority database scan — because all the transformation math is already baked into the pipeline string.

The spatial query in `candidates_for()` uses GeoPandas, so it is a vectorized polygon intersection against the entire GeoPackage at once. This is fast for the local pool (tens to hundreds of candidates per region) but would be slow if run without the local/non-local split for the full global database.

---

## Step 4 — Scoring Each Candidate

The engine iterates over each CRS in its candidate list. For each one:

**Transformation.** The `TransformerCache` looks up the pipeline string from the database and constructs a pyproj `Transformer` from it. The transformer is cached by pipeline string so it is only constructed once per unique CRS per engine instance. Constructing a transformer is the most expensive single operation in the loop (it parses and validates the proj4 pipeline), so this cache provides significant speedup when the same engine instance is reused across many models. The cache calls `shapely.ops.transform()` with the transformer's `.transform` method, which applies the projection coordinate-by-coordinate to the entire geometry in one pass.

If the pipeline string is `None` (unknown CRS) or equals `+proj=noop` (identity transform), the geometry is returned unchanged and the row is skipped.

**Overlap computation.** The transformed geometry — now in the candidate CRS's units, typically meters or feet — is intersected with the target boundary, which has been transformed into the same CRS. The overlap metric is:

```
overlap = intersection.length / geometry.length
```

This uses linear length rather than area because the input is a `MultiLineString`. A value of `1.0` means every vertex of the model falls inside the target boundary. A value of `0.0` means no part of the transformed geometry touches the boundary — the CRS is wrong.

Only candidates with `overlap >= min_overlap` (default 0.11%) survive. The threshold exists to filter out numerical noise from nearly-correct projections that share similar parameters.

---

## Step 5 — The Two-Tier Search Strategy

The engine always tries local candidates first. If any local candidate exceeds the threshold, the non-local pool is never touched. This is the common case — for a model somewhere in the US, the correct CRS is almost certainly in the local pool for the state or region, which typically contains 10–50 candidates rather than the thousands in the global database.

If no local candidate passes, the engine falls back to non-local candidates. This handles edge cases: models at the boundary between CRS areas of use, models in territories with unusual CRS coverage, or models in regions where the PROJ area-of-use polygons are coarse bounding boxes that don't fully capture the local projections.

The method field in `InferenceResult` records which tier produced the winner (`"local"`, `"non_local"`, or `"none"` if even the fallback failed).

---

## Step 6 — Resolving Ties

When two or more candidates share the same (rounded) maximum overlap, the engine passes the tied candidates to each tiebreaker in sequence. A tiebreaker receives a GeoDataFrame of tied candidates and returns a filtered GeoDataFrame with only the preferred candidate(s). If after all tiebreakers there is still more than one candidate, the first row wins.

**SmallestCodeTiebreaker** casts the `code` column to integers and returns the row with the minimum value. After reviewing many CRS, it was determined that lower codes are often times the more common variants of other CRS.

**NHDTiebreaker** uses the National Hydrography Dataset. For each tied candidate, it reads the `NHDFlowline` layer from the national GeoPackage using the candidate's bounding box as a spatial filter, then counts how many distinct flowline segments intersect the transformed geometry. The candidate with the most flowline intersections wins. The intuition is that the correct CRS will align the model's river centerlines with NHD flowlines — wrong CRS transformations will shift the geometry away from the actual rivers. This is a much stronger signal than smallest-code, but requires the large NHD GeoPackage to be available locally.

---

## Step 7 — The Result

`InferenceResult` is a frozen dataclass. `crs` is the winning authority:code string, or `None` if the search failed. `confidence` is the raw overlap fraction of the winner. `candidates` is a GeoDataFrame containing every candidate that exceeded the minimum overlap threshold, with their geometries in the winning CRS and their overlap scores, sorted by overlap descending. The candidates frame is useful for debugging — it shows not just the winner but how far ahead it was and which projections were close runners-up.

---

## Thread Safety and Caching

`CRSInferenceEngine` is stateless except for the `TransformerCache`. The cache is a plain dict keyed by pipeline string — not thread-safe by default. In practice, the library is used in multiprocessing contexts (one process per model) rather than multithreaded ones, so this is not a concern. If you use threads, create one engine instance per thread.

The `CRSDatabase` loads the entire `proj.gpkg` into memory on first access and holds it for the lifetime of the object. For batch inference jobs, construct a single database instance and share it across all `Target` constructions to avoid repeated disk reads.

---

## Configuration

All runtime behavior can be tuned through environment variables, which the library reads at import time from the process environment (or from a `.env` file via `python-dotenv`):

| Variable | Default | Effect |
|----------|---------|--------|
| `MIN_OVERLAP_PCT` | `0.0011` | Minimum overlap fraction to consider a CRS match |
| `NHD_GPKG_PATH` | — | Path to NHD national GeoPackage for `NHDTiebreaker` |
| `RAS_SIZE_LIMIT` | `10000000000` | Max file size in bytes before `ModelTooLargeError` |

