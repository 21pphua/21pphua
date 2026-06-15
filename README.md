# stockscan

**An elite stock scan/research model** — a two-stage funnel that pairs a
quantitative screen with the *A+ Assessment* pressure-test engine.

> Educational decision framework, **not financial advice.**

It turns the single-name judging engine from the *A+ Assessment Model Upgrade v1*
spec into a scanner: a cheap quantitative screen narrows a universe down to the
few names worth running the expensive, evidence-anchored assessment on.

```
Stage 1  (cheap, broad)    quantitative screen ranks a universe
   │                        momentum · trend · value · quality · low-vol
   ▼
Stage 2  (expensive, deep)  the A+ Assessment engine judges the survivors
                            ① evidence-anchored M8   ② quantified EV
                            ③ opportunity-cost hurdle ④ base-rate → spec size
```

## Design decisions (chosen with the analyst)

| Decision | Choice |
|---|---|
| **Data** | Hybrid — quantitative fields auto-pulled (yfinance); qualitative CORE subscores LLM-drafted, analyst-confirmed |
| **Funnel** | Two-stage: quant screen → deep assessment on the top survivors |
| **CORE subscores** | LLM drafts theme/moat/proof/entry **with cited evidence**; you confirm or override before they count |
| **Deliverable** | Installable Python package + `stockscan` CLI |

The hard part of "scanning" is that the CORE axes (theme, moat, proof, entry)
are judgment calls — you can't subjectively score thousands of tickers. The
funnel solves that: Stage 1 is pure quant over the whole universe; Stage 2's
LLM-drafts-you-confirm loop is the only place human-grade judgment is spent,
and only on the handful that survive.

## Install

The **core engine and CLI have zero required dependencies** — they run offline.
The two outer stages pull in optional extras:

```bash
pip install -e .            # engine + CLI + offline demo
pip install -e '.[data]'    # + yfinance for the Stage-1 screen
pip install -e '.[research]'# + anthropic for LLM-drafted subscores
pip install -e '.[all]'     # everything
```

The research step needs an API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Network egress:** the Stage-1 screen pulls from Yahoo Finance via yfinance.
On a restricted/cloud environment, allow egress to `query1.finance.yahoo.com`
and `query2.finance.yahoo.com` (the offline `demo` needs no network).

## Usage

### Prove the engine offline (no deps, no key)

```bash
stockscan demo
```

Runs the spec's worked example for **V**, then strips the moat citation to show
the evidence cap auto-firing (decisive `18 → 14`).

### Stage 1 only — rank a universe

```bash
stockscan universes                          # list built-in universes
stockscan screen --top 10                    # default universe: sp500 (503 names)
stockscan screen --universe dow30 --top 10   # the Dow 30, quicker
stockscan screen --universe my_watchlist.txt # your own file (one ticker/line)
stockscan screen --tickers AAPL,MSFT,NVDA,V
```

Built-in universes (`sp500`, `dow30`) are packaged with the tool. Refresh the
S&P 500 list any time with `python scripts/refresh_universes.py`.

### Stage 2 — assess one name (LLM draft → you confirm)

```bash
stockscan assess NVDA
stockscan assess NVDA --yes          # auto-confirm the draft
stockscan assess NVDA --context "Focus on the data-center cycle risk."
```

You'll see the drafted CORE subscores with their cited facts and can
`[a]ccept / [e]dit / [s]kip` before the math runs.

### Full funnel

```bash
stockscan scan --top 8                 # screen the S&P 500, assess the top 8
stockscan scan --universe dow30 --top 12 --yes
```

Produces the Stage-1 table, a per-name A+ assessment, and a final ranking.

## What the assessment reports

Each name comes back in the spec's worked-example shape:

```
NVDA — A+ ASSESSMENT
============================================================
M8:        78 (B) — core 51 | CAPPED: moat 18->14 (no cited fact)
EV:        +6.1% exp · -12.0% down · +23.5% up · asym 0.51 / 18mo
OPP-COST:  BUY/ADD clears (cand +6.1% vs best alt hold_cash +4.5%)
SPEC SIZE: n/a (quality tier)
READ:      B-band, +6.1% expected over 18mo (contained downside); clears its alternatives.
```

- **M8** — evidence-anchored band. A decisive CORE subscore with no cited fact
  is auto-capped at the 70% threshold (`capped` shows what was caught).
- **EV** — bear/base/bull × probabilities → expected return, downside, upside,
  asymmetry. Bases run *below* street. Read compounders on downside + asymmetry,
  not expected return alone.
- **OPP-COST** — must beat the best alternative dollar (add to a winner, hold
  cash, replace the weakest); a diversifier can win as a *swap* at lower raw EV.
- **SPEC SIZE** — a speculative name gets a hard position-size cap tied to the
  outside-view base rate, not just a lower score.

## Use it as a library

```python
from stockscan import assess, AssessmentInput

res = assess(AssessmentInput(
    ticker="V",
    subs={"theme": 10, "moat": 18, "proof": 10, "entry": 10,
          "ceiling": 8, "cycle": 8, "falsify": 4, "confirm": 1},
    evidence={"moat": "dual-network duopoly; >30% returns on capital"},
    price=324, bear=285, base=367, bull=400,
    p_bear=0.25, p_base=0.50, p_bull=0.25,
    cash_yield_pct=4.5, weakest_replace_ev=3.0, diversifies=True,
))
print(res.band, res.exp_ret_pct, res.read)
```

The four upgrades are also importable individually: `m8_score`,
`expected_value`, `opportunity_cost`, `spec_size_cap`.

## Project layout

```
stockscan/
  assess/      the A+ engine — m8, ev, oppcost, spec, pipeline
  data/        market-data providers (yfinance bulk; swap-in seam for a paid feed)
  screen/      Stage-1 factors + ranking
  research/    LLM-drafted CORE subscores (Claude, structured output)
  universes/   packaged ticker lists (sp500.txt, dow30.txt)
  universe.py  resolve a built-in name or a file path
  report.py    rendering
  cli.py       the `stockscan` command
scripts/
  refresh_universes.py   regenerate the S&P 500 list
tests/         pinned to the spec's worked examples
```

## Tests

```bash
pip install -e '.[dev]'
pytest
```

## Roadmap / seams left open

- **Paid data feed** — `data/providers.py` has a `get_provider()` factory; add a
  `PolygonProvider` / `FMPProvider` without touching the screen or engine.
- **More universes** — drop a file in `stockscan/universes/` (e.g. a Russell
  list) and it's instantly available by name.
- **Persisted runs** — assessments are plain dataclasses; easy to serialize.
- *Deliberately excluded* (per the spec's anti-bloat line): sell/trim engine,
  multi-factor exposure tags, rename — none sharpen *judging a stock*.
