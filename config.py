"""Central configuration: thresholds, weights, defaults.

Everything tunable lives here so the judgment rules are auditable in one
place rather than scattered through the code.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Assessment engine (Stage 2)
# ---------------------------------------------------------------------------

# Max points per M8 axis. Sums to 100 -> band cutoffs are on a 100 scale.
M8_MAX: dict[str, int] = {
    "theme": 15,
    "moat": 20,
    "proof": 15,
    "entry": 15,
    "ceiling": 10,
    "cycle": 10,
    "falsify": 5,
    "confirm": 10,
}

# The narrative-prone CORE axes. A *decisive* subscore on these
# (> int(0.7 * max)) must cite a fact or it is capped at the threshold.
EVIDENCE_REQUIRED: tuple[str, ...] = ("theme", "moat", "proof", "entry")

# Final-score band cutoffs (after bear haircut).
BANDS: tuple[tuple[int, str], ...] = (
    (80, "A"),
    (65, "B"),
    (50, "C"),
    (0, "REJECT"),
)

# Expected-value default horizon (months).
DEFAULT_HORIZON_MO: int = 18

# Base-rate -> max position size (% of portfolio) for speculative names.
FULL_SPEC_BAND: float = 3.0  # max size for a high-base-rate spec
SPEC_LOW_BAND: float = 1.0   # base_rate < 15%
SPEC_MID_BAND: float = 2.0   # 15% <= base_rate < 30%

# ---------------------------------------------------------------------------
# Quantitative screen (Stage 1)
# ---------------------------------------------------------------------------

# Composite-factor weights. Higher composite -> better Stage-1 rank.
# Each factor is converted to a cross-sectional z-score before weighting,
# so weights are relative importances, not absolute scales.
FACTOR_WEIGHTS: dict[str, float] = {
    "momentum": 0.25,    # 12-1 month price return
    "trend": 0.20,       # price vs 200-day moving average
    "value": 0.20,       # earnings yield (1 / forward P/E)
    "quality": 0.20,     # return on equity
    "low_volatility": 0.15,  # inverse of trailing volatility
}

# How many Stage-1 survivors advance to the deep assessment by default.
DEFAULT_TOP_N: int = 10

# Default universe: a built-in name (resolved by stockscan.universe) or a path.
# "sp500" is the real S&P 500 list packaged with the tool; "dow30" is a quick
# 30-name option. Override with --universe <name|file> or --tickers.
DEFAULT_UNIVERSE: str = "sp500"

# ---------------------------------------------------------------------------
# LLM research (Stage 2 CORE-subscore drafting)
# ---------------------------------------------------------------------------

# Default to the most capable model. Adaptive thinking, high effort.
LLM_MODEL: str = "claude-opus-4-8"
LLM_MAX_TOKENS: int = 8000
LLM_EFFORT: str = "high"

# ---------------------------------------------------------------------------
# SAR Trading breakout scanner (stockscan sar)
# ---------------------------------------------------------------------------

# Lookback windows (daily bars): run-up window, then the pullback base.
SAR_RUNUP_LOOKBACK: int = 40
SAR_PULLBACK_LOOKBACK: int = 20

# Checklist weights (sum to 100): run-up, SMA incline, tightening, volume
# dry-up, range break, breakout volume, close near high. Breakout volume +
# range break weighted heaviest. This weighting is ours, not the source doc's.
SAR_WEIGHTS: tuple[int, ...] = (15, 15, 10, 10, 20, 20, 10)

# Verdict cutoffs on the 0-100 score.
SAR_TAKE_AT: int = 65
SAR_WATCH_AT: int = 40

# Stock filters from the doc: price > $1, ADR% > 5, avg daily $ volume > $3.5M.
SAR_MIN_PRICE: float = 1.0
SAR_MIN_ADR: float = 0.05
SAR_MIN_DOLLAR_VOL: float = 3_500_000

# "Coiling" watchlist: steps 01-04 score >= this (of 50) and the close sits
# within SAR_COIL_MAX_GAP below the base high.
SAR_COIL_MIN_PREP: int = 35
SAR_COIL_MAX_GAP: float = 0.03

# Market-regime indexes (10 SMA above 20 SMA = favorable).
SAR_REGIME_INDEXES: tuple[str, ...] = ("SPY", "QQQ")
