"""Universe scan for SAR breakout setups.

Pipeline:
  1. Batched daily OHLCV download (yfinance, chunked).
  2. Cheap stock filters (price, ADR%, $ volume) drop most of the universe.
  3. Score the latest bar of every survivor with the SAR checklist.
  4. Split into BREAKOUTS (score >= min_score, range broken) and COILING
     (setup formed, close within a few % of the base high — set alerts).
  5. Market-regime check on SPY / QQQ.

Run it after the close: the checklist is defined on completed daily bars.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from stockscan.config import SAR_TAKE_AT, SAR_REGIME_INDEXES, SAR_EARNINGS_WARN_DAYS
from stockscan.sar.engine import (
    Bar, SetupScore, passes_filters, score_setup, market_regime,
)

Fetcher = Callable[..., dict]


def fetch_ohlcv(tickers: Sequence[str], period: str = "9mo", chunk: int = 200,
                on_progress=None, **_) -> dict[str, list[Bar]]:
    """Daily OHLCV for many tickers via yfinance, in batched chunks."""
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError("yfinance is required. Install with: pip install 'stockscan[data]'") from exc

    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    out: dict[str, list[Bar]] = {}
    for start in range(0, len(tickers), chunk):
        batch = tickers[start:start + chunk]
        try:
            df = yf.download(batch, period=period, interval="1d", auto_adjust=True,
                             group_by="ticker", threads=True, progress=False)
        except Exception:  # pragma: no cover - network resilience
            df = None
        for tk in batch:
            bars: list[Bar] = []
            if df is not None and not df.empty:
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        sub = df[tk] if tk in df.columns.get_level_values(0) else None
                    else:
                        sub = df
                    if sub is not None:
                        sub = sub.dropna(subset=["Open", "High", "Low", "Close"])
                        for ts, r in sub.iterrows():
                            bars.append(Bar(ts.strftime("%Y-%m-%d"), float(r["Open"]), float(r["High"]),
                                            float(r["Low"]), float(r["Close"]), float(r.get("Volume", 0) or 0)))
                except Exception:  # pragma: no cover
                    bars = []
            out[tk] = bars
        if on_progress:
            done = min(start + chunk, len(tickers))
            on_progress(done, len(tickers), batch[-1])
    return out


@dataclass
class SarScanResult:
    generated: str
    scanned: int
    with_data: int
    passed_filters: int
    regime: dict[str, Optional[bool]]
    breakouts: list[SetupScore] = field(default_factory=list)
    coiling: list[SetupScore] = field(default_factory=list)
    bars: dict[str, list[Bar]] = field(default_factory=dict)

    @property
    def regime_ok(self) -> Optional[bool]:
        vals = [v for v in self.regime.values() if v is not None]
        return all(vals) if vals else None


# The doc's breakout rule needs real volume: below this multiple of the 20-day
# average, a range break is listed as COILING (not confirmed), not BREAKOUT.
MIN_BREAKOUT_VOLX = 1.3


def _session_open_today() -> Optional[str]:
    """Today's date (US/Eastern) if the regular session hasn't closed yet, else None."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:  # pragma: no cover
        return None
    if now.weekday() < 5 and (now.hour, now.minute) < (16, 15):
        return now.strftime("%Y-%m-%d")
    return None


def drop_partial_bar(bars: list[Bar], today: Optional[str]) -> list[Bar]:
    """Mid-session the last bar is incomplete (volume, close) — score the prior close instead."""
    return bars[:-1] if today and bars and bars[-1].date == today else bars


def breakout_volx(bars: Sequence[Bar]) -> float:
    w = bars[-20:]
    avg = sum(b.volume for b in w) / len(w) if w else 0
    return bars[-1].volume / avg if avg else 0.0


def lookup_earnings(tickers: Sequence[str], max_workers: int = 8) -> dict[str, Optional[str]]:
    """Next earnings date (YYYY-MM-DD) per ticker via yfinance; None when unknown."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date

    def one(tk: str) -> Optional[str]:
        try:
            cal = yf.Ticker(tk).calendar
            ds = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if ds is None and cal is not None and hasattr(cal, "loc"):
                ds = list(cal.loc["Earnings Date"])
            if not isinstance(ds, (list, tuple)):
                ds = [ds] if ds else []
            future = sorted(str(d)[:10] for d in ds if d and str(d)[:10] >= date.today().isoformat())
            return future[0] if future else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return dict(zip(tickers, ex.map(one, tickers)))


def _attach_earnings(setups: Sequence[SetupScore], dates: dict[str, Optional[str]]) -> None:
    from datetime import date
    for s in setups:
        d = dates.get(s.ticker)
        if d:
            s.earnings_date = d
            try:
                s.days_to_earnings = (date.fromisoformat(d) - date.today()).days
            except ValueError:
                pass


def run_sar_scan(tickers: Sequence[str], fetch: Fetcher = fetch_ohlcv, min_score: int = SAR_TAKE_AT,
                 top: int = 25, apply_filters: bool = True, on_progress=None,
                 today: Optional[str] = "auto", earnings=lookup_earnings) -> SarScanResult:
    tickers = list(dict.fromkeys(t.upper() for t in tickers))
    today = _session_open_today() if today == "auto" else today
    data = {k: drop_partial_bar(v, today) for k, v in fetch(tickers, on_progress=on_progress).items()}
    idx = {k: drop_partial_bar(v, today) for k, v in fetch(list(SAR_REGIME_INDEXES)).items()}
    regime = {k: market_regime(idx.get(k, [])) for k in SAR_REGIME_INDEXES}

    with_data = passed = 0
    breakouts: list[SetupScore] = []
    coiling: list[SetupScore] = []
    for tk in tickers:
        bars = data.get(tk) or []
        if not bars:
            continue
        with_data += 1
        if apply_filters:
            ok, _ = passes_filters(bars)
            if not ok:
                continue
        try:
            s = score_setup(bars, ticker=tk)
        except ValueError:
            continue
        passed += 1
        if s.is_breakout and s.score >= min_score and breakout_volx(bars) >= MIN_BREAKOUT_VOLX:
            breakouts.append(s)
        elif s.is_coiling or (s.is_breakout and s.score >= min_score):  # low-volume break = unconfirmed
            coiling.append(s)

    breakouts.sort(key=lambda s: s.score, reverse=True)
    coiling.sort(key=lambda s: (s.prep_points, s.gap_to_base), reverse=True)
    breakouts, coiling = breakouts[:top], coiling[:top]
    keep = {s.ticker for s in breakouts + coiling}
    if earnings and keep:
        _attach_earnings(breakouts + coiling, earnings(sorted(keep)))
    return SarScanResult(
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        scanned=len(tickers), with_data=with_data, passed_filters=passed, regime=regime,
        breakouts=breakouts, coiling=coiling, bars={t: data[t] for t in keep},
    )


def _setup_json(s: SetupScore, kind: str, bars: list[Bar], keep_bars: int = 130) -> dict:
    d = asdict(s)
    d["kind"] = kind
    d["risk_adr"] = round(s.risk_adr, 2)
    d["wide_stop"] = s.wide_stop
    d["earnings_soon"] = s.days_to_earnings is not None and 0 <= s.days_to_earnings <= SAR_EARNINGS_WARN_DAYS
    d["steps"] = [{**asdict(st), "status": st.status} for st in s.steps]
    d["bars"] = [[b.date, round(b.open, 4), round(b.high, 4), round(b.low, 4), round(b.close, 4), int(b.volume)]
                 for b in bars[-keep_bars:]]
    return d


def write_shortlist(result: SarScanResult, path: str) -> None:
    """JSON the web walkthrough can load ("Load scan file")."""
    doc = {
        "format": "sar-shortlist/1",
        "generated": result.generated,
        "scanned": result.scanned,
        "passed_filters": result.passed_filters,
        "regime": result.regime,
        "results": [_setup_json(s, "breakout", result.bars[s.ticker]) for s in result.breakouts]
                   + [_setup_json(s, "coiling", result.bars[s.ticker]) for s in result.coiling],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
