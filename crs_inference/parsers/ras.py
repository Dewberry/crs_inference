import math
from functools import cached_property
from pathlib import Path
from typing import Literal, overload

from shapely.geometry import LineString, MultiLineString

from crs_inference.consts import RAS_SIZE_LIMIT
from crs_inference.errors import (
    EmptyGeometryError,
    HTMLDownloadError,
    ModelTooLargeError,
)


@overload
def _search_contents(lines: list, search_string: str, token: str = ..., *, expect_one: Literal[True] = ...) -> str: ...
@overload
def _search_contents(lines: list, search_string: str, token: str = ..., *, expect_one: Literal[False]) -> list[str]: ...
def _search_contents(lines: list, search_string: str, token: str = "=", *, expect_one: bool = True) -> str | list[str]:
    """Split each line by token and return the second half when search_string appears in the first half."""
    results = []
    for line in lines:
        if f"{search_string}{token}" in line:
            results.append(token.join(line.split(token)[1:]))
    if expect_one and len(results) > 1:
        raise ValueError(f"expected 1 result, got {len(results)}")
    elif expect_one and len(results) == 0:
        raise ValueError("expected 1 result, no results found")
    elif expect_one:
        return results[0]
    return results


def _handle_spaces_around_equals(line: str, lines: list[str]) -> str:
    """Return line with or without a space after '=' depending on what appears in lines."""
    if line in lines:
        return line
    if "= " in line and line.replace("= ", "=") in lines:
        return line.replace("= ", "=")
    return line.replace("=", "= ")


def _handle_spaces(line: str, lines: list[str]) -> str:
    """Find a line in lines, trying common space-around-equals variants."""
    if line in lines:
        return line
    if _handle_spaces_around_equals(line.rstrip(" "), lines) in lines:
        return _handle_spaces_around_equals(line.rstrip(" "), lines)
    if _handle_spaces_around_equals(line + " ", lines) in lines:
        return _handle_spaces_around_equals(line + " ", lines)
    raise ValueError(f"line: {line} not found in lines")


def _text_block_from_start_end_str(
    start_str: str, end_strs: list[str], lines: list, additional_lines: int = 0
) -> list[str]:
    """Return lines from the exact match of start_str until a line containing any end_str."""
    start_str = _handle_spaces(start_str, lines)
    start_index = lines.index(start_str)
    end_index = len(lines)
    for line in lines[start_index + 1:]:
        if end_index != len(lines):
            break
        for end_str in end_strs:
            if end_str in line:
                end_index = lines.index(line) + additional_lines
                break
    return lines[start_index:end_index]


def _text_block_from_start_str_length(start_str: str, number_of_lines: int, lines: list) -> list[str]:
    """Return number_of_lines lines immediately after the exact match of start_str."""
    start_str = _handle_spaces(start_str, lines)
    results = []
    in_block = False
    for line in lines:
        if line == start_str:
            in_block = True
            continue
        if in_block:
            if len(results) >= number_of_lines:
                return results
            results.append(line)
    return results


def _data_pairs_from_text_block(lines: list[str], width: int) -> list[tuple[float, float]]:
    """Split lines at given width to get paired data strings and convert to float tuples."""
    pairs = []
    for line in lines:
        for i in range(0, len(line), width):
            x = line[i: int(i + width / 2)]
            y = line[int(i + width / 2): int(i + width)]
            pairs.append((float(x), float(y)))
    return pairs


class _Reach:
    """One river reach parsed from a HEC-RAS geometry file."""

    def __init__(self, ras_data: list, river_reach: str):
        reach_lines = _text_block_from_start_end_str(
            f"River Reach={river_reach}", ["River Reach"], ras_data, -1
        )
        self.ras_data = reach_lines
        self.river_reach = river_reach
        self.river = river_reach.split(",")[0].rstrip()
        self.reach = river_reach.split(",")[1].rstrip()

    @cached_property
    def coords(self) -> list[tuple[float, float]]:
        """Return the coordinate pairs for this reach."""
        lines = _text_block_from_start_str_length(
            f"Reach XY= {self.number_of_coords} ",
            math.ceil(self.number_of_coords / 2),
            self.ras_data,
        )
        return _data_pairs_from_text_block(lines, 32)

    @cached_property
    def number_of_coords(self) -> int:
        """Return the number of coordinates in this reach."""
        return int(_search_contents(self.ras_data, "Reach XY"))

    @cached_property
    def linestring(self) -> LineString:
        """Return the reach centerline as a LineString."""
        return LineString(self.coords)


class RasParser:
    """Parse a HEC-RAS geometry (.g##) file into a MultiLineString centerline."""

    def __init__(self, contents: str):
        self._lines = contents.splitlines()

    @classmethod
    def from_string(cls, contents: str) -> "RasParser":
        """Build a RasParser from a string of file contents."""
        return cls(contents)

    @classmethod
    def from_file(cls, path: Path | str) -> "RasParser":
        """Build a RasParser by reading a local file."""
        with open(path) as f:
            return cls(f.read())

    @classmethod
    def from_s3(cls, uri: str) -> "RasParser":
        """Build a RasParser by downloading a file from S3."""
        from crs_inference.loaders.s3 import get_s3_content
        return cls(get_s3_content(uri))

    def validate(self) -> None:
        """Raise an error if the file is too large, empty, or appears to be an HTML error page."""
        total_size = sum(len(line) for line in self._lines)
        if total_size > RAS_SIZE_LIMIT:
            raise ModelTooLargeError(total_size)
        if self.parse().is_empty:
            if any("<html>" in line.lower() for line in self._lines):
                raise HTMLDownloadError()
            raise EmptyGeometryError()

    def parse(self) -> MultiLineString:
        """Return the model centerline geometry."""
        return self.geometry

    @cached_property
    def reaches(self) -> list[_Reach]:
        """Return a list of Reach objects parsed from the file."""
        names = _search_contents(self._lines, "River Reach", expect_one=False)
        return [_Reach(self._lines, name) for name in names]

    @cached_property
    def geometry(self) -> MultiLineString:
        """Return the full model centerline as a MultiLineString."""
        return MultiLineString([r.linestring for r in self.reaches])
