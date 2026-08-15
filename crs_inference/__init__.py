"""crs_inference: automatic CRS inference for geospatial models."""

__version__ = "0.1.0"

from crs_inference.consts import MIN_OVERLAP_PCT
from crs_inference.database import CRSDatabase
from crs_inference.engine import CRSInferenceEngine
from crs_inference.errors import (
    EmptyGeometryError,
    HTMLDownloadError,
    ModelTooLargeError,
)
from crs_inference.parsers.ras import RasParser
from crs_inference.result import InferenceResult
from crs_inference.target import Target
from crs_inference.tiebreakers import NHDTiebreaker, SmallestCodeTiebreaker


def infer_crs(
    geometry,
    target: Target,
    *,
    tiebreakers=None,
    min_overlap: float | None = None,
) -> InferenceResult:
    """Infer the CRS for a geometry given a target boundary."""
    kwargs = {}
    if tiebreakers is not None:
        kwargs["tiebreakers"] = tiebreakers
    if min_overlap is not None:
        kwargs["min_overlap"] = min_overlap
    return CRSInferenceEngine(**kwargs).infer(geometry, target)


__all__ = [
    "MIN_OVERLAP_PCT",
    "CRSDatabase",
    "CRSInferenceEngine",
    "EmptyGeometryError",
    "HTMLDownloadError",
    "InferenceResult",
    "ModelTooLargeError",
    "NHDTiebreaker",
    "RasParser",
    "SmallestCodeTiebreaker",
    "Target",
    "infer_crs",
]
