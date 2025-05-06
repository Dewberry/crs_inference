"""Errors."""


class EmptyGeometryError(Exception):
    """Raised when an empty geometry is loaded."""

    def __init__(self):
        super().__init__("Geometry is empty.")


class HTMLDownloadError(Exception):
    """Raised when the geometry contents reflect a failed download from MIP."""

    def __init__(self):
        super().__init__("Download contained '<html>' tag indicating a bad download.")


class OutOfMemoryError(Exception):
    """Raised when a geometry might consume too much memory when reprojected many times."""

    def __init__(self, size: int):
        super().__init__(f"Geometry had size {size / 1e6} MB.")
