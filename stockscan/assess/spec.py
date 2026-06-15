"""Upgrade 4 — Base-rate -> spec-size binding.

M5 already asks the base rate; now it sizes by it. A spec doesn't just get a
lower score — it gets a hard position-size cap tied to the outside-view odds
the category reaches commercial scale. "Size like the base rate is real."
"""

from __future__ import annotations

from stockscan.config import FULL_SPEC_BAND, SPEC_LOW_BAND, SPEC_MID_BAND


def spec_size_cap(base_rate_pct: float, full_spec_band: float = FULL_SPEC_BAND) -> dict:
    """Map an outside-view base rate to a max position size (% of portfolio)."""
    if base_rate_pct < 15:
        cap = SPEC_LOW_BAND
    elif base_rate_pct < 30:
        cap = SPEC_MID_BAND
    else:
        cap = full_spec_band
    return {"base_rate_pct": base_rate_pct, "max_position_pct": cap}
