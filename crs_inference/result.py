from dataclasses import dataclass, field
from typing import Literal

import geopandas as gpd


@dataclass(frozen=True)
class InferenceResult:
    crs: str | None
    confidence: float
    method: Literal["local", "non_local", "none"]
    candidates: gpd.GeoDataFrame = field(compare=False)
