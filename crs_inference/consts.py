"""Shared project constants."""

import os
from pathlib import Path

LATENT_CRS = "EPSG:4326"
MIN_OVERLAP_PCT: float = float(os.getenv("MIN_OVERLAP_PCT", 0.0011))

# Path to the NHD National GeoPackage; not bundled. Set NHD_GPKG_PATH in the environment
# or pass a path directly to NHDTiebreaker.
NHD_GPKG_PATH: Path | None = Path(p) if (p := os.getenv("NHD_GPKG_PATH")) else None
RAS_SIZE_LIMIT: int = int(os.getenv("RAS_SIZE_LIMIT", int(1e10)))
