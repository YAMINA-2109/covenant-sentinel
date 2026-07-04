"""ANALYZER — turns rules + facts into findings.

The LLM only *selects* which facts feed each covenant test (honouring the
covenant's measurement basis); every number is then computed by the
deterministic tools, and each tool call is streamed to the trace. When the
analysis exposes a gap — a missing metric, conflicting preliminary/final
figures, or an unexplained breach — the Analyzer queues targeted follow-up
retrievals: that loop is the agentic heart of the system.
"""

from app.agent.prompts import ANALYZER_SYSTEM, CAUSE_SYSTEM
from app.agent.schemas import AnalyzerOutput, CauseAnalysis
from app.agent.state import (
    AuditState,
    CauseMatch,
    CovenantRule,
    FinancialFact,
    Finding,
    RetrievalRequest,
    TrendPoint,
)
from app.agent.nodes.common import (
    fmt_value,
    metric_components,
    pretty_metric,
    snippets_block,
    source_from_snippets,
)
from app.core.events import EventType, Node
from app.tools.financial import check_threshold, compute_ratio, project_linear

AT_RISK_HORIZON_PERIODS = 3.0


def _fact_at(state: AuditState, index: int | None) -> FinancialFact | None:
    if index is None or not (0 <= index < len(state.facts)):
        return None
    return state.facts[index]


def _rule_by_id(state: AuditState, rule_id: str) -> CovenantRule | None:
    for rule in state.rules:
        if rule.rule_id == rule_id:
            return rule
    return None


async def run_analyzer(state: AuditState, ctx) -> None:
    bus = ctx.bus
    bus.publish(
        Node.ANALYZER,
        EventType.NODE_STARTED,
        {"facts_available": len(state.facts), "retrieval_round": state.retrieval_rounds},
    )

    rules_lines = "\n".join(
        f"- rule_id={rule.rule_id} | name={rule.name} | metric={rule.metric} | "
        f"requirement={rule.operator} {rule.threshold}{rule.unit} | "
        f"basis_notes={rule.definition_notes or 'none'}"
        for rule in state.rules
    )
    facts_lines = "\n".join(
        f"[{index}] metric={fact.metric} value={fact.value} unit={fact.unit} "
        f"period={fact.period or '?'} basis={fact.basis}"
        for index, fact in enumerate(state.facts)
    )
    output = await ctx.llm.chat_json(
        ANALYZER_SYSTEM,
        (
            f"COVENANTS:\n{rules_lines}\n\nFACTS (numbered):\n{facts_lines}\n\n"
            "Produce exactly one assessment per covenant."
        ),
        AnalyzerOutput,
    )

    state.findings = []  # recomputed idempotently on every pass
    followups: list[RetrievalRequest] = []
    queued = {(request.reason, request.query) for request in state.pending_retrievals}

    def queue(reason: str, query: str, doc_kind: str | None = None) -> None:
        if (reason, query) not in queued:
            queued.add((reason, query))
            followups.append(RetrievalRequest(reason=reason, query=query, doc_kind=doc_kind))

    for assessment in output.assessments:
        rule = _rule_by_id(state, assessment.rule_id)
        if rule is None:
            continue

        numerator = _fact_at(state, assessment.numerator_fact)
        denominator = _fact_at(state, assessment.denominator_fact)
        value_fact = _fact_at(state, assessment.value_fact)

        # --- data gaps -> targeted re-retrieval (the agentic loop) ---
        is_ratio = assessment.mode == "ratio"
        missing = bool(assessment.missing_metrics) or (
            (numerator is None or denominator is None) if is_ratio else value_fact is None
        )
        if missing:
            for query in assessment.followup_queries or [
                f"{pretty_metric(m)} value" for m in assessment.missing_metrics
            ]:
                queue(f"facts:{rule.rule_id}", query)
            bus.publish(
                Node.ANALYZER,
                EventType.NEED_MORE_RETRIEVAL,
                {
                    "covenant": rule.name,
                    "missing": assessment.missing_metrics,
                    "queries": assessment.followup_queries,
                    "why": assessment.rationale,
                },
            )
            state.findings.append(
                Finding(
                    rule_id=rule.rule_id,
                    covenant=rule.name,
                    required=f"{rule.operator} {fmt_value(rule.threshold, rule.unit)}",
                    actual="data missing",
                    status="data_missing",
                    notes=assessment.rationale,
                )
            )
            continue

        # --- deterministic computation (never the LLM) ---
        used_facts = [f for f in (numerator, denominator, value_fact) if f is not None]
        if is_ratio and numerator is not None and denominator is not None:
            bus.publish(
                Node.ANALYZER,
                EventType.TOOL_CALL,
                {
                    "tool": "compute_ratio",
                    "numerator": f"{numerator.metric}={numerator.value}",
                    "denominator": f"{denominator.metric}={denominator.value}",
                },
            )
            ratio = compute_ratio(
                numerator.value, denominator.value, pretty_metric(numerator.metric), pretty_metric(denominator.metric)
            )
            bus.publish(Node.ANALYZER, EventType.TOOL_RESULT, {"tool": "compute_ratio", "formula": ratio.formula})
            actual_value, computed_by = ratio.value, ratio.formula
        elif value_fact is not None:
            actual_value, computed_by = value_fact.value, f"direct: {value_fact.metric}={value_fact.value}"
        else:
            continue  # unreachable: the missing-guard above already queued a re-retrieval

        bus.publish(
            Node.ANALYZER,
            EventType.TOOL_CALL,
            {"tool": "check_threshold", "value": actual_value, "operator": rule.operator, "threshold": rule.threshold},
        )
        threshold_result = check_threshold(actual_value, rule.operator, rule.threshold)
        bus.publish(Node.ANALYZER, EventType.TOOL_RESULT, {"tool": "check_threshold", "detail": threshold_result.detail})

        status = "ok" if threshold_result.passed else "breach"
        notes = assessment.rationale

        # --- conflicting preliminary vs final figures -> prudence + clause check ---
        conflict_facts = [f for f in (_fact_at(state, i) for i in assessment.conflict_facts) if f]
        if len({round(f.value, 4) for f in conflict_facts}) > 1:
            status = "conflict"
            values = ", ".join(f"{fmt_value(f.value, rule.unit)} ({f.basis})" for f in conflict_facts)
            notes = (
                f"Conflicting figures for the same metric: {values}. Prudent provisional test "
                f"used the more conservative value pending verification of the governing clause. "
                + notes
            )
            used_facts.extend(conflict_facts)
            if not any(s.tag == f"clause:{rule.rule_id}" for s in state.snippets):
                queue(
                    f"clause:{rule.rule_id}",
                    "measurement supersession preliminary flash estimates final quarter-end figures govern",
                    doc_kind="credit_agreement",
                )
                bus.publish(
                    Node.ANALYZER,
                    EventType.NEED_MORE_RETRIEVAL,
                    {"covenant": rule.name, "why": "conflicting preliminary vs final figures — need the governing clause"},
                )

        # --- trend & projection (early warning: 'drifting toward breach') ---
        trend_points: list[TrendPoint] = []
        for pair in assessment.trend:
            pair_numerator = _fact_at(state, pair.numerator_fact)
            pair_denominator = _fact_at(state, pair.denominator_fact)
            pair_value = _fact_at(state, pair.value_fact)
            if pair_numerator and pair_denominator:
                trend_points.append(
                    TrendPoint(period=pair.period, value=compute_ratio(pair_numerator.value, pair_denominator.value).value)
                )
            elif pair_value:
                trend_points.append(TrendPoint(period=pair.period, value=pair_value.value))
        projection_note = ""
        if len(trend_points) >= 2:
            series = [(point.period, point.value) for point in trend_points]
            bus.publish(
                Node.ANALYZER,
                EventType.TOOL_CALL,
                {"tool": "project_linear", "series": [f"{p}: {v:.2f}" for p, v in series], "threshold": rule.threshold},
            )
            projection = project_linear(series, rule.threshold, rule.operator)
            bus.publish(Node.ANALYZER, EventType.TOOL_RESULT, {"tool": "project_linear", "detail": projection.detail})
            projection_note = projection.detail
            if (
                status == "ok"
                and projection.periods_to_threshold is not None
                and projection.periods_to_threshold <= AT_RISK_HORIZON_PERIODS
            ):
                status = "at_risk"

        # --- breaches demand a WHY: cross-check transactions + remedy clauses ---
        if status == "breach":
            if rule.rule_id not in state.cause_coverage and not any(
                s.tag == f"cause:{rule.rule_id}" for s in state.snippets
            ):
                components = " ".join(pretty_metric(c) for c in metric_components(rule.metric))
                queue(
                    f"cause:{rule.rule_id}",
                    f"{components} increase movement schedule drawdown transactions during the quarter",
                )
                queue(
                    f"clause:{rule.rule_id}",
                    "equity cure remedy covenant breach waiver",
                    doc_kind="credit_agreement",
                )
                bus.publish(
                    Node.ANALYZER,
                    EventType.NEED_MORE_RETRIEVAL,
                    {"covenant": rule.name, "why": "breach detected — retrieving transaction causes and remedy clauses"},
                )

        sources = [source for fact in used_facts for source in fact.sources]
        finding = Finding(
            rule_id=rule.rule_id,
            covenant=rule.name,
            required=f"{rule.operator} {fmt_value(rule.threshold, rule.unit)}",
            actual=fmt_value(actual_value, rule.unit),
            actual_value=actual_value,
            status=status,
            headroom=f"{threshold_result.headroom:+.2f}{'x' if rule.unit == 'x' else 'm'}",
            computed_by=computed_by,
            trend=trend_points,
            projection_note=projection_note,
            notes=notes,
            sources=sources,
        )
        state.findings.append(finding)
        bus.publish(
            Node.ANALYZER,
            EventType.FINDING,
            {
                "covenant": finding.covenant,
                "required": finding.required,
                "actual": finding.actual,
                "status": finding.status,
                "headroom": finding.headroom,
                "computed_by": finding.computed_by,
                "projection": finding.projection_note,
                "citations": [f"{s.section}" for s in finding.sources[:4]],
            },
        )

    # --- root-cause pass, once the cause evidence has been retrieved ---
    for rule in state.rules:
        cause_snippets = [s for s in state.snippets if s.tag == f"cause:{rule.rule_id}"]
        if not cause_snippets or rule.rule_id in state.cause_coverage:
            continue
        analysis = await ctx.llm.chat_json(
            CAUSE_SYSTEM,
            (
                f"Covenant breached: {rule.name} ({rule.metric}). Explain the movement of its "
                f"driving metric using these records:\n{snippets_block(cause_snippets)}"
            ),
            CauseAnalysis,
        )
        matched_amount = unexplained_amount = 0.0
        for item in analysis.items:
            state.causes.append(
                CauseMatch(
                    rule_id=rule.rule_id,
                    description=item.description,
                    amount=item.amount,
                    matched=item.matched,
                    sources=[source_from_snippets(item.source_section, item.source_quote, cause_snippets)],
                )
            )
            if item.amount:
                if item.matched:
                    matched_amount += item.amount
                else:
                    unexplained_amount += item.amount
        total = matched_amount + unexplained_amount
        if total > 0:
            state.cause_coverage[rule.rule_id] = round(matched_amount / total, 4)
        bus.publish(
            Node.ANALYZER,
            EventType.THOUGHT,
            {
                "covenant": rule.name,
                "cause_coverage": state.cause_coverage.get(rule.rule_id),
                "explained_eur_m": matched_amount,
                "unexplained_eur_m": unexplained_amount,
                "note": analysis.note,
            },
        )

    state.pending_retrievals.extend(followups)
