"""Data providers.

Hybrid model: quantitative fields are auto-pulled here; the qualitative CORE
subscores are drafted by the LLM and confirmed by you (see research/).

The default provider is yfinance (free, no key). The ``DataProvider``
interface is deliberately small so a paid feed (Polygon / FMP / Alpha Vantage)
can be dropped in later without touching the screen or the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class MarketSnapshot:
    """The quantitative inputs the Stage-1 screen needs for one ticker.

    Any field may be ``None`` when the provider can't supply it; the screen
    handles missing factors by neutralising them (z-score 0).
    """

    ticker: str
    price: Optional[float] = None
    momentum_12_1: Optional[float] = None   # 12-month return excluding last month
    pct_above_200dma: Optional[float] = None  # (price / 200dma - 1)
    forward_pe: Optional[float] = None
    return_on_equity: Optional[float] = None
    volatility: Optional[float] = None       # annualised daily-return stdev
    name: Optional[str] = None
    sector: Optional[str] = None

    @property
    def earnings_yield(self) -> Optional[float]:
        if self.forward_pe and self.forward_pe > 0:
            return 1.0 / self.forward_pe
        return None


class DataProvider(Protocol):
    """Minimal interface every provider implements."""

    def snapshot(self, ticker: str) -> MarketSnapshot: ...


class YFinanceProvider:
    """Free provider backed by the ``yfinance`` library.

    Install with ``pip install 'stockscan[data]'``.
    """

    def __init__(self) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "yfinance is required for the YFinanceProvider. "
                "Install it with: pip install 'stockscan[data]'"
            ) from exc

    def snapshot(self, ticker: str) -> MarketSnapshot:
        import numpy as np
        import yfinance as yf

        t = yf.Ticker(ticker)
        info = {}
        try:
            info = t.info or {}
        except Exception:  # pragma: no cover - network/parse resilience
            info = {}

        # Price history for momentum, trend, volatility.
        momentum = pct_200 = vol = price = None
        try:
            hist = t.history(period="13mo", interval="1d", auto_adjust=True)
            closes = hist["Close"].dropna()
            if len(closes) > 0:
                price = float(closes.iloc[-1])
            if len(closes) >= 252:
                # 12-1 momentum: return from ~12mo ago to ~1mo ago.
                p_12mo = float(closes.iloc[-252])
                p_1mo = float(closes.iloc[-21])
                if p_12mo > 0:
                    momentum = p_1mo / p_12mo - 1.0
            if len(closes) >= 200:
                dma200 = float(closes.iloc[-200:].mean())
                if dma200 > 0 and price is not None:
                    pct_200 = price / dma200 - 1.0
            if len(closes) >= 30:
                daily_ret = closes.pct_change().dropna()
                vol = float(daily_ret.std() * np.sqrt(252))
        except Exception:  # pragma: no cover - network/parse resilience
            pass

        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")

        return MarketSnapshot(
            ticker=ticker,
            price=price,
            momentum_12_1=momentum,
            pct_above_200dma=pct_200,
            forward_pe=info.get("forwardPE"),
            return_on_equity=info.get("returnOnEquity"),
            volatility=vol,
            name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
        )


def get_provider(name: str = "yfinance") -> DataProvider:
    """Factory. Today only yfinance; the seam where a paid feed plugs in."""
    if name == "yfinance":
        return YFinanceProvider()
    raise ValueError(
        f"Unknown data provider: {name!r}. Available: 'yfinance'. "
        "A paid provider (Polygon/FMP/Alpha Vantage) can be added here."
    )
