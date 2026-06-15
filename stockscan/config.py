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

# A small, dependency-free default universe so the tool runs out of the box.
# Override with --universe <file> (one ticker per line) for the real thing.
DEFAULT_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AVGO", "TSLA",
    "V", "MA", "JPM", "UNH", "COST", "HD", "PG", "JNJ", "ABBV", "KO",
    "WMT", "XOM",
)

# ---------------------------------------------------------------------------
# LLM research (Stage 2 CORE-subscore drafting)
# ---------------------------------------------------------------------------

# Default to the most capable model. Adaptive thinking, high effort.
LLM_MODEL: str = "claude-opus-4-8"
LLM_MAX_TOKENS: int = 8000
LLM_EFFORT: str = "high"
