"""Upgrade 1 — Evidence-anchored M8.

A *decisive* CORE subscore (above ``int(0.7 * max)``) must carry a one-line
cited fact. No fact -> the subscore is capped at the threshold. This closes
the "score can launder a narrative into a number" hole: high subscores have
to show their work. Applied only to the four CORE axes (the narrative-prone
ones) — that is the anti-bloat line.
"""

from __future__ import annotations

from typing import Mapping

from stockscan.config import M8_MAX, EVIDENCE_REQUIRED, BANDS


def _band(final: int) -> str:
    for cutoff, label in BANDS:
        if final >= cutoff:
            return label
    return "REJECT"


def m8_score(
    subs: Mapping[str, int],
    evidence: Mapping[str, str] | None = None,
    bear: int = 0,
) -> dict:
    """Score the eight M8 axes with evidence-anchoring on the CORE four.

    Parameters
    ----------
    subs:
        Subscores keyed by axis name (``theme``, ``moat``, ``proof``,
        ``entry``, ``ceiling``, ``cycle``, ``falsify``, ``confirm``).
    evidence:
        One-line cited fact per CORE axis. A decisive CORE subscore with no
        evidence is capped at the threshold.
    bear:
        The bear-case haircut, subtracted from the final score.

    Returns
    -------
    dict with ``final``, ``band``, ``core``, and ``capped`` (a map of any
    axis that got capped -> ``(original, capped_to)``).
    """
    evidence = evidence or {}
    capped: dict[str, tuple[int, int]] = {}
    s = dict(subs)

    for ax in EVIDENCE_REQUIRED:
        thresh = int(0.7 * M8_MAX[ax])
        if s.get(ax, 0) > thresh and not evidence.get(ax):
            capped[ax] = (s[ax], thresh)
            s[ax] = thresh  # laundering caught

    core = s["theme"] + s["moat"] + s["proof"] + s["entry"]
    final = (
        core
        + s["ceiling"]
        + s["cycle"]
        + s["falsify"]
        + s["confirm"]
        - bear
    )
    return {
        "final": final,
        "band": _band(final),
        "core": core,
        "capped": capped,
    }
