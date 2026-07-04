"""LangGraph wiring of the audit pipeline.

PLANNER → RETRIEVER → ANALYZER —(pending retrievals?)→ RETRIEVER (loop)
                                └────────────────────→ CRITIC → SYNTHESIZER

Nodes are plain async functions over the typed AuditState; the graph only
handles sequencing and the retrieval loop, so the whole pipeline could be
re-wired or replayed trivially.
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.llm import VultrLLM
from app.agent.nodes import analyzer, critic, planner, retriever, synthesizer
from app.agent.state import AuditState
from app.core.config import get_settings
from app.core.events import EventType, Node, RunBus
from app.rag.store import DocumentStore, build_retriever


@dataclass
class Ctx:
    bus: RunBus
    store: DocumentStore
    retriever: Any
    llm: VultrLLM


def _wrap(node_fn, ctx: Ctx):
    async def node(state: AuditState) -> dict:
        await node_fn(state, ctx)
        return state.model_dump()

    return node


def _route_after_analyzer(state: AuditState) -> str:
    if state.pending_retrievals and state.retrieval_rounds < state.max_retrieval_rounds:
        return "retrieve_more"
    return "verify"


async def run_audit(state: AuditState, bus: RunBus) -> AuditState:
    store = DocumentStore()
    for doc in state.documents:
        store.add(doc)
    ctx = Ctx(bus=bus, store=store, retriever=await build_retriever(store), llm=VultrLLM())

    graph = StateGraph(AuditState)
    graph.add_node("planner", _wrap(planner.run_planner, ctx))
    graph.add_node("retriever", _wrap(retriever.run_retriever, ctx))
    graph.add_node("analyzer", _wrap(analyzer.run_analyzer, ctx))
    graph.add_node("critic", _wrap(critic.run_critic, ctx))
    graph.add_node("synthesizer", _wrap(synthesizer.run_synthesizer, ctx))
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "analyzer")
    graph.add_conditional_edges(
        "analyzer", _route_after_analyzer, {"retrieve_more": "retriever", "verify": "critic"}
    )
    graph.add_edge("critic", "synthesizer")
    graph.add_edge("synthesizer", END)

    result = await graph.compile().ainvoke(state, config={"recursion_limit": 60})
    final_state = AuditState.model_validate(result) if isinstance(result, dict) else result

    bus.publish(
        Node.SYSTEM,
        EventType.RUN_COMPLETED,
        {
            "verdicts": len(final_state.verdicts),
            "overall_confidence": final_state.overall_confidence,
            "retrieval_rounds": final_state.retrieval_rounds,
        },
    )
    _persist_trace(final_state, bus)

    # reflect results on the caller's state object so GET /audits/{id} serves them
    for field in AuditState.model_fields:
        setattr(state, field, getattr(final_state, field))
    return final_state


def _persist_trace(state: AuditState, bus: RunBus) -> None:
    """Every run is written to disk: replayable evidence of a real execution."""
    try:
        trace_dir = get_settings().trace_dir
        os.makedirs(trace_dir, exist_ok=True)
        path = os.path.join(trace_dir, f"{state.run_id}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "events": [event.model_dump() for event in bus.history],
                    "state": state.model_dump(),
                },
                handle,
                indent=1,
                default=str,
            )
    except OSError:
        pass  # tracing must never take down a run
