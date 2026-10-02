"""SAR Trading breakout-setup scoring engine (pure Python, no deps).

"SAR" here is the SAR Trading educator's system, NOT the Parabolic SAR
indicator. The checklist (daily chart):

  01  30%+ run-up over days/weeks before the pullback
  02  10/20 SMA inclining (10 rising, above a rising 20)
  03  Orderly pullback with a tightening range
  04  Volume drying up during the pullback
  05a Close breaks the pullback range
  05b ...on high volume
  05c ...closing near the high of day

Each item earns partial credit (0..1) times its weight; weights sum to 100.
The weighting is this tool's own (breakout volume + range break heaviest) —
the source docs don't specify points. Scoring mirrors the web walkthrough
(SAR Setup Walkthrough.dc.html) so a name scores the same in both.

Educational decision framework, not financial advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from stockscan.config import (
    SAR_RUNUP_LOOKBACK,
    SAR_PULLBACK_LOOKBACK,
    SAR_WEIGHTS,
    SAR_TAKE_AT,
    SAR_WATCH_AT,
    SAR_MIN_PRICE,
    SAR_MIN_ADR,
    SAR_MIN_DOLLAR_VOL,
    SAR_COIL_MIN_PREP,
    SAR_COIL_MAX_GAP,
)


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StepScore:
    key: str
    title: str
    frac: float      # 0..1 partial credit
    points: int
    max_points: int
    metric: str

    @property
    def status(self) -> str:
        return "met" if self.frac >= 0.8 else "partial" if self.frac >= 0.4 else "missing"


@dataclass
class Target:
    label: str
    price: float
    r_multiple: float
    note: str = ""


@dataclass
class SetupScore:
    ticker: str
    date: str
    score: int
    verdict: str            # "Take" | "Watch" | "Skip"
    steps: list[StepScore]
    entry: float
    stop: float
    base_high: float
    base_low: float
    run_low: float
    run_high: float
    runup_pct: float
    adr_pct: float
    dollar_vol: float
    sma10: Optional[float]
    targets: list[Target] = field(default_factory=list)

    @property
    def risk(self) -> float:
        return self.entry - self.stop

    @property
    def is_breakout(self) -> bool:
        return self.entry > self.base_high

    @property
    def prep_points(self) -> int:
        """Points from steps 01-04 (the setup forming, before any breakout)."""
        return sum(s.points for s in self.steps[:4])

    @property
    def gap_to_base(self) -> float:
        """Fractional distance from close to the base high (negative = below)."""
        return self.entry / self.base_high - 1.0 if self.base_high else 0.0

    @property
    def is_coiling(self) -> bool:
        """Setup is formed but hasn't broken out: strong 01-04, close just under the base."""
        return (not self.is_breakout
                and self.prep_points >= SAR_COIL_MIN_PREP
                and self.gap_to_base >= -SAR_COIL_MAX_GAP)


STEP_TITLES = [
    ("runup", "30%+ run-up"),
    ("sma", "10/20 SMA inclining"),
    ("tighten", "Tightening pullback"),
    ("dryup", "Volume dries up"),
    ("rangebreak", "Breaks the range"),
    ("breakvol", "On high volume"),
    ("nearhod", "Closes near the high"),
]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _round_half_up(x: float) -> int:
    return int(x + 0.5)


def sma(values: Sequence[float], period: int) -> list[Optional[float]]:
    out: list[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def min_bars() -> int:
    return SAR_RUNUP_LOOKBACK + SAR_PULLBACK_LOOKBACK + 1


def adr_pct(bars: Sequence[Bar], i: Optional[int] = None, n: int = 20) -> float:
    i = len(bars) - 1 if i is None else i
    w = bars[max(0, i - n + 1): i + 1]
    return sum(b.high / b.low - 1 for b in w if b.low > 0) / len(w) if w else 0.0


def dollar_volume(bars: Sequence[Bar], i: Optional[int] = None, n: int = 20) -> float:
    i = len(bars) - 1 if i is None else i
    w = bars[max(0, i - n + 1): i + 1]
    return sum(b.close * b.volume for b in w) / len(w) if w else 0.0


def passes_filters(bars: Sequence[Bar]) -> tuple[bool, str]:
    """The doc's stock filters: price > $1, ADR% > 5, avg $ volume > $3.5M."""
    if len(bars) < min_bars():
        return False, f"only {len(bars)} bars"
    if bars[-1].close <= SAR_MIN_PRICE:
        return False, "price"
    if adr_pct(bars) <= SAR_MIN_ADR:
        return False, "adr"
    if dollar_volume(bars) <= SAR_MIN_DOLLAR_VOL:
        return False, "dollar volume"
    return True, ""


def _swing_highs(H: Sequence[float], focus: int, above: float, k: int = 3) -> list[float]:
    last = len(H) - 1
    out = []
    for j in range(k, last - k + 1):
        if focus - 2 <= j <= focus:
            continue
        if all(H[j] >= H[j - d] and H[j] >= H[j + d] for d in range(1, k + 1)) and H[j] > above:
            out.append(H[j])
    return sorted(out)


def score_setup(bars: Sequence[Bar], i: Optional[int] = None, ticker: str = "",
                take_at: int = SAR_TAKE_AT, watch_at: int = SAR_WATCH_AT) -> SetupScore:
    """Score bar ``i`` (default: latest) as a potential SAR breakout day."""
    n = len(bars)
    i = n - 1 if i is None else i
    RL, PL = SAR_RUNUP_LOOKBACK, SAR_PULLBACK_LOOKBACK
    if i < RL + PL:
        raise ValueError(f"need at least {RL + PL + 1} bars before the scored bar (have {i + 1})")

    C = [b.close for b in bars]
    H = [b.high for b in bars]
    L = [b.low for b in bars]
    V = [b.volume for b in bars]
    s10, s20, av20 = sma(C, 10), sma(C, 20), sma(V, 20)

    # 01 run-up: largest low->high rise in the window before the base.
    ws, we = max(0, i - RL - PL), i - PL
    min_c, min_i, best, low_i, high_i = float("inf"), ws, 0.0, ws, ws
    for k in range(ws, we + 1):
        if C[k] < min_c:
            min_c, min_i = C[k], k
        g = C[k] / min_c - 1
        if g > best:
            best, low_i, high_i = g, min_i, k
    run_low, run_high = L[low_i], max(H[low_i: we + 1])
    f1 = _clamp(best / 0.30)

    # 02 SMA incline.
    sl10, sl20 = s10[i] - s10[i - 5], s20[i] - s20[i - 5]
    f2 = (0.4 if sl10 > 0 else 0) + (0.4 if s10[i] > s20[i] else 0) + (0.2 if sl20 > 0 else 0)

    # 03 tightening base: 2nd-half avg range vs 1st-half.
    base = list(range(i - PL, i))
    half = PL // 2
    rg = [(H[k] - L[k]) / C[k] for k in base]
    r1, r2 = sum(rg[:half]) / half, sum(rg[half:]) / (PL - half)
    tight = r2 / r1 if r1 else 1.0
    f3 = _clamp((1 - tight) / 0.4)
    base_high, base_low = max(H[k] for k in base), min(L[k] for k in base)

    # 04 volume dry-up: base avg vs run-up window avg.
    p_avg = sum(V[k] for k in base) / PL
    ev = V[max(0, i - PL - RL): i - PL]
    e_avg = sum(ev) / len(ev) if ev else p_avg
    dry = p_avg / e_avg if e_avg else 1.0
    f4 = _clamp((1 - dry) / 0.3)

    # 05a range break.
    gap = (C[i] - base_high) / base_high
    f5 = 1.0 if gap > 0 else _clamp(1 + gap / 0.05) * 0.5

    # 05b breakout volume.
    volx = V[i] / av20[i] if av20[i] else 0.0
    f6 = _clamp((volx - 1) / 0.8)

    # 05c close near high of day.
    pos = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 1.0
    f7 = _clamp((pos - 0.5) / 0.45)

    fracs = [f1, f2, f3, f4, f5, f6, f7]
    metrics = [
        f"{best:+.1%} {bars[low_i].date}->{bars[high_i].date}",
        f"10 {s10[i]:.2f} / 20 {s20[i]:.2f}",
        f"range {r1:.1%}->{r2:.1%}",
        f"{dry:.0%} of run-up vol",
        f"close {C[i]:.2f} vs base {base_high:.2f}",
        f"{volx:.2f}x avg vol",
        f"close at {pos:.0%} of range",
    ]
    steps = [
        StepScore(key, title, fr, _round_half_up(fr * w), w, m)
        for (key, title), fr, w, m in zip(STEP_TITLES, fracs, SAR_WEIGHTS, metrics)
    ]
    score = sum(s.points for s in steps)
    verdict = "Take" if score >= take_at else "Watch" if score >= watch_at else "Skip"

    entry, stop = C[i], L[i]
    R = entry - stop
    adr = adr_pct(bars, i)
    sma10_last = s10[-1]
    rm = (lambda p: (p - entry) / R) if R > 0 else (lambda p: 0.0)

    targets: list[Target] = []
    if R > 0:
        targets.append(Target("5R partial", entry + 5 * R, 5.0, "sell 10-30%, stop to breakeven"))
    mm = base_high + (run_high - run_low)
    targets.append(Target("Measured move", mm, rm(mm), "run-up height added to base high"))
    for j, p in enumerate(_swing_highs(H, i, entry * 1.005)[:2], 1):
        targets.append(Target(f"Resistance {j}", p, rm(p), "prior swing high"))
    if adr:
        targets.append(Target("+1 ADR", entry * (1 + adr), rm(entry * (1 + adr))))
        targets.append(Target("+3 ADR", entry * (1 + 3 * adr), rm(entry * (1 + 3 * adr))))
    targets.sort(key=lambda t: t.price)
    if sma10_last:
        targets.append(Target("Trailing exit", sma10_last, rm(sma10_last), "exit on daily close below 10 SMA"))
    targets.append(Target("Stop", stop, -1.0, "breakout-day low"))

    return SetupScore(
        ticker=ticker, date=bars[i].date, score=score, verdict=verdict, steps=steps,
        entry=entry, stop=stop, base_high=base_high, base_low=base_low,
        run_low=run_low, run_high=run_high, runup_pct=best, adr_pct=adr,
        dollar_vol=dollar_volume(bars, i), sma10=sma10_last, targets=targets,
    )


def market_regime(bars: Sequence[Bar]) -> Optional[bool]:
    """True when the index's 10 SMA is above its 20 SMA (doc: setup works best)."""
    if len(bars) < 20:
        return None
    C = [b.close for b in bars]
    return sma(C, 10)[-1] > sma(C, 20)[-1]
