"""The A+ Assessment pressure-test engine (Stage 2).

Four targeted upgrades over a plain scoring model:

  1. Evidence-anchored M8     — decisive CORE subscores must cite a fact.
  2. Quantified M2 (EV)        — bear/base/bull -> expected return + asymmetry.
  3. Opportunity-cost hurdle   — must beat the best alternative dollar.
  4. Base-rate -> spec size    — specs get a smaller size, not just a score.
"""

from stockscan.assess.m8 import m8_score
from stockscan.assess.ev import expected_value
from stockscan.assess.oppcost import opportunity_cost
from stockscan.assess.spec import spec_size_cap
from stockscan.assess.pipeline import assess, AssessmentInput, AssessmentResult

__all__ = [
    "m8_score",
    "expected_value",
    "opportunity_cost",
    "spec_size_cap",
    "assess",
    "AssessmentInput",
    "AssessmentResult",
]
