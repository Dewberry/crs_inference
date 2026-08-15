"""End-to-end inference test using the Winooski River HEC-RAS model (Chittenden County, VT)."""

from pathlib import Path

from crs_inference import CRSInferenceEngine, RasParser, Target

WINOOSKI_G01 = Path(__file__).parent / "winooski" / "winooski.g01"
CHITTENDEN_FIPS = "50007"
EXPECTED_CRS = "EPSG:5646"


def test_winooski_infers_expected_crs():
    parser = RasParser.from_file(WINOOSKI_G01)
    parser.validate()
    target = Target.from_county(CHITTENDEN_FIPS)
    result = CRSInferenceEngine().infer(parser.parse(), target)
    assert result.crs == EXPECTED_CRS, (
        f"Expected {EXPECTED_CRS}, got {result.crs}. "
        f"Candidates: {result.candidates[['authority', 'code', 'overlap_pct']].to_string()}"
    )
    assert result.confidence > 0.0
    assert result.method == "local"
