import logging
import os
from collections.abc import Sequence

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

from crs_inference.consts import LATENT_CRS, MIN_OVERLAP_PCT
from crs_inference.result import InferenceResult
from crs_inference.target import Target
from crs_inference.tiebreakers import SmallestCodeTiebreaker, Tiebreaker
from crs_inference.transformer import TransformerCache

logger = logging.getLogger(__name__)


class CRSInferenceEngine:
    """Stateless CRS scoring engine. Thread-safe; share a single instance across workers."""

    def __init__(
        self,
        tiebreakers: Sequence[Tiebreaker] | None = None,
        min_overlap: float = MIN_OVERLAP_PCT,
    ):
        self._tiebreakers = list(tiebreakers) if tiebreakers else [SmallestCodeTiebreaker()]
        self._min_overlap = min_overlap
        self._transformers = TransformerCache()

    def infer(self, geometry: BaseGeometry, target: Target) -> InferenceResult:
        """Run inference: try local CRS first, fall back to non-local."""
        logger.debug("infer pid=%d", os.getpid())
        local_result = self._score(geometry, target, target.local_projections)
        if local_result.crs is not None:
            return local_result
        return self._score(geometry, target, target.non_local_projections)

    def _score(self, geometry: BaseGeometry, target: Target, crs_list: list[str]) -> InferenceResult:
        """Score each CRS in crs_list and return the best result."""
        rows = []
        for crs in crs_list:
            projected = self._transformers.transform(geometry, crs)
            if not projected.is_valid or projected.length == 0:
                continue
            overlap = projected.intersection(target.geometry).length / projected.length
            auth, code = crs.split(":", 1)
            rows.append(
                {
                    "authority": auth,
                    "code": code,
                    "overlap_pct": round(overlap, 4),
                    "geometry": projected,
                }
            )

        if not rows:
            return InferenceResult(crs=None, confidence=0.0, method="none", candidates=gpd.GeoDataFrame())

        all_candidates = gpd.GeoDataFrame(rows, crs=LATENT_CRS)
        positive: gpd.GeoDataFrame = all_candidates[all_candidates["overlap_pct"] > 0].copy()  # type: ignore[assignment]

        if positive.empty or positive["overlap_pct"].max() < self._min_overlap:
            return InferenceResult(crs=None, confidence=0.0, method="none", candidates=positive)

        sort_cols = ["overlap_pct"]
        for i, tb in enumerate(self._tiebreakers):
            col = f"_tb_score_{i}"
            positive = tb.score(positive).rename(columns={"_tb_score": col})
            sort_cols.append(col)

        positive.sort_values(sort_cols, ascending=False, inplace=True)

        winner = positive.iloc[0]
        method = "local" if crs_list is target.local_projections else "non_local"
        return InferenceResult(
            crs=f"{winner['authority']}:{winner['code']}",
            confidence=float(winner["overlap_pct"]),
            method=method,
            candidates=positive,
        )
