"""Errors."""


class EmptyGeometryError(Exception):
    """Raised when an empty geometry is loaded."""

    def __init__(self):
        super().__init__("Geometry is empty.")


class HTMLDownloadError(Exception):
    """Raised when the geometry contents reflect a failed download from MIP."""

    def __init__(self):
        super().__init__("Download contained '<html>' tag indicating a bad download.")
