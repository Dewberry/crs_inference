import geopandas as gpd
from shapely.geometry import box

from crs_inference.tiebreakers import SmallestCodeTiebreaker


def _make_candidates(codes: list[str], authority: str = "ESRI") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "authority": [authority] * len(codes),
            "code": codes,
            "overlap_pct": [0.95] * len(codes),
            "geometry": [box(-80, 35, -79, 36)] * len(codes),
        },
        crs="EPSG:4326",
    )


def test_smallest_code_picks_minimum():
    tb = SmallestCodeTiebreaker()
    candidates = _make_candidates(["102720", "102697", "102719"])
    result = tb.score(candidates).sort_values("_tb_score", ascending=False)
    assert result.iloc[0]["code"] == "102697"


def test_smallest_code_single_candidate():
    tb = SmallestCodeTiebreaker()
    candidates = _make_candidates(["102697"])
    result = tb.score(candidates)
    assert len(result) == 1
