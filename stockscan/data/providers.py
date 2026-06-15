"""Data providers.

Hybrid model: quantitative fields are auto-pulled here; the qualitative CORE
subscores are drafted by the LLM and confirmed by you (see research/).

The default provider is yfinance (free, no key). The ``DataProvider``
interface is deliberately small so a paid feed (Polygon / FMP / Alpha Vantage)
can be dropped in later without touching the screen or the engine.

For screening a large universe (e.g. the S&P 500), ``bulk_snapshot`` does one
batched price download plus a thread-pooled fundamentals fetch — far faster
than calling ``snapshot`` 500 times.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence


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


def price_factors(closes: Sequence[float]) -> dict:
    """Compute price-based factors from a series of adjusted closes.

    Pure function (no pandas) so it's unit-testable offline and shared by the
    single-name and bulk paths. Returns price / momentum_12_1 /
    pct_above_200dma / volatility, with ``None`` where there's too little data.
    """
    from math import sqrt

    closes = [float(c) for c in closes if c is not None]
    out = {"price": None, "momentum_12_1": None, "pct_above_200dma": None, "volatility": None}
    if not closes:
        return out

    out["price"] = closes[-1]

    if len(closes) >= 252:
        p_12mo = closes[-252]
        p_1mo = closes[-21]
        if p_12mo > 0:
            out["momentum_12_1"] = p_1mo / p_12mo - 1.0

    if len(closes) >= 200:
        dma200 = sum(closes[-200:]) / 200.0
        if dma200 > 0:
            out["pct_above_200dma"] = out["price"] / dma200 - 1.0

    if len(closes) >= 30:
        rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes)) if closes[i - 1] > 0]
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / len(rets)
            out["volatility"] = sqrt(var) * sqrt(252)

    return out


class YFinanceProvider:
    """Free provider backed by the ``yfinance`` library.

    Install with ``pip install 'stockscan[data]'``.

    Note: requires network egress to ``query1.finance.yahoo.com`` and
    ``query2.finance.yahoo.com``.
    """

    def __init__(self, max_workers: int = 8) -> None:
        try:
            import yfinance  # noqa: F401
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "yfinance is required for the YFinanceProvider. "
                "Install it with: pip install 'stockscan[data]'"
            ) from exc
        self.max_workers = max_workers

    # --- fundamentals (one ticker's .info) -----------------------------------

    @staticmethod
    def _info(ticker: str) -> dict:
        import yfinance as yf

        try:
            return yf.Ticker(ticker).info or {}
        except Exception:  # pragma: no cover - network/parse resilience
            return {}

    @staticmethod
    def _from_info(ticker: str, info: dict, pf: dict) -> MarketSnapshot:
        price = pf.get("price") or info.get("currentPrice") or info.get("regularMarketPrice")
        return MarketSnapshot(
            ticker=ticker,
            price=price,
            momentum_12_1=pf.get("momentum_12_1"),
            pct_above_200dma=pf.get("pct_above_200dma"),
            forward_pe=info.get("forwardPE"),
            return_on_equity=info.get("returnOnEquity"),
            volatility=pf.get("volatility"),
            name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
        )

    # --- single name ---------------------------------------------------------

    def snapshot(self, ticker: str) -> MarketSnapshot:
        import yfinance as yf

        pf = {"price": None, "momentum_12_1": None, "pct_above_200dma": None, "volatility": None}
        try:
            hist = yf.Ticker(ticker).history(period="13mo", interval="1d", auto_adjust=True)
            pf = price_factors(list(hist["Close"].dropna()))
        except Exception:  # pragma: no cover - network/parse resilience
            pass
        return self._from_info(ticker, self._info(ticker), pf)

    # --- bulk (for screening a universe) -------------------------------------

    def bulk_snapshot(self, tickers: Sequence[str], on_progress=None) -> list[MarketSnapshot]:
        """One batched price download + thread-pooled fundamentals."""
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor, as_completed

        tickers = list(tickers)
        n = len(tickers)

        # 1. Batched price history for every name in one request.
        closes_by_ticker: dict[str, list[float]] = {}
        try:
            df = yf.download(
                tickers, period="13mo", interval="1d", auto_adjust=True,
                group_by="ticker", threads=True, progress=False,
            )
            for tk in tickers:
                try:
                    if len(tickers) == 1:
                        series = df["Close"]
                    else:
                        series = df[tk]["Close"]
                    closes_by_ticker[tk] = [float(c) for c in series.dropna().tolist()]
                except Exception:
                    closes_by_ticker[tk] = []
        except Exception:  # pragma: no cover - network/parse resilience
            closes_by_ticker = {tk: [] for tk in tickers}

        # 2. Thread-pooled fundamentals (.info is the slow part).
        infos: dict[str, dict] = {}
        done = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(self._info, tk): tk for tk in tickers}
            for fut in as_completed(futs):
                tk = futs[fut]
                infos[tk] = fut.result()
                done += 1
                if on_progress:
                    on_progress(done, n, tk)

        return [
            self._from_info(tk, infos.get(tk, {}), price_factors(closes_by_ticker.get(tk, [])))
            for tk in tickers
        ]


def get_provider(name: str = "yfinance", **kwargs) -> DataProvider:
    """Factory. Today only yfinance; the seam where a paid feed plugs in."""
    if name == "yfinance":
        return YFinanceProvider(**kwargs)
    raise ValueError(
        f"Unknown data provider: {name!r}. Available: 'yfinance'. "
        "A paid provider (Polygon/FMP/Alpha Vantage) can be added here."
    )
