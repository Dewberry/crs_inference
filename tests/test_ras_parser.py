from pathlib import Path

import pytest
from shapely.geometry import MultiLineString

from crs_inference.errors import EmptyGeometryError
from crs_inference.parsers.ras import RasParser


def test_from_file_parses_reaches(sample_g01: Path):
    parser = RasParser.from_file(sample_g01)
    assert len(parser.reaches) == 1
    assert parser.reaches[0].river == "TestRiver"
    assert parser.reaches[0].reach == " TestReach"


def test_parse_returns_multilinestring(sample_g01: Path):
    parser = RasParser.from_file(sample_g01)
    geom = parser.parse()
    assert isinstance(geom, MultiLineString)
    assert not geom.is_empty


def test_validate_passes_on_valid(sample_g01: Path):
    parser = RasParser.from_file(sample_g01)
    parser.validate()  # should not raise


def test_validate_raises_empty_geometry():
    parser = RasParser.from_string("")
    with pytest.raises(EmptyGeometryError):
        parser.validate()


def test_validate_raises_html_download_error():
    parser = RasParser.from_string("<html><body>Access Denied</body></html>")
    from crs_inference.errors import HTMLDownloadError
    with pytest.raises(HTMLDownloadError):
        parser.validate()


def test_from_string_roundtrip(sample_g01: Path):
    contents = sample_g01.read_text()
    parser = RasParser.from_string(contents)
    assert len(parser.reaches) == 1
