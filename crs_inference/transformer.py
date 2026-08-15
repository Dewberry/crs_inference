import shapely.ops
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

from crs_inference.database import CRSDatabase


class TransformerCache:
    """Cache pyproj transformers by CRS string to avoid repeated pipeline parsing."""

    def __init__(self, database: CRSDatabase | None = None):
        self._db = database or CRSDatabase.bundled()
        self._transformers: dict[str, Transformer | None] = {}

    def transform(self, geometry: BaseGeometry, crs: str) -> BaseGeometry:
        """Transform geometry from crs to EPSG:4326 using a cached transformer."""
        if crs not in self._transformers:
            pipeline = self._db.pipeline_for(crs)
            if pipeline is None or pipeline == "+proj=noop":
                self._transformers[crs] = None
            else:
                self._transformers[crs] = Transformer.from_pipeline(pipeline)
        transformer = self._transformers[crs]
        if transformer is None:
            return geometry
        return shapely.ops.transform(transformer.transform, geometry)
