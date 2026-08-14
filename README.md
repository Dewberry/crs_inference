# crs-inference

Automatically infers the Coordinate Reference System (CRS/EPSG code) for geospatial models that lack explicit CRS metadata. The primary use case is HEC-RAS riverine hydraulic models, but the core engine works with any Shapely geometry.

The library works by transforming model geometry into each plausible CRS, measuring how much of the geometry overlaps a known geographic boundary, and returning the CRS with the highest overlap.

## Installation

```bash
pip install -e .
```

For development extras:

```bash
pip install -e ".[dev]"    # pytest, ruff
pip install -e ".[ops]"    # matplotlib, pynhd, pystac
```

Requires **Python ≥ 3.12**.

## Quick Start

```python
from crs_inference import infer_crs, RasParser, Target

# Parse a HEC-RAS geometry file
parser = RasParser.from_file("path/to/model.g01")
parser.validate()
geometry = parser.parse()          # returns a Shapely MultiLineString

# Build a target using a US county FIPS code
target = Target.from_county("50007")   # Chittenden County, VT

# Infer the CRS
result = infer_crs(geometry, target)

print(result.crs)           # e.g. "EPSG:5646"
print(result.confidence)    # overlap fraction, e.g. 0.97
print(result.method)        # "local" | "non_local" | "none"
```

You can also build a target from a bounding box or any Shapely geometry:

```python
from crs_inference import CRSDatabase, Target

db = CRSDatabase.bundled()
target = Target.from_bbox(-73.2, 44.3, -72.8, 44.6, crs="EPSG:4326", database=db)
```

For custom tiebreakers or overlap thresholds, use the engine directly:

```python
from crs_inference import CRSInferenceEngine
from crs_inference.tiebreakers import NHDTiebreaker

engine = CRSInferenceEngine(
    tiebreakers=[NHDTiebreaker()],
    min_overlap=0.05,
)
result = engine.infer(geometry, target)
```

## Documentation

- [How it works](docs/technical_reference.md)
- [Developer guide](docs/developers.md)
- [FAQ](docs/faq.md)
