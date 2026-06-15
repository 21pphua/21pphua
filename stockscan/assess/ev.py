"""Upgrade 2 — Quantified M2 (expected value).

M2 already asks "what's priced in?" — now it answers in numbers. Bear/base/
bull targets x probabilities -> expected return, downside, and asymmetry.
Bases run *below* street (house style). This is the formal answer to "25% off
a high can still be expensive."

Read compounders on downside + asymmetry, not exp_ret alone.
"""

from __future__ import annotations

from stockscan.config import DEFAULT_HORIZON_MO


def expected_value(
    price: float,
    bear: float,
    base: float,
    bull: float,
    p_bear: float,
    p_base: float,
    p_bull: float,
    horizon_mo: int = DEFAULT_HORIZON_MO,
) -> dict:
    """Probability-weighted return, downside, upside, and asymmetry.

    ``asymmetry`` = expected return / |downside|. > 1 = favourable skew.
    Returns ``None`` for asymmetry when downside is non-negative (no
    meaningful skew to report).
    """
    if price <= 0:
        raise ValueError("price must be positive")
    if abs(p_bear + p_base + p_bull - 1.0) > 1e-9:
        raise ValueError("probabilities must sum to 1.0")

    exp = bear * p_bear + base * p_base + bull * p_bull
    exp_ret = (exp / price - 1) * 100
    downside = (bear / price - 1) * 100
    asym = round(exp_ret / abs(downside), 2) if downside < 0 else None

    return {
        "exp_price": round(exp, 2),
        "exp_ret_pct": round(exp_ret, 1),
        "downside_pct": round(downside, 1),
        "upside_pct": round((bull / price - 1) * 100, 1),
        "asymmetry": asym,
        "horizon_mo": horizon_mo,
    }
