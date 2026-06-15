"""Stage-2 orchestration: run all four upgrades in one pass and compose a verdict.

Mirrors the spec's §3 pressure-test pipeline:

    4  m8_score()        decisive CORE subscores must cite a fact
    5  expected_value()  a number, not "beatable? Y/N"
       spec_size_cap()   binds size, not just score
    6b opportunity_cost() must beat the best alternative dollar
    7  compose: VERDICT + M8 + EV line + opp-cost line
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from stockscan.assess.m8 import m8_score
from stockscan.assess.ev import expected_value
from stockscan.assess.oppcost import opportunity_cost
from stockscan.assess.spec import spec_size_cap
from stockscan.config import DEFAULT_HORIZON_MO


@dataclass
class AssessmentInput:
    """Everything the four upgrades need to judge one name.

    These are exactly the fields the LLM research step drafts (with cited
    evidence) and the human confirms before they count.
    """

    ticker: str

    # --- M8 subscores + evidence ---
    subs: dict                              # axis -> subscore
    evidence: dict = field(default_factory=dict)  # CORE axis -> cited fact
    bear_haircut: int = 0

    # --- Expected value (M2) ---
    price: float = 0.0
    bear: float = 0.0
    base: float = 0.0
    bull: float = 0.0
    p_bear: float = 0.0
    p_base: float = 0.0
    p_bull: float = 0.0
    horizon_mo: int = DEFAULT_HORIZON_MO

    # --- Opportunity cost ---
    add_winner_ev: float = 0.0
    cash_yield_pct: float = 4.5
    weakest_replace_ev: float = 0.0
    diversifies: bool = False

    # --- Spec sizing (M5). None => quality tier, sizing n/a. ---
    base_rate_pct: Optional[float] = None


@dataclass
class AssessmentResult:
    ticker: str
    m8: dict
    ev: dict
    opp_cost: dict
    spec: Optional[dict]
    read: str

    @property
    def band(self) -> str:
        return self.m8["band"]

    @property
    def exp_ret_pct(self) -> float:
        return self.ev["exp_ret_pct"]

    @property
    def clears_hurdle(self) -> bool:
        return self.opp_cost["clears"]


def _compose_read(m8: dict, ev: dict, opp: dict, spec: Optional[dict]) -> str:
    """One-line synthesis in the spirit of the spec's worked example."""
    band = m8["band"]
    asym = ev["asymmetry"]
    skew = (
        "favourable skew" if (asym is not None and asym >= 1)
        else "contained downside" if (ev["downside_pct"] > -20)
        else "real downside"
    )
    if not opp["clears"]:
        dollar = "FAILS the opportunity-cost hurdle"
    elif "SWAP" in opp["verdict"]:
        dollar = "justified as a SWAP (diversifies)"
    else:
        dollar = "clears its alternatives"
    size = ""
    if spec is not None:
        size = f"; spec sized to <= {spec['max_position_pct']:.1f}%"
    return (
        f"{band}-band, {ev['exp_ret_pct']:+.1f}% expected over "
        f"{ev['horizon_mo']}mo ({skew}); {dollar}{size}."
    )


def assess(inp: AssessmentInput) -> AssessmentResult:
    """Run the full pressure-test on one name."""
    m8 = m8_score(inp.subs, inp.evidence, inp.bear_haircut)

    ev = expected_value(
        inp.price, inp.bear, inp.base, inp.bull,
        inp.p_bear, inp.p_base, inp.p_bull, inp.horizon_mo,
    )

    opp = opportunity_cost(
        cand_ev=ev["exp_ret_pct"],
        add_winner_ev=inp.add_winner_ev,
        cash_yield_pct=inp.cash_yield_pct,
        weakest_replace_ev=inp.weakest_replace_ev,
        diversifies=inp.diversifies,
    )

    spec = spec_size_cap(inp.base_rate_pct) if inp.base_rate_pct is not None else None

    return AssessmentResult(
        ticker=inp.ticker,
        m8=m8,
        ev=ev,
        opp_cost=opp,
        spec=spec,
        read=_compose_read(m8, ev, opp, spec),
    )
