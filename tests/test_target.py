from shapely.geometry import Point

from crs_inference.target import Target


def test_from_bbox_has_candidates():
    target = Target.from_bbox(-80.5, 35.2, -79.8, 35.9)
    assert len(target.local_projections) > 0
    assert isinstance(target.local_projections[0], str)
    assert ":" in target.local_projections[0]


def test_from_county_single():
    target = Target.from_county("37183")  # Wake County, NC
    assert len(target.local_projections) > 0


def test_from_county_list():
    target = Target.from_county(["37183", "37063"])
    assert len(target.local_projections) > 0


def test_from_geometry_reprojects():

    # Point in NC in EPSG:32617 (UTM zone 17N)
    pt = Point(700000, 3900000)
    target = Target.from_geometry(pt, crs="EPSG:32617")
    # geometry stored in 4326, should be around (-80, 35)
    assert isinstance(target.geometry, Point)
    assert -90 < target.geometry.x < -70
    assert 30 < target.geometry.y < 40
