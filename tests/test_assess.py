"""Tests pinned to the A+ spec's worked examples."""

from stockscan.assess import (
    m8_score,
    expected_value,
    opportunity_cost,
    spec_size_cap,
    assess,
    AssessmentInput,
)


# --- Upgrade 1: evidence-anchored M8 -----------------------------------------

def _v_subs():
    # Only `moat` is decisive (18 > 14); the other CORE axes sit at/below
    # their thresholds so they don't require evidence. Totals to 69.
    return {
        "theme": 10, "moat": 18, "proof": 10, "entry": 10,
        "ceiling": 8, "cycle": 8, "falsify": 4, "confirm": 1,
    }


def test_m8_cited_decisive_moat_scores_69_band_b():
    out = m8_score(_v_subs(), evidence={"moat": "dual-network duopoly"}, bear=0)
    assert out["final"] == 69
    assert out["band"] == "B"
    assert out["capped"] == {}


def test_m8_stripped_citation_caps_moat_to_65():
    out = m8_score(_v_subs(), evidence={}, bear=0)  # no moat citation
    assert out["final"] == 65          # 18 -> 14 drops the score by 4
    assert out["band"] == "B"
    assert out["capped"]["moat"] == (18, 14)


def test_m8_bands():
    base = {"theme": 0, "moat": 0, "proof": 0, "entry": 0,
            "ceiling": 0, "cycle": 0, "falsify": 0, "confirm": 0}
    assert m8_score({**base, "moat": 20, "theme": 15, "proof": 15, "entry": 15,
                     "ceiling": 10, "cycle": 10},
                    evidence={"moat": "x", "theme": "x", "proof": "x", "entry": "x"}
                    )["band"] == "A"  # 85
    assert m8_score(base)["band"] == "REJECT"


# --- Upgrade 2: quantified expected value ------------------------------------

def test_expected_value_v_at_324():
    ev = expected_value(
        price=324, bear=285, base=367, bull=400,
        p_bear=0.25, p_base=0.50, p_bull=0.25, horizon_mo=18,
    )
    assert ev["exp_ret_pct"] == 9.5
    assert ev["downside_pct"] == -12.0
    assert ev["upside_pct"] == 23.5
    assert ev["asymmetry"] == 0.79
    assert ev["horizon_mo"] == 18


def test_expected_value_probabilities_must_sum_to_one():
    import pytest
    with pytest.raises(ValueError):
        expected_value(100, 90, 110, 130, 0.3, 0.3, 0.3)


# --- Upgrade 3: opportunity-cost hurdle --------------------------------------

def test_opp_cost_clears_when_candidate_beats_best_alt():
    out = opportunity_cost(
        cand_ev=9.5, add_winner_ev=0.0, cash_yield_pct=4.5,
        weakest_replace_ev=3.0,
    )
    assert out["best_alternative"] == "hold_cash"
    assert out["clears"] is True
    assert out["verdict"] == "BUY/ADD clears"


def test_opp_cost_swap_justified_on_diversification():
    out = opportunity_cost(
        cand_ev=2.0, add_winner_ev=8.0, cash_yield_pct=4.5,
        weakest_replace_ev=3.0, diversifies=True,
    )
    assert out["clears"] is True
    assert "SWAP" in out["verdict"]


def test_opp_cost_fails_without_diversification():
    out = opportunity_cost(
        cand_ev=2.0, add_winner_ev=8.0, cash_yield_pct=4.5,
        weakest_replace_ev=3.0, diversifies=False,
    )
    assert out["clears"] is False
    assert out["verdict"].startswith("FAILS")


# --- Upgrade 4: base-rate -> spec size ---------------------------------------

def test_spec_size_cap_bands():
    assert spec_size_cap(10)["max_position_pct"] == 1.0
    assert spec_size_cap(15)["max_position_pct"] == 2.0   # SMR @ ~15% -> 2%
    assert spec_size_cap(40)["max_position_pct"] == 3.0


# --- Full pipeline -----------------------------------------------------------

def test_assess_end_to_end_v():
    inp = AssessmentInput(
        ticker="V",
        subs=_v_subs(),
        evidence={"moat": "dual-network duopoly"},
        price=324, bear=285, base=367, bull=400,
        p_bear=0.25, p_base=0.50, p_bull=0.25,
        add_winner_ev=0.0, cash_yield_pct=4.5, weakest_replace_ev=3.0,
        diversifies=True,
    )
    res = assess(inp)
    assert res.band == "B"
    assert res.exp_ret_pct == 9.5
    assert res.clears_hurdle is True
    assert res.spec is None  # quality tier
    assert "B-band" in res.read
