"""Upgrade 3 — Opportunity-cost / benchmark hurdle.

Every BUY/ADD must beat the best alternative use of the same dollar: add to a
winner you own, hold cash, or replace the weakest name. A HOLD that can't beat
its own alternatives is a trim candidate, not a hold.

Diversification credit: a correlation-reducer can win as a *swap* at lower raw
EV — the swap-not-stack edge, made mechanical.
"""

from __future__ import annotations


def opportunity_cost(
    cand_ev: float,
    add_winner_ev: float,
    cash_yield_pct: float,
    weakest_replace_ev: float,
    diversifies: bool = False,
) -> dict:
    """Compare a candidate's EV to the best alternative dollar.

    Parameters are all expected returns (in %), except ``diversifies`` which
    flags a correlation-reducer eligible for the swap exception.
    """
    alts = {
        "add_to_winner": add_winner_ev,
        "hold_cash": cash_yield_pct,
        "replace_weakest": weakest_replace_ev,
    }
    best = max(alts, key=alts.get)
    beats = cand_ev > alts[best]

    if beats:
        verdict = "BUY/ADD clears"
    elif diversifies:
        verdict = "SWAP-justified (diversification)"
    else:
        verdict = "FAILS — better dollar elsewhere"

    return {
        "best_alternative": best,
        "best_alt_value": alts[best],
        "cand_ev": cand_ev,
        "clears": beats or diversifies,
        "verdict": verdict,
    }
