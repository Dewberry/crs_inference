from shapely.geometry import Point

from crs_inference.database import CRSDatabase


def test_bundled_loads():
    db = CRSDatabase.bundled()
    gdf = db._gdf
    assert len(gdf) > 0
    assert "auth_name" in gdf.columns
    assert "code" in gdf.columns
    assert "proj4" in gdf.columns


def test_candidates_for_returns_lists():
    db = CRSDatabase.bundled()
    # Point in North Carolina
    geom = Point(-80.0, 35.5)
    local, non_local = db.candidates_for(geom)
    assert isinstance(local, list)
    assert isinstance(non_local, list)
    assert len(local) > 0


def test_pipeline_for_returns_string():
    db = CRSDatabase.bundled()
    geom = Point(-80.0, 35.5)
    local, _ = db.candidates_for(geom)
    assert len(local) > 0
    pipeline = db.pipeline_for(local[0])
    assert pipeline is None or isinstance(pipeline, str)


def test_pipeline_for_unknown_returns_none():
    db = CRSDatabase.bundled()
    result = db.pipeline_for("FAKE:99999")
    assert result is None
