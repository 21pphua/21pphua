"""LLM-drafted CORE subscores — the research step you confirm.

Claude (claude-opus-4-8, adaptive thinking) researches a survivor and drafts
the full assessment input WITH cited evidence for the decisive CORE axes. The
code then enforces the evidence-cap and does the math; you review/override the
draft before it counts. This keeps the evidence-anchor rule honest while
saving the legwork — the "LLM-drafts, you confirm" model.

Requires ``pip install 'stockscan[research]'`` and ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

from typing import Optional

from stockscan.config import (
    M8_MAX,
    LLM_MODEL,
    LLM_MAX_TOKENS,
)
from stockscan.assess.pipeline import AssessmentInput
from stockscan.data.providers import MarketSnapshot


_SYSTEM = """\
You are the research engine behind an A+ stock-assessment pressure-test. You
draft a disciplined, evidence-anchored judgement of a single stock that a
human reviewer will confirm or override. You are NOT giving financial advice;
you are producing a structured decision artefact.

Hard rules (the model is built to catch laundering, so do not launder):

1. EVIDENCE-ANCHORED CORE SUBSCORES. For each of the four CORE axes — theme,
   moat, proof, entry — if you score it DECISIVELY (above 70% of its max),
   you MUST supply a one-line cited fact in the matching evidence field
   (a concrete number, filing, product fact, or named comparable). If you
   cannot cite a fact, score it AT OR BELOW the 70% threshold and leave the
   evidence field empty. Do not write a high subscore with hand-waving.

2. BASES BELOW STREET. Your base-case price target must sit BELOW consensus /
   street expectations. A stock 25% off its high can still be expensive —
   reckon with what is priced in, not with the drawdown.

3. PROBABILITIES SUM TO 1.0. p_bear + p_base + p_bull must equal exactly 1.0.

4. SPEC HONESTY. If this is a pre-revenue / unproven-category name, set
   is_spec=true and give base_rate_pct = the outside-view odds the category
   reaches commercial scale. Otherwise is_spec=false and base_rate_pct=null.

5. BEAR HAIRCUT. bear_haircut is points (0-15) subtracted from the final
   score for unresolved bear-case risk — be honest about it.

Axis maxima: theme 15, moat 20, proof 15, entry 15, ceiling 10, cycle 10,
falsify 5, confirm 10.
"""


def _build_pydantic_model():
    """Build the ResearchDraft model lazily (pydantic ships with anthropic)."""
    from pydantic import BaseModel, Field

    class ResearchDraft(BaseModel):
        # --- M8 subscores (0..max per axis) ---
        theme: int = Field(description="Secular theme strength, 0-15")
        moat: int = Field(description="Durable competitive advantage, 0-20")
        proof: int = Field(description="Evidence the thesis is working, 0-15")
        entry: int = Field(description="Quality of the entry point, 0-15")
        ceiling: int = Field(description="Upside ceiling / TAM headroom, 0-10")
        cycle: int = Field(description="Cycle / macro positioning, 0-10")
        falsify: int = Field(description="Clarity of what would falsify the thesis, 0-5")
        confirm: int = Field(description="Independent confirmation of the thesis, 0-10")

        # --- Cited evidence for the CORE axes (empty string if none) ---
        evidence_theme: str = Field(default="", description="One-line cited fact for theme")
        evidence_moat: str = Field(default="", description="One-line cited fact for moat")
        evidence_proof: str = Field(default="", description="One-line cited fact for proof")
        evidence_entry: str = Field(default="", description="One-line cited fact for entry")

        bear_haircut: int = Field(default=0, description="Points subtracted for bear risk, 0-15")

        # --- Expected value (M2): prices over the horizon ---
        bear: float = Field(description="Bear-case price target")
        base: float = Field(description="Base-case price target (BELOW street)")
        bull: float = Field(description="Bull-case price target")
        p_bear: float = Field(description="Probability of bear case (sums to 1)")
        p_base: float = Field(description="Probability of base case (sums to 1)")
        p_bull: float = Field(description="Probability of bull case (sums to 1)")
        horizon_mo: int = Field(default=18, description="Horizon in months")

        # --- Spec sizing (M5) ---
        is_spec: bool = Field(default=False, description="Pre-revenue / unproven category?")
        base_rate_pct: Optional[float] = Field(
            default=None,
            description="If spec: outside-view odds (%) the category reaches scale",
        )

        rationale: str = Field(description="2-4 sentence summary of the judgement")

    return ResearchDraft


# Exposed name for type hints / imports; the concrete model is built lazily.
ResearchDraft = None  # populated on first call to _build_pydantic_model via draft_assessment


def _snapshot_context(s: MarketSnapshot) -> str:
    def fmt(v, pct=False, suffix=""):
        if v is None:
            return "n/a"
        return f"{v * 100:.1f}%" if pct else f"{v:.2f}{suffix}"

    return (
        f"Ticker: {s.ticker}\n"
        f"Name: {s.name or 'n/a'}\n"
        f"Sector: {s.sector or 'n/a'}\n"
        f"Price: {fmt(s.price)}\n"
        f"12-1 momentum: {fmt(s.momentum_12_1, pct=True)}\n"
        f"% above 200dma: {fmt(s.pct_above_200dma, pct=True)}\n"
        f"Forward P/E: {fmt(s.forward_pe)}\n"
        f"Return on equity: {fmt(s.return_on_equity, pct=True)}\n"
        f"Annualised volatility: {fmt(s.volatility, pct=True)}\n"
    )


def draft_assessment(
    snapshot: MarketSnapshot,
    client=None,
    extra_context: str = "",
    model: str = LLM_MODEL,
) -> AssessmentInput:
    """Ask Claude to draft an evidence-anchored assessment input for one name.

    Returns an ``AssessmentInput`` ready for ``assess()`` — but you should
    show it to the user for confirmation/override first (the CLI does this).
    """
    try:
        import anthropic  # noqa: F401
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "anthropic is required for LLM research. "
            "Install it with: pip install 'stockscan[research]'"
        ) from exc

    import anthropic as _anthropic

    global ResearchDraft
    Draft = _build_pydantic_model()
    ResearchDraft = Draft

    client = client or _anthropic.Anthropic()

    user_content = (
        "Draft the assessment for this stock. Use the quantitative snapshot "
        "below plus your own knowledge. Follow every hard rule.\n\n"
        f"{_snapshot_context(snapshot)}"
    )
    if extra_context:
        user_content += f"\nAdditional context from the analyst:\n{extra_context}\n"

    # Structured output: validated against the pydantic schema. Adaptive
    # thinking keeps the reasoning honest on a genuinely analytical task.
    response = client.messages.parse(
        model=model,
        max_tokens=LLM_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
        output_format=Draft,
    )
    draft = response.parsed_output
    if draft is None:  # pragma: no cover - refusal / parse failure
        raise RuntimeError(
            f"Could not draft an assessment for {snapshot.ticker} "
            f"(stop_reason={response.stop_reason})."
        )

    return _draft_to_input(snapshot, draft)


def _draft_to_input(snapshot: MarketSnapshot, draft) -> AssessmentInput:
    """Map a ResearchDraft + snapshot onto an AssessmentInput."""
    subs = {
        "theme": draft.theme,
        "moat": draft.moat,
        "proof": draft.proof,
        "entry": draft.entry,
        "ceiling": draft.ceiling,
        "cycle": draft.cycle,
        "falsify": draft.falsify,
        "confirm": draft.confirm,
    }
    # Clamp to axis maxima so a hallucinated over-max can't slip through.
    subs = {k: max(0, min(v, M8_MAX[k])) for k, v in subs.items()}

    evidence = {
        "theme": draft.evidence_theme.strip(),
        "moat": draft.evidence_moat.strip(),
        "proof": draft.evidence_proof.strip(),
        "entry": draft.evidence_entry.strip(),
    }
    evidence = {k: v for k, v in evidence.items() if v}  # drop empties

    return AssessmentInput(
        ticker=snapshot.ticker,
        subs=subs,
        evidence=evidence,
        bear_haircut=max(0, draft.bear_haircut),
        price=snapshot.price or draft.base,
        bear=draft.bear,
        base=draft.base,
        bull=draft.bull,
        p_bear=draft.p_bear,
        p_base=draft.p_base,
        p_bull=draft.p_bull,
        horizon_mo=draft.horizon_mo,
        base_rate_pct=draft.base_rate_pct if draft.is_spec else None,
    )
