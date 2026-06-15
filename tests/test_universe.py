"""Tests for universe resolution and price-factor math (no network)."""

import pytest

from stockscan.universe import resolve_universe, list_builtin_universes
from stockscan.data.providers import price_factors


def test_builtin_universes_present():
    names = list_builtin_universes()
    assert "sp500" in names
    assert "dow30" in names


def test_sp500_resolves_to_real_list():
    tickers = resolve_universe("sp500")
    assert len(tickers) > 450          # ~500 constituents
    assert "AAPL" in tickers
    assert "BRK-B" in tickers          # normalised from BRK.B for Yahoo


def test_dow30_has_30():
    assert len(resolve_universe("dow30")) == 30


def test_name_is_case_insensitive():
    assert resolve_universe("SP500") == resolve_universe("sp500")


def test_file_path_wins(tmp_path):
    f = tmp_path / "my.txt"
    f.write_text("# comment\nAAPL\nmsft\n\nNVDA\n")
    assert resolve_universe(str(f)) == ["AAPL", "MSFT", "NVDA"]


def test_unknown_name_raises():
    with pytest.raises(ValueError):
        resolve_universe("not_a_real_universe")


# --- price-factor math -------------------------------------------------------

def test_price_factors_empty():
    out = price_factors([])
    assert out["price"] is None
    assert out["momentum_12_1"] is None


def test_price_factors_uptrend():
    closes = [100 + i for i in range(260)]  # steady climb
    out = price_factors(closes)
    assert out["price"] == closes[-1]
    assert out["momentum_12_1"] > 0          # up over the year
    assert out["pct_above_200dma"] > 0       # above its average
    assert out["volatility"] is not None and out["volatility"] >= 0


def test_price_factors_short_series_partial():
    out = price_factors([10, 11, 12])  # too short for momentum/trend
    assert out["price"] == 12
    assert out["momentum_12_1"] is None
    assert out["pct_above_200dma"] is None
