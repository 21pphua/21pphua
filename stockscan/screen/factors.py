"""Factor extraction and cross-sectional normalisation.

Pure-Python (no pandas/numpy required) so the screen logic is testable
offline. Each raw factor is turned into a cross-sectional z-score; the
composite is a weighted sum of z-scores. Transparent by design — you can
read exactly why a name ranks where it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Optional, Sequence

from stockscan.config import FACTOR_WEIGHTS
from stockscan.data.providers import MarketSnapshot


# Raw factor name -> (extractor, higher_is_better)
def _raw_factors(s: MarketSnapshot) -> dict[str, Optional[float]]:
    return {
        "momentum": s.momentum_12_1,
        "trend": s.pct_above_200dma,
        "value": s.earnings_yield,            # higher earnings yield = cheaper
        "quality": s.return_on_equity,
        # Lower volatility is better -> negate so "higher is better" holds.
        "low_volatility": (-s.volatility) if s.volatility is not None else None,
    }


@dataclass
class FactorScores:
    ticker: str
    raw: dict[str, Optional[float]]
    z: dict[str, float]
    composite: float


def _zscores(values: Sequence[Optional[float]]) -> list[float]:
    """Z-score a column, treating missing values as neutral (0)."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return [0.0 for _ in values]
    mean = sum(present) / len(present)
    var = sum((v - mean) ** 2 for v in present) / len(present)
    std = sqrt(var)
    if std == 0:
        return [0.0 for _ in values]
    return [((v - mean) / std) if v is not None else 0.0 for v in values]


def score_factors(snapshots: Sequence[MarketSnapshot]) -> list[FactorScores]:
    """Compute per-name factor z-scores and the weighted composite."""
    raw_by_name = [_raw_factors(s) for s in snapshots]
    factor_names = list(FACTOR_WEIGHTS.keys())

    # Z-score each factor across the universe.
    z_columns: dict[str, list[float]] = {}
    for f in factor_names:
        z_columns[f] = _zscores([rb[f] for rb in raw_by_name])

    results: list[FactorScores] = []
    for i, snap in enumerate(snapshots):
        z = {f: z_columns[f][i] for f in factor_names}
        composite = sum(FACTOR_WEIGHTS[f] * z[f] for f in factor_names)
        results.append(
            FactorScores(
                ticker=snap.ticker,
                raw=raw_by_name[i],
                z=z,
                composite=composite,
            )
        )
    return results
