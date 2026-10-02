"""Tests for the SAR breakout scanner (offline — synthetic bars, fake fetcher)."""

import json
import random

from stockscan.sar.engine import Bar, score_setup, passes_filters, market_regime, sma
from stockscan.sar.scan import run_sar_scan, write_shortlist


def _bars(phases, seed=11, start_price=9.6, base_vol=1.4e6):
    """Build a deterministic series. phase = (drift, vol_mult, range) or 'BO'."""
    rnd = random.Random(seed)
    bars, p = [], start_price
    for n, ph in enumerate(phases):
        date = f"2026-{1 + n // 28:02d}-{1 + n % 28:02d}"
        if ph == "BO":
            hi20 = max(b.high for b in bars[-20:])
            o, c = p * 1.004, hi20 * 1.03
            h, l, vm = c * 1.004, min(o, p) * 0.985, 3.4
        else:
            dr, vm, rg = ph
            o = p * (1 + (rnd.random() - 0.5) * rg * 0.3)
            c = p * (1 + dr + (rnd.random() - 0.5) * rg * 0.55)
            h = max(o, c) * (1 + rg * (0.15 + 0.3 * rnd.random()))
            l = min(o, c) * (1 - rg * (0.15 + 0.3 * rnd.random()))
        bars.append(Bar(date, o, h, l, c, base_vol * vm * (0.8 + 0.4 * rnd.random())))
        p = c
    return bars


def textbook(breakout=True):
    ph = [(0, 1.0, 0.06)] * 30 + [(0.019, 2.1, 0.075)] * 24
    ph += [((-0.003 if i < 9 else 0.002), 0.6 - i * 0.014, 0.062 - i * 0.0016) for i in range(18)]
    if breakout:
        ph.append("BO")
    return _bars(ph)


def flat():
    return _bars([(0, 1.0, 0.06)] * 80, seed=3)


def test_sma_matches_naive():
    v = [float(x) for x in range(1, 31)]
    s = sma(v, 10)
    assert s[8] is None and abs(s[9] - 5.5) < 1e-9 and abs(s[-1] - 25.5) < 1e-9


def test_textbook_breakout_scores_take():
    s = score_setup(textbook(), ticker="TXT")
    assert s.is_breakout
    assert s.verdict == "Take", s.score
    assert s.steps[0].status == "met"          # run-up
    assert s.steps[4].status == "met"          # range break
    assert s.steps[5].points >= 15             # breakout volume weighted heavily


def test_weights_sum_to_100():
    s = score_setup(textbook())
    assert sum(st.max_points for st in s.steps) == 100


def test_flat_series_scores_low():
    s = score_setup(flat())
    assert s.verdict == "Skip", s.score
    assert s.steps[0].frac < 0.8


def test_coiling_detected_before_breakout():
    s = score_setup(textbook(breakout=False))
    assert not s.is_breakout
    assert s.prep_points >= 25


def test_targets_and_stop():
    s = score_setup(textbook())
    labels = [t.label for t in s.targets]
    assert "5R partial" in labels and "Measured move" in labels and labels[-1] == "Stop"
    five_r = next(t for t in s.targets if t.label == "5R partial")
    assert abs(five_r.price - (s.entry + 5 * s.risk)) < 1e-9
    assert s.stop < s.entry


def _wide(price=20.0, vol=1e6, n=70):
    # ~10.5% ADR, $20M/day at the defaults
    return [Bar(str(i), price, price * 1.05, price * 0.95, price, vol) for i in range(n)]


def test_filters():
    assert passes_filters(_wide())[0]
    assert passes_filters(_wide(price=0.8, vol=1e8))[1] == "price"
    assert passes_filters(_wide(vol=1e5))[1] == "dollar volume"
    tight = [Bar(b.date, b.open, b.close * 1.01, b.close * 0.99, b.close, b.volume) for b in _wide()]
    assert passes_filters(tight)[1] == "adr"
    assert not passes_filters(_wide(n=40))[0]


def test_market_regime():
    up = [Bar(str(i), 100 + i, 101 + i, 99 + i, 100 + i, 1e6) for i in range(30)]
    down = [Bar(str(i), 130 - i, 131 - i, 129 - i, 130 - i, 1e6) for i in range(30)]
    assert market_regime(up) is True
    assert market_regime(down) is False
    assert market_regime(up[:5]) is None


def test_run_scan_with_fake_fetcher(tmp_path):
    universe = {"BRK": textbook(), "COIL": textbook(breakout=False), "FLAT": flat(), "NODATA": []}
    up = [Bar(str(i), 100 + i, 101 + i, 99 + i, 100 + i, 1e6) for i in range(30)]

    def fake_fetch(tickers, on_progress=None, **_):
        return {t: (up if t in ("SPY", "QQQ") else universe.get(t, [])) for t in tickers}

    res = run_sar_scan(list(universe), fetch=fake_fetch, min_score=65, apply_filters=False,
                       today=None, earnings=lambda tks: {"BRK": "2099-01-01"})
    assert [s.ticker for s in res.breakouts] == ["BRK"]
    assert "FLAT" not in [s.ticker for s in res.breakouts + res.coiling]
    assert res.regime_ok is True
    assert res.with_data == 3

    out = tmp_path / "shortlist.json"
    write_shortlist(res, str(out))
    doc = json.loads(out.read_text())
    assert doc["format"] == "sar-shortlist/1"
    first = doc["results"][0]
    assert first["ticker"] == "BRK" and first["kind"] == "breakout"
    assert len(first["bars"][0]) == 6 and len(first["steps"]) == 7
    assert first["earnings_date"] == "2099-01-01" and first["earnings_soon"] is False
    assert "risk_adr" in first and "wide_stop" in first


# --- risk / ADR -------------------------------------------------------------

def test_risk_adr():
    s = score_setup(textbook())
    assert s.risk_adr > 0
    assert s.wide_stop == (s.risk_adr > 1.0)


# --- backtest ---------------------------------------------------------------

from stockscan.sar import engine as _engine
from stockscan.sar.backtest import backtest_ticker, summarize, run_backtest, render_backtest


def _phases_textbook():
    ph = [(0, 1.0, 0.06)] * 30 + [(0.019, 2.1, 0.075)] * 24
    ph += [((-0.003 if i < 9 else 0.002), 0.6 - i * 0.014, 0.062 - i * 0.0016) for i in range(18)]
    return ph + ["BO"]


def _loosen(monkeypatch):
    monkeypatch.setattr(_engine, "SAR_MIN_ADR", 0.0)
    monkeypatch.setattr(_engine, "SAR_MIN_DOLLAR_VOL", 0.0)


def test_backtest_winner_exits_on_10sma(monkeypatch):
    _loosen(monkeypatch)
    bars = _bars(_phases_textbook() + [(0.03, 1.4, 0.04)] * 15 + [(-0.04, 1.0, 0.04)] * 10)
    bo_date = bars[72].date
    trades = backtest_ticker("T", bars, min_score=65)
    bo = [t for t in trades if t.entry_date == bo_date]
    assert bo, [t.entry_date for t in trades]
    tr = bo[0]
    assert not tr.open and tr.exit_reason in ("10sma", "breakeven")
    assert tr.r > 0


def test_backtest_stopped_out(monkeypatch):
    _loosen(monkeypatch)
    bars = _bars(_phases_textbook() + [(-0.15, 1.0, 0.05)] + [(0, 1.0, 0.05)] * 5)
    bo_date = bars[72].date
    tr = [t for t in backtest_ticker("T", bars, min_score=65) if t.entry_date == bo_date][0]
    assert tr.exit_reason == "stop"
    assert tr.r <= -0.99


def test_summarize_and_render(monkeypatch):
    _loosen(monkeypatch)
    win = _bars(_phases_textbook() + [(0.03, 1.4, 0.04)] * 15 + [(-0.04, 1.0, 0.04)] * 10)
    lose = _bars(_phases_textbook() + [(-0.15, 1.0, 0.05)] + [(0, 1.0, 0.05)] * 5)
    spy = [Bar(b.date, 100 + i, 101 + i, 99 + i, 100 + i, 1e6) for i, b in enumerate(win)]

    def fake_fetch(tickers, period=None, **_):
        d = {"WIN": win, "LOSE": lose, "SPY": spy}
        return {t: d.get(t, []) for t in tickers}

    res = run_backtest(["WIN", "LOSE"], fake_fetch, min_score=65)
    st = summarize(res.trades)
    assert st and st.trades >= 2
    assert 0 < st.win_rate < 1
    assert st.max_consec_losses >= 1
    text = render_backtest(res)
    assert "PLAIN ENGLISH" in text and "made money" in text
