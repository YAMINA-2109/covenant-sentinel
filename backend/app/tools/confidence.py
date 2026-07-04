"""Deterministic confidence scoring.

The confidence attached to each verdict is NOT a number hallucinated by a
model. It is computed from:

(a) the Critic's checklist outcomes (citation validity, data freshness,
    definition basis, internal consistency), weighted below; and
(b) — as the track brief specifies — the share of the flagged movement that
    was matched to a clearly documented cause versus left unexplained
    (``cause_coverage``).

score = 0.8 * weighted_checks + 0.2 * cause_coverage   (when causes apply)

Verdicts that rest on a trend PROJECTION (status at_risk) additionally carry a
fixed 0.9 projection factor: a three-point linear extrapolation is inherently
an estimate, and the score must say so.
"""

from app.agent.state import CriticCheck

CHECK_WEIGHTS: dict[str, float] = {
    "citation_valid": 0.30,
    "data_freshness": 0.25,
    "definition_basis": 0.25,
    "internal_consistency": 0.20,
}
DEFAULT_WEIGHT = 0.20
CAUSE_SHARE = 0.20
PROJECTION_FACTOR = 0.9


def score_verdict(
    checks: list[CriticCheck],
    cause_coverage: float | None = None,
    projected: bool = False,
) -> float:
    """Return a confidence in [0, 1]."""
    if not checks:
        return 0.5  # nothing verified: explicitly middling, never silently high

    total_weight = 0.0
    passed_weight = 0.0
    for check in checks:
        weight = CHECK_WEIGHTS.get(check.check, DEFAULT_WEIGHT)
        total_weight += weight
        if check.passed:
            passed_weight += weight
    score = passed_weight / total_weight if total_weight else 0.5

    if cause_coverage is not None:
        cause_coverage = min(max(cause_coverage, 0.0), 1.0)
        score = (1 - CAUSE_SHARE) * score + CAUSE_SHARE * cause_coverage
    if projected:
        score *= PROJECTION_FACTOR
    return round(score, 4)


def overall_confidence(verdict_confidences: list[float]) -> float:
    """A memo is only as trustworthy as its weakest confirmed finding."""
    if not verdict_confidences:
        return 0.0
    return round(min(verdict_confidences), 4)
