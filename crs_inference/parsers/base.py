from typing import Protocol

from shapely.geometry.base import BaseGeometry


class GeometryParser(Protocol):
    """Parse a source file/string into a shapely geometry for CRS inference.

    Protocol (structural subtyping) rather than ABC: parsers don't need to
    import or inherit from this class — they just need matching method signatures.
    Type checkers enforce the contract statically; no runtime coupling required.
    """

    def parse(self) -> BaseGeometry: ...
    def validate(self) -> None: ...
