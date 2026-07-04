"""PLANNER — reads the credit agreement, decides which covenants to test,
and seeds the first round of retrieval requests."""

from app.agent.prompts import PLANNER_SYSTEM
from app.agent.schemas import PlannerOutput
from app.agent.state import AuditState, CovenantRule, RetrievalRequest
from app.agent.nodes.common import hits_block, metric_components, pretty_metric, slug, source_from_hits
from app.core.events import EventType, Node

PLANNER_QUERIES = [
    "financial covenants leverage ratio minimum liquidity interest coverage",
    "definitions EBITDA total debt net interest expense liquidity measurement",
]


def _normalize_threshold(threshold: float, unit: str) -> tuple[float, str]:
    """Monetary thresholds are normalised to EUR millions regardless of how the
    model expressed them; ratio thresholds pass through untouched."""
    if unit != "x" and threshold >= 100_000:
        return threshold / 1_000_000, "EUR_m"
    if unit != "x":
        return threshold, "EUR_m"
    return threshold, unit


async def run_planner(state: AuditState, ctx) -> None:
    bus = ctx.bus
    bus.publish(Node.PLANNER, EventType.NODE_STARTED, {"task": "identify covenants to test"})

    # If no upload was recognisably the agreement, search every document.
    agreement_kind = (
        "credit_agreement"
        if any(doc.kind == "credit_agreement" for doc in state.documents)
        else None
    )
    hits, seen = [], set()
    for query in PLANNER_QUERIES:
        bus.publish(
            Node.PLANNER,
            EventType.RETRIEVAL_QUERY,
            {"query": query, "target": agreement_kind or "all documents"},
        )
        for hit in await ctx.retriever.search(query, k=4, doc_kind=agreement_kind):
            if hit.section_id in seen:
                continue
            seen.add(hit.section_id)
            hits.append(hit)
            bus.publish(
                Node.PLANNER,
                EventType.RETRIEVAL_HIT,
                {"doc": hit.filename, "section": hit.title, "page": hit.page, "score": hit.score},
            )

    inventory = "\n".join(f"- {d.filename} ({d.kind})" for d in state.documents)
    output = await ctx.llm.chat_json(
        PLANNER_SYSTEM,
        (
            f"Documents uploaded for this audit:\n{inventory}\n\n"
            f"Credit agreement excerpts:\n{hits_block(hits)}\n\n"
            "Identify every financial covenant to test and the ordered audit plan."
        ),
        PlannerOutput,
    )
    if not output.rules:
        raise RuntimeError("Planner identified no financial covenants in the agreement")

    seen_queries: set[str] = set()
    for extracted in output.rules:
        threshold, unit = _normalize_threshold(extracted.threshold, extracted.unit)
        rule = CovenantRule(
            rule_id=slug(extracted.rule_id or extracted.name),
            name=extracted.name,
            metric=extracted.metric,
            operator=extracted.operator,
            threshold=threshold,
            unit=unit,
            definition_notes=extracted.definition_notes,
            sources=[source_from_hits(extracted.source_section, extracted.source_quote, hits)],
        )
        state.rules.append(rule)
        for component in metric_components(rule.metric):
            query = f"{pretty_metric(component)} current and prior quarter values"
            if query in seen_queries:
                continue
            seen_queries.add(query)
            state.pending_retrievals.append(
                RetrievalRequest(reason=f"facts:{rule.rule_id}", query=query)
            )

    state.plan = output.plan or [f"Test {rule.name}" for rule in state.rules]
    bus.publish(
        Node.PLANNER,
        EventType.THOUGHT,
        {
            "plan": state.plan,
            "covenants": [
                f"{rule.name}: {rule.operator} {rule.threshold}{'' if rule.unit == 'x' else ' ' + rule.unit}"
                for rule in state.rules
            ],
            "seeded_queries": [request.query for request in state.pending_retrievals],
        },
    )
