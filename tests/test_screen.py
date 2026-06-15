"""Tests for the Stage-1 quantitative screen (no network / no deps)."""

from stockscan.data.providers import MarketSnapshot
from stockscan.screen.factors import score_factors
from stockscan.screen.stage1 import screen_universe


class _FakeProvider:
    """Returns canned snapshots keyed by ticker — no network."""

    def __init__(self, snaps):
        self._snaps = {s.ticker: s for s in snaps}

    def snapshot(self, ticker):
        return self._snaps.get(ticker, MarketSnapshot(ticker=ticker))


def _snaps():
    return [
        # Strong on every factor.
        MarketSnapshot("WIN", price=100, momentum_12_1=0.40,
                       pct_above_200dma=0.20, forward_pe=15, return_on_equity=0.30,
                       volatility=0.18, name="Winner"),
        # Middling.
        MarketSnapshot("MID", price=50, momentum_12_1=0.05,
                       pct_above_200dma=0.0, forward_pe=25, return_on_equity=0.12,
                       volatility=0.28, name="Middle"),
        # Weak on every factor.
        MarketSnapshot("LAG", price=10, momentum_12_1=-0.20,
                       pct_above_200dma=-0.15, forward_pe=60, return_on_equity=0.02,
                       volatility=0.55, name="Laggard"),
    ]


def test_factor_zscores_have_zero_mean():
    scored = score_factors(_snaps())
    for factor in ("momentum", "trend", "value", "quality", "low_volatility"):
        col = [s.z[factor] for s in scored]
        assert abs(sum(col)) < 1e-9


def test_ranking_orders_strong_above_weak():
    rows = screen_universe(["WIN", "MID", "LAG"], _FakeProvider(_snaps()), top_n=3)
    assert [r.ticker for r in rows] == ["WIN", "MID", "LAG"]
    assert rows[0].composite > rows[-1].composite


def test_top_n_truncates():
    rows = screen_universe(["WIN", "MID", "LAG"], _FakeProvider(_snaps()), top_n=1)
    assert len(rows) == 1
    assert rows[0].ticker == "WIN"


def test_missing_data_is_neutral_not_fatal():
    snaps = _snaps() + [MarketSnapshot("UNKNOWN")]  # all fields None
    rows = screen_universe(
        ["WIN", "MID", "LAG", "UNKNOWN"], _FakeProvider(snaps), top_n=4
    )
    # The all-missing name should land near the middle (neutral z=0), not crash.
    tickers = [r.ticker for r in rows]
    assert "UNKNOWN" in tickers
    assert tickers[0] == "WIN"


def test_earnings_yield_derived_from_forward_pe():
    s = MarketSnapshot("X", forward_pe=20)
    assert abs(s.earnings_yield - 0.05) < 1e-9
    assert MarketSnapshot("Y", forward_pe=None).earnings_yield is None
    assert MarketSnapshot("Z", forward_pe=-5).earnings_yield is None
