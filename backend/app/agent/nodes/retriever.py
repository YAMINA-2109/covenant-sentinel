"""RETRIEVER — executes pending retrieval requests (multi-turn by design).

'facts:*' requests use STRATIFIED retrieval: every non-agreement document
kind is searched separately so a small treasury note can never be drowned
out by a large report — in a covenant audit, the conflicting figure hiding
in a side document IS the point. Extraction LLM calls then run concurrently.

'cause:*' and 'clause:*' requests keep the raw passages as evidence snippets
for the Analyzer's root-cause pass and the Critic's clause checks.
"""

import asyncio

from app.agent.prompts import EXTRACTOR_SYSTEM
from app.agent.schemas import FactExtraction
from app.agent.state import AuditState, EvidenceSnippet, FinancialFact, RetrievalRequest
from app.agent.nodes.common import hits_block, slug, source_from_hits
from app.core.events import EventType, Node
from app.rag.store import RetrievalHit


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
    doc_kinds = list(dict.fromkeys(doc.kind for doc in state.documents))
    fact_kinds = [kind for kind in doc_kinds if kind != "credit_agreement"] or doc_kinds

    extraction_jobs: list[tuple[RetrievalRequest, list[RetrievalHit]]] = []

    for request in requests:
        if request.reason.startswith("facts:"):
            bus.publish(
                Node.RETRIEVER,
                EventType.RETRIEVAL_QUERY,
                {"query": request.query, "reason": request.reason, "doc_kind": " + ".join(fact_kinds)},
            )
            hits: list[RetrievalHit] = []
            seen_sections: set[str] = set()
            for kind in fact_kinds:
                for hit in await ctx.retriever.search(request.query, k=3, doc_kind=kind):
                    if hit.section_id in seen_sections:
                        continue
                    seen_sections.add(hit.section_id)
                    hits.append(hit)
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
            if hits:
                extraction_jobs.append((request, hits))
            else:
                bus.publish(
                    Node.RETRIEVER,
                    EventType.THOUGHT,
                    {"note": f"no passages found for '{request.query}'"},
                )
        else:  # cause:* / clause:* — keep raw evidence for downstream reasoning
            bus.publish(
                Node.RETRIEVER,
                EventType.RETRIEVAL_QUERY,
                {"query": request.query, "reason": request.reason, "doc_kind": request.doc_kind},
            )
            hits = await ctx.retriever.search(request.query, k=4, doc_kind=request.doc_kind)
            stored = 0
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

    async def extract(request: RetrievalRequest, hits: list[RetrievalHit]) -> None:
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

    if extraction_jobs:
        await asyncio.gather(*(extract(request, hits) for request, hits in extraction_jobs))
