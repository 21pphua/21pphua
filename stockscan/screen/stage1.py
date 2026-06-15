"""Stage-1 entry point: fetch a universe, rank it, return the survivors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from stockscan.config import DEFAULT_TOP_N
from stockscan.data.providers import DataProvider, MarketSnapshot
from stockscan.screen.factors import FactorScores, score_factors


@dataclass
class ScreenRow:
    rank: int
    ticker: str
    name: Optional[str]
    composite: float
    snapshot: MarketSnapshot
    factors: FactorScores


def screen_universe(
    tickers: Sequence[str],
    provider: DataProvider,
    top_n: int = DEFAULT_TOP_N,
    on_progress=None,
) -> list[ScreenRow]:
    """Pull snapshots for every ticker, rank by composite factor score.

    Parameters
    ----------
    tickers:
        The universe to screen.
    provider:
        A ``DataProvider`` (e.g. ``YFinanceProvider``).
    top_n:
        How many survivors to return for Stage-2 assessment.
    on_progress:
        Optional callable ``(i, n, ticker)`` for CLI progress output.
    """
    tickers = list(tickers)

    # Prefer the batched path (one price download + pooled fundamentals) when
    # the provider offers it — essential for a 500-name universe.
    bulk = getattr(provider, "bulk_snapshot", None)
    if callable(bulk):
        snapshots = bulk(tickers, on_progress=on_progress)
    else:
        snapshots = []
        n = len(tickers)
        for i, ticker in enumerate(tickers, 1):
            if on_progress:
                on_progress(i, n, ticker)
            try:
                snapshots.append(provider.snapshot(ticker))
            except Exception:  # pragma: no cover - one bad ticker shouldn't sink the run
                snapshots.append(MarketSnapshot(ticker=ticker))

    scored = score_factors(snapshots)
    order = sorted(
        zip(snapshots, scored),
        key=lambda pair: pair[1].composite,
        reverse=True,
    )

    rows: list[ScreenRow] = []
    for rank, (snap, fac) in enumerate(order, 1):
        rows.append(
            ScreenRow(
                rank=rank,
                ticker=snap.ticker,
                name=snap.name,
                composite=fac.composite,
                snapshot=snap,
                factors=fac,
            )
        )
    return rows[:top_n] if top_n else rows
