"""Errors."""


class EmptyGeometryError(Exception):
    """Raised when an empty geometry is loaded."""

    def __init__(self):
        super().__init__("Geometry is empty.")


class HTMLDownloadError(Exception):
    """Raised when the geometry contents reflect a failed download from MIP."""

    def __init__(self):
        super().__init__("Download contained '<html>' tag indicating a bad download.")


class ModelTooLargeError(Exception):
    """Raised when a geometry file exceeds the size limit."""

    def __init__(self, size: int):
        super().__init__(f"Geometry file had size {size / 1e6:.1f} MB, which exceeds the limit.")
