import geopandas as gpd
from shapely.geometry import MultiLineString

from crs_inference.engine import CRSInferenceEngine
from crs_inference.result import InferenceResult
from crs_inference.target import Target


def test_infer_result_is_inference_result():
    # Use a geometry with coordinates that look like they could be in a projected CRS
    # near Charlotte, NC in ESRI:102719 (NAD 1983 StatePlane NC)
    geom = MultiLineString([[(481000, 234000), (482000, 234500)]])
    target = Target.from_bbox(-81.5, 34.5, -79.5, 36.5)
    engine = CRSInferenceEngine()
    result = engine.infer(geom, target)
    assert isinstance(result, InferenceResult)
    assert result.method in ("local", "non_local", "none")
    assert 0.0 <= result.confidence <= 1.0


def test_infer_returns_none_for_garbage_geometry():
    from shapely.geometry import LineString

    # Coordinates that don't project sensibly into any local CRS for NC
    geom = LineString([(1e12, 1e12), (1e12 + 1, 1e12 + 1)])
    target = Target.from_bbox(-81.5, 34.5, -79.5, 36.5)
    engine = CRSInferenceEngine()
    result = engine.infer(geom, target)
    assert result.crs is None
    assert result.method == "none"


def test_infer_candidates_is_geodataframe():
    from shapely.geometry import LineString

    geom = LineString([(481000, 234000), (482000, 234500)])
    target = Target.from_bbox(-81.5, 34.5, -79.5, 36.5)
    engine = CRSInferenceEngine()
    result = engine.infer(geom, target)
    assert isinstance(result.candidates, gpd.GeoDataFrame)
