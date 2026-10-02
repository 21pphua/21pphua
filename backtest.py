"""Backtest the SAR rules over history — does the checklist actually pay?

Rules simulated (per the doc):
  * Entry at the CLOSE of a qualifying breakout day: score >= min_score,
    close above the 20-bar base, volume >= 1.3x its 20-day average, and the
    doc's stock filters (price, ADR%, $ volume) passing on that day.
  * Initial stop = breakout-day low. If a later bar trades through it, exit
    at the stop (or the open, if it gapped below).
  * At +5R sell ``partial`` (default 20%) and move the stop to breakeven.
  * Exit everything on a daily CLOSE below the 10 SMA.
  * One position per ticker at a time. Optional: skip wide-stop trades
    (stop wider than ``max_risk_adr`` average daily ranges).

Caveats, stated plainly in the report too:
  * Survivorship bias — today's ticker list excludes names that delisted.
  * Fills at the close / stop price; no slippage or commissions.
  * Entries can overlap across tickers; R-stats ignore portfolio limits.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from stockscan.config import SAR_TAKE_AT, SAR_REGIME_INDEXES
from stockscan.sar.engine import Bar, Series, score_setup, sma, min_bars

MIN_VOLX = 1.3


@dataclass
class Trade:
    ticker: str
    entry_date: str
    entry: float
    stop: float
    score: int
    risk_adr: float
    regime_ok: Optional[bool]
    trend_ok: Optional[bool] = None
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    r: float = 0.0
    hit_5r: bool = False
    bars_held: int = 0
    open: bool = False


def _regime_by_date(index_bars: Sequence[Bar]) -> dict[str, bool]:
    C = [b.close for b in index_bars]
    s10, s20 = sma(C, 10), sma(C, 20)
    return {b.date: (s10[i] > s20[i]) for i, b in enumerate(index_bars) if s20[i] is not None}


def backtest_ticker(ticker: str, bars: Sequence[Bar], min_score: int = SAR_TAKE_AT,
                    partial: float = 0.20, max_risk_adr: Optional[float] = None,
                    regime: Optional[dict[str, bool]] = None, trend_filter: bool = False) -> list[Trade]:
    S = Series(bars)
    n = len(S)
    trades: list[Trade] = []
    i = min_bars() - 1
    while i < n - 1:
        # cheap gates first; full score only on candidate breakout days
        if not (S.breaks_range(i) and S.volx(i) >= MIN_VOLX and S.passes_filters(i)[0]):
            i += 1
            continue
        s = score_setup(bars, i, ticker=ticker, series=S, with_targets=False)
        if (s.score < min_score or s.risk <= 0 or (max_risk_adr and s.risk_adr > max_risk_adr)
                or (trend_filter and s.trend_ok is False)):
            i += 1
            continue
        t = Trade(ticker, s.date, s.entry, s.stop, s.score, round(s.risk_adr, 2),
                  (regime or {}).get(s.date), s.trend_ok)
        R, stop, target, banked, left = s.risk, s.stop, s.entry + 5 * s.risk, 0.0, 1.0
        j = i + 1
        while j < n:
            o, h, l, c = S.O[j], S.H[j], S.L[j], S.C[j]
            if l <= stop:
                px = min(stop, o)
                t.exit_reason = "breakeven" if t.hit_5r else "stop"
                break
            if not t.hit_5r and h >= target:
                t.hit_5r, banked, left, stop = True, partial * 5.0, 1 - partial, t.entry
            if S.s10[j] is not None and c < S.s10[j]:
                px = c
                t.exit_reason = "10sma"
                break
            j += 1
        else:
            j, px, t.open, t.exit_reason = n - 1, S.C[n - 1], True, "open"
        t.exit_date, t.exit_price, t.bars_held = S.bars[j].date, px, j - i
        t.r = banked + left * (px - t.entry) / R
        trades.append(t)
        i = j + 1
    return trades


@dataclass
class Stats:
    trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    expectancy_r: float
    profit_factor: float
    max_consec_losses: int
    max_drawdown_r: float
    max_drawdown_pct_1pct_risk: float
    avg_bars_held: float
    hit_5r_rate: float


def summarize(trades: Sequence[Trade]) -> Optional[Stats]:
    closed = sorted((t for t in trades if not t.open), key=lambda t: t.exit_date)
    if not closed:
        return None
    wins = [t.r for t in closed if t.r > 0]
    losses = [t.r for t in closed if t.r <= 0]
    streak = worst = 0
    eq = peak = 0.0
    dd_r = 0.0
    acct = peak_acct = 1.0
    dd_pct = 0.0
    for t in closed:
        streak = streak + 1 if t.r <= 0 else 0
        worst = max(worst, streak)
        eq += t.r
        peak = max(peak, eq)
        dd_r = max(dd_r, peak - eq)
        acct *= 1 + 0.01 * t.r
        peak_acct = max(peak_acct, acct)
        dd_pct = max(dd_pct, 1 - acct / peak_acct)
    gross_loss = -sum(losses)
    return Stats(
        trades=len(closed),
        win_rate=len(wins) / len(closed),
        avg_win_r=sum(wins) / len(wins) if wins else 0.0,
        avg_loss_r=sum(losses) / len(losses) if losses else 0.0,
        expectancy_r=sum(t.r for t in closed) / len(closed),
        profit_factor=(sum(wins) / gross_loss) if gross_loss else float("inf"),
        max_consec_losses=worst,
        max_drawdown_r=dd_r,
        max_drawdown_pct_1pct_risk=dd_pct,
        avg_bars_held=sum(t.bars_held for t in closed) / len(closed),
        hit_5r_rate=sum(1 for t in closed if t.hit_5r) / len(closed),
    )


@dataclass
class BacktestResult:
    generated: str
    period: str
    tickers: int
    trades: list[Trade] = field(default_factory=list)

    def overall(self) -> Optional[Stats]:
        return summarize(self.trades)

    def by_score(self) -> list[tuple[str, Optional[Stats]]]:
        bands = [("65-74", 65, 75), ("75-84", 75, 85), ("85+", 85, 101)]
        return [(lbl, summarize([t for t in self.trades if lo <= t.score < hi])) for lbl, lo, hi in bands]

    def by_regime(self) -> list[tuple[str, Optional[Stats]]]:
        return [("favorable", summarize([t for t in self.trades if t.regime_ok is True])),
                ("unfavorable", summarize([t for t in self.trades if t.regime_ok is False]))]

    def by_trend(self) -> list[tuple[str, Optional[Stats]]]:
        return [("uptrend", summarize([t for t in self.trades if t.trend_ok is True])),
                ("counter-trend", summarize([t for t in self.trades if t.trend_ok is False]))]

    def by_stop_width(self) -> list[tuple[str, Optional[Stats]]]:
        return [("stop <= 1 ADR", summarize([t for t in self.trades if t.risk_adr <= 1.0])),
                ("stop > 1 ADR", summarize([t for t in self.trades if t.risk_adr > 1.0]))]


def run_backtest(tickers: Sequence[str], fetch: Callable[..., dict], period: str = "3y",
                 chunk: int = 200, min_score: int = SAR_TAKE_AT, partial: float = 0.20,
                 max_risk_adr: Optional[float] = None, on_progress=None,
                 trend_filter: bool = False) -> BacktestResult:
    """Fetch history chunk-by-chunk (keeps memory flat) and simulate every ticker."""
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    idx = fetch([SAR_REGIME_INDEXES[0]], period=period)
    regime = _regime_by_date(idx.get(SAR_REGIME_INDEXES[0], []))
    res = BacktestResult(datetime.now(timezone.utc).isoformat(timespec="seconds"), period, len(tickers))
    for start in range(0, len(tickers), chunk):
        batch = tickers[start:start + chunk]
        data = fetch(batch, period=period)
        for tk in batch:
            bars = data.get(tk) or []
            if len(bars) > min_bars():
                res.trades.extend(backtest_ticker(tk, bars, min_score, partial, max_risk_adr, regime, trend_filter))
        if on_progress:
            on_progress(min(start + chunk, len(tickers)), len(tickers), batch[-1])
    return res


def write_trades_csv(res: BacktestResult, path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        rows = [asdict(t) for t in res.trades]
        if not rows:
            fh.write("no trades\n")
            return
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def render_backtest(res: BacktestResult) -> str:
    def row(label: str, s: Optional[Stats]) -> str:
        if not s:
            return f"  {label:<16}{'—':>7}"
        pf = "inf" if s.profit_factor == float("inf") else f"{s.profit_factor:.2f}"
        return (f"  {label:<16}{s.trades:>7}{s.win_rate:>8.0%}{s.avg_win_r:>+9.2f}{s.avg_loss_r:>+9.2f}"
                f"{s.expectancy_r:>+8.2f}{pf:>7}{s.max_consec_losses:>8}{s.max_drawdown_pct_1pct_risk:>8.0%}")

    hdr = f"  {'':<16}{'TRADES':>7}{'WIN%':>8}{'AVG WIN':>9}{'AVG LOSS':>9}{'EXP R':>8}{'PF':>7}{'STREAK':>8}{'MAX DD':>8}"
    ov = res.overall()
    lines = ["", "SAR BACKTEST", "=" * 82,
             f"{res.tickers} tickers · period {res.period} · generated {res.generated}", ""]
    if not ov:
        lines += ["  No closed trades.", ""]
        return "\n".join(lines)
    lines += [
        "PLAIN ENGLISH",
        "-" * 82,
        f"  Out of {ov.trades} trades, {ov.win_rate:.0%} made money.",
        f"  Winners averaged {ov.avg_win_r:+.1f}R, losers {ov.avg_loss_r:+.1f}R "
        f"(R = what you risked; at 1% risk, 1R = 1% of the account).",
        f"  On average each trade made {ov.expectancy_r:+.2f}R. "
        + ("Positive = the rules made money over this period." if ov.expectancy_r > 0
           else "Negative = the rules lost money over this period."),
        f"  Worst losing streak: {ov.max_consec_losses} in a row. "
        f"Worst account drop at 1% risk: {ov.max_drawdown_pct_1pct_risk:.0%}.",
        f"  {ov.hit_5r_rate:.0%} of trades reached the 5R partial. Average hold: {ov.avg_bars_held:.0f} trading days.",
        "  The doc claims ~30% wins, ~4:1 win/loss, up to 35 losses in a row, 20-35% drawdowns.",
        "",
        "DETAIL", "-" * 82, hdr, row("All trades", ov), "",
        "  By score", *[row(l, s) for l, s in res.by_score()], "",
        "  By long-term trend (the new filter: 50/200 SMA + near 52-week high)", *[row(l, s) for l, s in res.by_trend()], "",
        "  By market (SPY 10 vs 20 SMA at entry)", *[row(l, s) for l, s in res.by_regime()], "",
        "  By stop width", *[row(l, s) for l, s in res.by_stop_width()], "",
        "CAVEATS: today's ticker list only (survivorship bias); fills at close/stop, no slippage",
        "or commissions; trades across tickers can overlap. Treat as a rough guide, not proof.", "",
    ]
    return "\n".join(lines)
