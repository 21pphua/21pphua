"""Command-line interface for stockscan.

Commands
--------
  demo     Run the worked example (V) offline — proves the engine, no deps.
  screen   Stage 1 only: rank a universe by the quantitative composite.
  assess   Stage 2 on one ticker: LLM-draft -> you confirm -> pressure-test.
  scan     Full funnel: screen -> draft survivors -> confirm -> ranked report.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import Optional, Sequence

from stockscan import __version__
from stockscan.config import DEFAULT_TOP_N, DEFAULT_UNIVERSE, M8_MAX
from stockscan.assess.pipeline import AssessmentInput, AssessmentResult, assess
from stockscan.universe import resolve_universe, list_builtin_universes
from stockscan import report


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _load_universe(args) -> list[str]:
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    return resolve_universe(args.universe or DEFAULT_UNIVERSE)


def _progress(i: int, n: int, ticker: str) -> None:
    sys.stderr.write(f"\r  fetching {i}/{n}: {ticker:<8}")
    sys.stderr.flush()
    if i == n:
        sys.stderr.write("\n")


def _confirm_draft(inp: AssessmentInput, auto_yes: bool) -> Optional[AssessmentInput]:
    """Show the LLM draft and let the analyst confirm, edit, or skip.

    Returns the (possibly edited) input, or None to skip the name.
    This is the human gate that keeps the evidence-anchor rule honest.
    """
    print(_format_draft(inp))
    if auto_yes:
        print("  [auto-confirmed]\n")
        return inp

    while True:
        choice = input("  [a]ccept / [e]dit / [s]kip > ").strip().lower()
        if choice in ("a", "accept", ""):
            return inp
        if choice in ("s", "skip"):
            return None
        if choice in ("e", "edit"):
            inp = _edit_input(inp)
            print(_format_draft(inp))
            continue
        print("  (a, e, or s)")


def _format_draft(inp: AssessmentInput) -> str:
    ev_lines = []
    for ax in ("theme", "moat", "proof", "entry"):
        fact = inp.evidence.get(ax, "")
        mark = "✓" if fact else "·"
        ev_lines.append(f"      {mark} {ax:<8} {inp.subs[ax]}/{M8_MAX[ax]}  {fact}")
    return "\n".join(
        [
            "",
            f"  DRAFT — {inp.ticker}",
            "  " + "-" * 50,
            "    CORE subscores (evidence required if decisive):",
            *ev_lines,
            f"    other: ceiling {inp.subs['ceiling']} cycle {inp.subs['cycle']} "
            f"falsify {inp.subs['falsify']} confirm {inp.subs['confirm']} "
            f"| bear haircut {inp.bear_haircut}",
            f"    EV inputs: price {inp.price} | bear {inp.bear} base {inp.base} "
            f"bull {inp.bull} | p {inp.p_bear}/{inp.p_base}/{inp.p_bull}",
            f"    spec base_rate: {inp.base_rate_pct}",
            "",
        ]
    )


def _edit_input(inp: AssessmentInput) -> AssessmentInput:
    """Minimal key=value editor for the draft fields."""
    print(
        "    Enter edits as 'field=value', one per line. Blank line to finish.\n"
        "    Subscores: theme/moat/proof/entry/ceiling/cycle/falsify/confirm\n"
        "    Evidence:  ev_theme/ev_moat/ev_proof/ev_entry\n"
        "    EV:        price/bear/base/bull/p_bear/p_base/p_bull/bear_haircut\n"
        "    Spec:      base_rate_pct (blank value clears it)"
    )
    subs = dict(inp.subs)
    evidence = dict(inp.evidence)
    changes: dict = {}
    while True:
        raw = input("    edit> ").strip()
        if not raw:
            break
        if "=" not in raw:
            print("      use field=value")
            continue
        field, _, value = raw.partition("=")
        field, value = field.strip(), value.strip()
        try:
            if field in subs:
                subs[field] = int(value)
            elif field.startswith("ev_"):
                ax = field[3:]
                if value:
                    evidence[ax] = value
                else:
                    evidence.pop(ax, None)
            elif field in ("price", "bear", "base", "bull", "p_bear", "p_base", "p_bull"):
                changes[field] = float(value)
            elif field == "bear_haircut":
                changes[field] = int(value)
            elif field == "base_rate_pct":
                changes[field] = float(value) if value else None
            else:
                print(f"      unknown field: {field}")
        except ValueError:
            print(f"      bad value for {field}: {value!r}")
    return dataclasses.replace(inp, subs=subs, evidence=evidence, **changes)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_demo(args) -> int:
    """The spec's worked example (V), entirely offline."""
    inp = AssessmentInput(
        ticker="V",
        subs={"theme": 13, "moat": 18, "proof": 13, "entry": 11,
              "ceiling": 7, "cycle": 8, "falsify": 4, "confirm": 8},
        evidence={
            "theme": "Secular shift cash->card; ~$240T global payments flows.",
            "moat": "Dual-network duopoly; ~50% incremental margins, returns on capital >30%.",
            "proof": "Double-digit payments-volume growth sustained across cycles.",
            "entry": "Trading at a discount to its own 5y multiple after the pullback.",
        },
        bear_haircut=0,
        price=324, bear=285, base=345, bull=400,
        p_bear=0.25, p_base=0.50, p_bull=0.25, horizon_mo=18,
        add_winner_ev=0.0, cash_yield_pct=4.5, weakest_replace_ev=3.0,
        diversifies=True,
        base_rate_pct=None,
    )
    res = assess(inp)
    print(report.render_assessment(res))

    # Demonstrate the evidence cap: strip the moat citation.
    stripped = dataclasses.replace(
        inp, evidence={k: v for k, v in inp.evidence.items() if k != "moat"}
    )
    res2 = assess(stripped)
    print("  (strip the moat citation -> the decisive subscore auto-caps:)")
    print(report.render_assessment(res2))
    return 0


def cmd_universes(args) -> int:
    names = list_builtin_universes()
    if not names:
        print("No built-in universes packaged.")
        return 0
    print("Built-in universes:")
    for name in names:
        try:
            count = len(resolve_universe(name))
        except Exception:
            count = "?"
        marker = "  (default)" if name == DEFAULT_UNIVERSE else ""
        print(f"  {name:<10} {count} tickers{marker}")
    print("\nUse: stockscan scan --universe <name|file>")
    return 0


def cmd_screen(args) -> int:
    from stockscan.data.providers import get_provider
    from stockscan.screen.stage1 import screen_universe

    tickers = _load_universe(args)
    provider = get_provider(args.provider)
    print(f"Screening {len(tickers)} names via {args.provider} ...", file=sys.stderr)
    rows = screen_universe(tickers, provider, top_n=args.top, on_progress=_progress)
    print(report.render_screen(rows))
    return 0


def _research_and_assess(snapshot, args) -> Optional[AssessmentResult]:
    from stockscan.research.llm import draft_assessment

    draft = draft_assessment(snapshot, extra_context=args.context or "")
    confirmed = _confirm_draft(draft, auto_yes=args.yes)
    if confirmed is None:
        return None
    return assess(confirmed)


def cmd_assess(args) -> int:
    from stockscan.data.providers import get_provider

    provider = get_provider(args.provider)
    ticker = args.ticker.upper()
    print(f"Fetching {ticker} ...", file=sys.stderr)
    snapshot = provider.snapshot(ticker)
    res = _research_and_assess(snapshot, args)
    if res is None:
        print("Skipped.")
        return 0
    print(report.render_assessment(res))
    return 0


def cmd_scan(args) -> int:
    from stockscan.data.providers import get_provider
    from stockscan.screen.stage1 import screen_universe

    tickers = _load_universe(args)
    provider = get_provider(args.provider)

    print(f"STAGE 1: screening {len(tickers)} names ...", file=sys.stderr)
    rows = screen_universe(tickers, provider, top_n=args.top, on_progress=_progress)
    print(report.render_screen(rows))

    print(f"STAGE 2: researching + assessing top {len(rows)} ...", file=sys.stderr)
    results: list[AssessmentResult] = []
    for row in rows:
        res = _research_and_assess(row.snapshot, args)
        if res is not None:
            print(report.render_assessment(res))
            results.append(res)

    if results:
        print(report.render_ranked_assessments(results))
    else:
        print("No names assessed.")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stockscan",
        description="Elite stock scan/research model — quantitative funnel + A+ assessment engine.",
    )
    p.add_argument("--version", action="version", version=f"stockscan {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_universe_args(sp):
        sp.add_argument("--tickers", help="Comma-separated tickers (overrides --universe).")
        sp.add_argument(
            "--universe",
            help=f"Built-in name ({', '.join(list_builtin_universes()) or 'none'}) "
            f"or a path to a file of tickers (default: {DEFAULT_UNIVERSE}).",
        )
        sp.add_argument("--provider", default="yfinance", help="Data provider (default: yfinance).")

    def add_research_args(sp):
        sp.add_argument("-y", "--yes", action="store_true", help="Auto-confirm LLM drafts.")
        sp.add_argument("--context", help="Extra analyst context passed to the LLM.")

    sp = sub.add_parser("demo", help="Run the worked example offline (no deps).")
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("universes", help="List built-in universes.")
    sp.set_defaults(func=cmd_universes)

    sp = sub.add_parser("screen", help="Stage 1 only: rank a universe.")
    add_universe_args(sp)
    sp.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Survivors to keep.")
    sp.set_defaults(func=cmd_screen)

    sp = sub.add_parser("assess", help="Stage 2 on one ticker (LLM draft -> confirm).")
    sp.add_argument("ticker", help="Ticker to assess, e.g. AAPL.")
    sp.add_argument("--provider", default="yfinance", help="Data provider (default: yfinance).")
    add_research_args(sp)
    sp.set_defaults(func=cmd_assess)

    sp = sub.add_parser("scan", help="Full funnel: screen -> draft -> confirm -> ranked report.")
    add_universe_args(sp)
    sp.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Survivors to assess.")
    add_research_args(sp)
    sp.set_defaults(func=cmd_scan)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except ImportError as exc:
        print(f"\nMissing dependency: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
