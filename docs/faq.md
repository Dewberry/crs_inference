# Frequently Asked Questions

<details>
<summary>What does "infer a CRS" actually mean?</summary>

HEC-RAS geometry files store raw coordinate pairs — numbers like `(897432.15, 214876.40)` — with no metadata indicating which coordinate reference system they belong to. CRS inference is the process of figuring out which projected coordinate system those numbers are in by testing each plausible CRS, transforming the geometry into it, and measuring how much of the result overlaps a known geographic boundary. The CRS that produces the highest overlap is returned as the best guess.
</details>

<details>
<summary>How accurate is the inference?</summary>

For models with clear, well-surveyed geometry and a reasonably tight target area (e.g., a single county), accuracy is very high. The end-to-end test suite confirms correct inference on real models. Accuracy decreases for very short models (few coordinates), models near the boundary between two CRS areas of use, or highly unusual projections. The `confidence` field in the result is the raw overlap fraction — values above ~0.8 are reliably correct; values below ~0.3 warrant manual review.
</details>

<details>
<summary>What is a "target" and why do I need one?</summary>

A `Target` tells the engine where on Earth to look. There's no magic way to determine CRS from a set of coordinates without knowing approximately where those coordinates are supposed to be.
</details>

<details>
<summary>What if I don't know which county a model is in?</summary>

Use `Target.from_bbox()` with the broadest bounding box you can confidently assert. A state or multi-state box works. A wider target means more CRS candidates that lead to overlaps with that target, but not all of them may be correct. 
</details>

<details>
<summary>What is the difference between "local" and "non_local" in the result?</summary>

"Local" means the winning CRS is one whose area-of-use polygon (as defined by PROJ) intersects your target geometry. These are the high-confidence candidates. "Non-local" means the engine exhausted the local pool without finding any candidate above the minimum overlap threshold and fell back to scoring every other known CRS. A non-local result is not wrong, but it warrants extra scrutiny — it may indicate the target geometry was too coarse or the model is genuinely in a marginal CRS.
</details>

<details>
<summary>What does the "confidence" value mean exactly?</summary>

Confidence is the fraction of the model geometry's total linear length that falls inside the target boundary after transformation into the inferred CRS. A value of `1.0` means the entire geometry is inside the target. A value of `0.5` means half of the geometry overlaps. It is not a probability estimate — it is a raw spatial overlap ratio. High confidence (> 0.8) strongly suggests the correct CRS. Low confidence (< 0.3) means the result is uncertain.
</details>

<details>
<summary>What is MIN_OVERLAP_PCT and should I change it?</summary>

`MIN_OVERLAP_PCT` (default 0.11%) is the minimum overlap fraction a CRS must achieve to be considered a valid candidate at all. It exists to filter out numerical noise — projections with nearly identical parameters can produce tiny non-zero overlaps even when wrong. In practice you should not need to change this. If you are getting `crs=None` results for models that should have a clear answer, try lowering it. If you are getting false positives, try raising it. Set it via the `MIN_OVERLAP_PCT` environment variable.
</details>

<details>
<summary>What is the NHDTiebreaker and when should I use it?</summary>

`NHDTiebreaker` breaks ties between candidates that have identical overlap scores by counting NHD flowline intersections. The idea is that the correct CRS will align a river centerline model with the actual rivers in the NHD dataset. It is more informative than the default `SmallestCodeTiebreaker` but requires the national NHD GeoPackage (~5 GB). Use it when you are processing many models at scale and want the most accurate tiebreaking, or when the default tiebreaker produces obviously wrong results for tied cases. Set the path via `NHD_GPKG_PATH`.
</details>

<details>
<summary>What is the SmallestCodeTiebreaker?</summary>

It is the default tiebreaker. When two or more candidates have identical overlap scores, it selects the one with the numerically smallest EPSG or ESRI code. This is a deterministic fallback that requires no external data. After reviewing many CRS, it was found that lower codes are generally the more common code for identical CRS with higher codes.
</details>

<details>
<summary>Can I use this library with non-HEC-RAS models?</summary>

Yes. The `CRSInferenceEngine` and `Target` classes work with any Shapely `BaseGeometry`. `RasParser` is just one way to produce that geometry. If you have another model format, write a parser that returns a `MultiLineString` (or any geometry) and pass it directly to `infer_crs()`.
</details>

<details>
<summary>Can I parse a model from S3 without downloading it first?</summary>

Yes. `RasParser.from_s3("s3://bucket/path/to/model.g01")` downloads the file content using boto3 and parses it in memory. AWS credentials must be configured in the environment (via `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, an IAM instance role, etc.). If the S3 URL is not accessible, the download will return an HTML error page and `validate()` will raise `HTMLDownloadError`.
</details>

<details>
<summary>Why does validate() raise HTMLDownloadError?</summary>

When an S3 object is inaccessible (wrong bucket, wrong key, insufficient permissions), AWS returns an XML or HTML error document instead of the requested file. `RasParser.from_s3()` downloads whatever the URL returns, and `validate()` checks if the content starts with `<html>`. If it does, the file was not a real HEC-RAS geometry file and inference would produce nonsense. Fix the S3 URI or credentials and try again.
</details>

<details>
<summary>Why does validate() raise ModelTooLargeError?</summary>

Some HEC-RAS models are very large (hundreds of reaches, thousands of coordinates per reach). The default limit is 10 GB (`RAS_SIZE_LIMIT`). Files larger than this are rejected before parsing to prevent out-of-memory conditions. If you have a legitimately large model and sufficient RAM, raise the limit via the `RAS_SIZE_LIMIT` environment variable.
</details>

<details>
<summary>How do I run inference on many models in parallel?</summary>

Create one `CRSInferenceEngine` instance per process and reuse it. The engine is stateless and the `TransformerCache` it holds gets warmer over time as more transformers are cached, so per-process reuse is faster than constructing a new engine per model. Use Python's `multiprocessing` (not `threading`) — the transformer cache is not thread-safe.

```python
engine = CRSInferenceEngine()  # once per process
for geometry, target in work_items:
    result = engine.infer(geometry, target)
```
</details>

<details>
<summary>What happens if the geometry is empty?</summary>

`validate()` raises `EmptyGeometryError` if the parsed geometry contains no coordinates. This can happen if the `.g01` file has no `River Reach=` sections, or if all `Reach XY=` blocks had zero coordinates. Check that the file is a geometry file (`.g01`, `.g02`, etc.) and not a plan or flow file.
</details>

<details>
<summary>How is proj.gpkg built and can I update it?</summary>

`proj.gpkg` is generated from the PROJ SQLite database by `scripts/proj_2_gpkg.py`. It queries all CRS definitions, computes their area-of-use bounding boxes, and pre-computes the pyproj pipeline strings. See the [Developer Guide](developers.md) for full rebuild instructions. After rebuilding, run the full test suite to confirm no known inference results changed.
</details>

<details>
<summary>Can I use a custom CRS database instead of the bundled one?</summary>

Yes. Pass a custom `CRSDatabase` instance to `Target` and `CRSInferenceEngine`:

```python
from crs_inference import CRSDatabase, Target, CRSInferenceEngine

db = CRSDatabase.from_file("path/to/custom.gpkg")
target = Target.from_county("50007", database=db)
engine = CRSInferenceEngine()
result = engine.infer(geometry, target)
```

The custom GeoPackage must have the same schema as the bundled one: columns `auth_name`, `code`, `proj4`, and `geometry`.
</details>

<details>
<summary>What Python version is required?</summary>

Python 3.12 or later. The library uses several 3.12+ features including the `type` statement syntax in type annotations.
</details>
