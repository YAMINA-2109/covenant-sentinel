"""RETRIEVER — executes pending retrieval requests (multi-turn by design).

'facts:*' requests are distilled into typed FinancialFacts via the extraction
LLM; 'cause:*' and 'clause:*' requests keep the raw passages as evidence
snippets for the Analyzer's root-cause pass and the Critic's clause checks.
"""

from app.agent.prompts import EXTRACTOR_SYSTEM
from app.agent.schemas import FactExtraction
from app.agent.state import AuditState, EvidenceSnippet, FinancialFact
from app.agent.nodes.common import hits_block, slug, source_from_hits
from app.core.events import EventType, Node


async def run_retriever(state: AuditState, ctx) -> None:
    bus = ctx.bus
    requests, state.pending_retrievals = state.pending_retrievals, []
    state.retrieval_rounds += 1
    bus.publish(
        Node.RETRIEVER,
        EventType.NODE_STARTED,
        {
            "round": state.retrieval_rounds,
            "requests": len(requests),
            "engine": getattr(ctx.retriever, "name", "unknown"),
        },
    )

    fact_keys = {
        (fact.metric, fact.period, fact.basis, round(fact.value, 4)) for fact in state.facts
    }
    snippet_keys = {(snippet.doc_id, snippet.section, snippet.tag) for snippet in state.snippets}

    for request in requests:
        bus.publish(
            Node.RETRIEVER,
            EventType.RETRIEVAL_QUERY,
            {"query": request.query, "reason": request.reason, "doc_kind": request.doc_kind},
        )
        hits = await ctx.retriever.search(request.query, k=4, doc_kind=request.doc_kind)
        for hit in hits:
            bus.publish(
                Node.RETRIEVER,
                EventType.RETRIEVAL_HIT,
                {
                    "doc": hit.filename,
                    "section": hit.title,
                    "page": hit.page,
                    "score": hit.score,
                    "preview": hit.text[:160],
                },
            )
        if not hits:
            bus.publish(
                Node.RETRIEVER, EventType.THOUGHT, {"note": f"no passages found for '{request.query}'"}
            )
            continue

        if request.reason.startswith("facts:"):
            extraction = await ctx.llm.chat_json(
                EXTRACTOR_SYSTEM,
                f"Query: {request.query}\n\nExcerpts:\n{hits_block(hits)}",
                FactExtraction,
            )
            added = 0
            for item in extraction.facts:
                fact = FinancialFact(
                    metric=slug(item.metric),
                    value=item.value,
                    unit=item.unit or "EUR_m",
                    period=item.period,
                    basis=item.basis,
                    sources=[source_from_hits(item.source_section, item.source_quote, hits)],
                )
                key = (fact.metric, fact.period, fact.basis, round(fact.value, 4))
                if key in fact_keys:
                    continue
                fact_keys.add(key)
                state.facts.append(fact)
                added += 1
            bus.publish(
                Node.RETRIEVER,
                EventType.THOUGHT,
                {"note": f"extracted {added} new fact(s) for '{request.query}'"},
            )
        else:  # cause:* / clause:* — keep raw evidence for downstream reasoning
            stored = 0
            for hit in hits:
                key = (hit.doc_id, hit.title, request.reason)
                if key in snippet_keys:
                    continue
                snippet_keys.add(key)
                state.snippets.append(
                    EvidenceSnippet(
                        doc_id=hit.doc_id,
                        section=hit.title,
                        page=hit.page,
                        text=hit.text,
                        tag=request.reason,
                    )
                )
                stored += 1
            bus.publish(
                Node.RETRIEVER,
                EventType.THOUGHT,
                {"note": f"stored {stored} evidence snippet(s) [{request.reason}]"},
            )
