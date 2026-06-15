"""stockscan — an elite stock scan/research model.

A two-stage funnel:

    Stage 1 (cheap, broad)   quantitative screen ranks a universe
    Stage 2 (expensive, deep) the A+ Assessment pressure-test engine
                              judges the survivors

The assessment engine is a faithful port of the "A+ ASSESSMENT MODEL
UPGRADE v1" spec: evidence-anchored M8, quantified expected value,
opportunity-cost hurdle, and base-rate -> spec-size binding.

Educational decision framework, not financial advice.
"""

from stockscan.assess import (
    m8_score,
    expected_value,
    opportunity_cost,
    spec_size_cap,
    assess,
    AssessmentInput,
    AssessmentResult,
)

__version__ = "0.1.0"

__all__ = [
    "m8_score",
    "expected_value",
    "opportunity_cost",
    "spec_size_cap",
    "assess",
    "AssessmentInput",
    "AssessmentResult",
    "__version__",
]
