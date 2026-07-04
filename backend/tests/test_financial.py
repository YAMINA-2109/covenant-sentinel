"""Unit tests for the deterministic financial tools, using the ACME demo numbers."""

from app.tools.confidence import overall_confidence, score_verdict
from app.agent.state import CriticCheck
from app.tools.financial import check_threshold, compute_ratio, project_linear


def test_leverage_ratio_matches_demo_scenario():
    result = compute_ratio(370.0, 100.0, "Total Debt", "LTM EBITDA")
    assert result.value == 3.7
    assert "3.70x" in result.formula


def test_leverage_breach_detected():
    result = check_threshold(3.7, "<=", 3.5)
    assert result.passed is False
    assert result.headroom == -0.2


def test_liquidity_final_figure_passes():
    result = check_threshold(5.3, ">=", 5.0)
    assert result.passed is True
    assert result.headroom == 0.3


def test_interest_coverage_drift_projection():
    points = [("Q4-2025", 3.10), ("Q1-2026", 2.80), ("Q2-2026", 2.50)]
    projection = project_linear(points, threshold=2.0, operator=">=")
    assert projection.slope_per_period == -0.3
    assert projection.periods_to_threshold is not None
    assert 1.5 <= projection.periods_to_threshold <= 1.8
    assert projection.projected_breach_period == "Q4-2026"


def test_confidence_is_deterministic_and_uses_cause_coverage():
    checks = [
        CriticCheck(check="citation_valid", passed=True),
        CriticCheck(check="data_freshness", passed=True),
        CriticCheck(check="definition_basis", passed=True),
        CriticCheck(check="internal_consistency", passed=False),
    ]
    without_cause = score_verdict(checks)
    assert without_cause == 0.8  # 0.30 + 0.25 + 0.25 of 1.00 total weight
    with_cause = score_verdict(checks, cause_coverage=40 / 45)
    assert with_cause == round(0.8 * 0.8 + 0.2 * (40 / 45), 4)


def test_overall_confidence_is_weakest_link():
    assert overall_confidence([0.92, 0.85, 0.99]) == 0.85
