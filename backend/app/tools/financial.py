"""Deterministic financial math.

The LLM never does arithmetic: every number that appears in a finding is
produced by one of these pure functions, and the finding records which tool
call produced it (`computed_by`), so judges can audit the math.
"""

from pydantic import BaseModel


class RatioResult(BaseModel):
    value: float
    formula: str


def compute_ratio(
    numerator: float, denominator: float, label_num: str = "", label_den: str = ""
) -> RatioResult:
    if denominator == 0:
        raise ValueError("denominator is zero")
    value = numerator / denominator
    formula = (
        f"{label_num or 'numerator'} {numerator:,.1f} / "
        f"{label_den or 'denominator'} {denominator:,.1f} = {value:.2f}x"
    )
    return RatioResult(value=round(value, 4), formula=formula)


class ThresholdResult(BaseModel):
    passed: bool
    headroom: float  # positive = margin remaining, negative = amount in breach
    headroom_pct: float | None = None  # headroom as % of threshold
    detail: str


def check_threshold(value: float, operator: str, threshold: float) -> ThresholdResult:
    comparisons = {
        "<=": value <= threshold,
        ">=": value >= threshold,
        "<": value < threshold,
        ">": value > threshold,
    }
    if operator not in comparisons:
        raise ValueError(f"unsupported operator: {operator}")
    passed = comparisons[operator]
    if operator in ("<=", "<"):
        headroom = threshold - value
    else:
        headroom = value - threshold
    headroom_pct = round(headroom / threshold * 100, 2) if threshold else None
    detail = (
        f"value {value:,.2f} {operator} {threshold:,.2f} -> "
        f"{'PASS' if passed else 'FAIL'} (headroom {headroom:+,.2f})"
    )
    return ThresholdResult(
        passed=passed, headroom=round(headroom, 4), headroom_pct=headroom_pct, detail=detail
    )


class TrendProjection(BaseModel):
    slope_per_period: float
    periods_to_threshold: float | None = None  # None if trend moves away from threshold
    projected_breach_period: str | None = None
    detail: str


def _advance_quarter(label: str, steps: int) -> str:
    """'Q2-2026' + 2 -> 'Q4-2026'. Falls back to a relative label if unparseable."""
    import re

    match = re.match(r"^Q([1-4])[-/ ]?(\d{4})$", label.strip(), re.IGNORECASE)
    if not match:
        return f"+{steps} periods"
    quarter, year = int(match.group(1)), int(match.group(2))
    index = (quarter - 1) + steps
    return f"Q{index % 4 + 1}-{year + index // 4}"


def project_linear(
    points: list[tuple[str, float]], threshold: float, operator: str
) -> TrendProjection:
    """Least-squares linear projection of a covenant metric toward its threshold.

    `operator` is the covenant requirement (e.g. '>=' means the metric must
    stay at or above the threshold; a downward slope is therefore the risky
    direction).
    """
    if len(points) < 2:
        return TrendProjection(slope_per_period=0.0, detail="not enough data points")

    values = [value for _, value in points]
    n = len(values)
    mean_x = (n - 1) / 2
    mean_y = sum(values) / n
    covariance = sum((i - mean_x) * (values[i] - mean_y) for i in range(n))
    variance = sum((i - mean_x) ** 2 for i in range(n))
    slope = covariance / variance
    last_period, last_value = points[-1]

    if operator in (">=", ">"):
        moving_toward_breach = slope < 0
        distance = last_value - threshold
    else:
        moving_toward_breach = slope > 0
        distance = threshold - last_value

    if not moving_toward_breach or slope == 0:
        return TrendProjection(
            slope_per_period=round(slope, 4),
            detail=f"trend {slope:+.2f}/period is not moving toward the {operator} {threshold} limit",
        )

    periods = distance / abs(slope)
    if periods < 0:
        # already past the threshold
        return TrendProjection(
            slope_per_period=round(slope, 4),
            periods_to_threshold=0.0,
            projected_breach_period=last_period,
            detail="threshold already crossed",
        )

    breach_period = _advance_quarter(last_period, max(1, int(-(-periods // 1))))
    return TrendProjection(
        slope_per_period=round(slope, 4),
        periods_to_threshold=round(periods, 2),
        projected_breach_period=breach_period,
        detail=(
            f"trend {slope:+.2f}/period; at this pace the {operator} {threshold} "
            f"limit is crossed in ~{periods:.1f} periods (≈ {breach_period})"
        ),
    )
