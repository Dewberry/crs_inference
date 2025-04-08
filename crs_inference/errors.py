"""Errors."""


class EmptyGeometryError(Exception):
    """Raised when an empty geometry is loaded."""

    message = "Geometry is empty."


class HTMLDownloadError(Exception):
    """Raised when the geometry contents reflect a failed download from MIP."""

    message = "Download contained '<html>' tag indicating a bad download."
