"""Human-readable rendering of screen and assessment output."""

from __future__ import annotations

from typing import Sequence

from stockscan.assess.pipeline import AssessmentResult
from stockscan.screen.stage1 import ScreenRow


def render_screen(rows: Sequence[ScreenRow]) -> str:
    """Stage-1 ranked table."""
    lines = ["", "STAGE 1 — QUANTITATIVE SCREEN (top survivors)", "=" * 60]
    header = f"{'#':>2}  {'TICKER':<8}{'COMPOSITE':>10}  {'NAME'}"
    lines.append(header)
    lines.append("-" * 60)
    for r in rows:
        name = (r.name or "")[:30]
        lines.append(f"{r.rank:>2}  {r.ticker:<8}{r.composite:>+10.2f}  {name}")
    lines.append("")
    return "\n".join(lines)


def render_assessment(res: AssessmentResult) -> str:
    """Stage-2 single-name pressure-test, in the spec's worked-example shape."""
    m8, ev, opp, spec = res.m8, res.ev, res.opp_cost, res.spec

    capped = ""
    if m8["capped"]:
        bits = ", ".join(
            f"{ax} {orig}->{cap} (no cited fact)"
            for ax, (orig, cap) in m8["capped"].items()
        )
        capped = f" | CAPPED: {bits}"
    else:
        capped = " | evidence-clean"

    asym = ev["asymmetry"]
    asym_s = f"{asym}" if asym is not None else "n/a"

    spec_line = (
        f"SPEC SIZE: max {spec['max_position_pct']:.1f}% "
        f"(base rate {spec['base_rate_pct']:.0f}%)"
        if spec is not None
        else "SPEC SIZE: n/a (quality tier)"
    )

    return "\n".join(
        [
            "",
            f"{res.ticker} — A+ ASSESSMENT",
            "=" * 60,
            f"M8:        {m8['final']} ({m8['band']}) — core {m8['core']}{capped}",
            f"EV:        {ev['exp_ret_pct']:+.1f}% exp · {ev['downside_pct']:+.1f}% down · "
            f"{ev['upside_pct']:+.1f}% up · asym {asym_s} / {ev['horizon_mo']}mo",
            f"OPP-COST:  {opp['verdict']} "
            f"(cand {opp['cand_ev']:+.1f}% vs best alt "
            f"{opp['best_alternative']} {opp['best_alt_value']:+.1f}%)",
            spec_line,
            f"READ:      {res.read}",
            "",
        ]
    )


def render_ranked_assessments(results: Sequence[AssessmentResult]) -> str:
    """Final ranked summary across all assessed names."""
    ordered = sorted(
        results,
        key=lambda r: (r.clears_hurdle, r.m8["final"], r.exp_ret_pct),
        reverse=True,
    )
    lines = ["", "FINAL RANKING — assessed survivors", "=" * 60]
    lines.append(
        f"{'TICKER':<8}{'BAND':<6}{'M8':>4}{'EXP%':>8}{'ASYM':>7}  HURDLE"
    )
    lines.append("-" * 60)
    for r in ordered:
        asym = r.ev["asymmetry"]
        asym_s = f"{asym:.2f}" if asym is not None else "  -"
        hurdle = "clears" if r.clears_hurdle else "FAILS"
        lines.append(
            f"{r.ticker:<8}{r.band:<6}{r.m8['final']:>4}"
            f"{r.exp_ret_pct:>+8.1f}{asym_s:>7}  {hurdle}"
        )
    lines.append("")
    lines.append("Educational decision framework, not financial advice.")
    lines.append("")
    return "\n".join(lines)
