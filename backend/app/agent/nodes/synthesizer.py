"""SYNTHESIZER — writes the escalation memo a credit officer would send.

The memo is generated from the verified verdicts only; the confidence
methodology footnote is appended by code so it can never be hallucinated.
"""

import json

from app.agent.prompts import SYNTHESIZER_SYSTEM
from app.agent.state import AuditState
from app.agent.nodes.common import snippets_block
from app.core.events import EventType, Node
from app.tools.confidence import overall_confidence

METHODOLOGY_FOOTNOTE = (
    "\n\n---\n*Methodology: every figure was computed by deterministic tools, "
    "never by the language model. Confidence per finding = 80% weighted Critic "
    "checks (citation validity 30%, data freshness 25%, definition basis 25%, "
    "internal consistency 20%) + 20% cause coverage — the share of the flagged "
    "movement matched to clearly documented causes, as required by the covenant-"
    "monitoring brief. Overall confidence is the weakest actionable finding.*"
)


async def run_synthesizer(state: AuditState, ctx) -> None:
    bus = ctx.bus
    bus.publish(Node.SYNTHESIZER, EventType.NODE_STARTED, {})

    actionable = [v.confidence for v in state.verdicts if v.final_status in ("breach", "at_risk")]
    state.overall_confidence = overall_confidence(actionable or [v.confidence for v in state.verdicts])

    verdict_context = []
    for verdict in state.verdicts:
        finding = next((f for f in state.findings if f.rule_id == verdict.rule_id), None)
        verdict_context.append(
            {
                "covenant": finding.covenant if finding else verdict.rule_id,
                "required": finding.required if finding else "",
                "actual": finding.actual if finding else "",
                "headroom": finding.headroom if finding else "",
                "computed_by": finding.computed_by if finding else "",
                "trend": [f"{p.period}: {p.value:.2f}" for p in (finding.trend if finding else [])],
                "projection": finding.projection_note if finding else "",
                "original_status": verdict.original_status,
                "final_status": verdict.final_status,
                "overturned": verdict.overturned,
                "confidence_pct": round(verdict.confidence * 100),
                "rationale": verdict.rationale,
                "citations": [
                    f"{source.section}" + (f", p.{source.page}" if source.page else "")
                    for source in (verdict.sources or (finding.sources if finding else []))[:5]
                ],
            }
        )
    causes_context = [
        {
            "covenant": cause.rule_id,
            "description": cause.description,
            "amount_eur_m": cause.amount,
            "documented": cause.matched,
        }
        for cause in state.causes
    ]
    clause_material = snippets_block([s for s in state.snippets if s.tag.startswith("clause:")])

    memo = await ctx.llm.chat(
        SYNTHESIZER_SYSTEM,
        (
            f"Documents audited: {', '.join(d.filename for d in state.documents)}\n\n"
            f"VERDICTS (verified by the Critic):\n{json.dumps(verdict_context, indent=1)}\n\n"
            f"ROOT CAUSES:\n{json.dumps(causes_context, indent=1)}\n\n"
            f"CAUSE COVERAGE by covenant: {json.dumps(state.cause_coverage)}\n\n"
            f"RELEVANT CLAUSES (for recommended actions):\n{clause_material or 'none'}\n\n"
            f"Overall confidence: {round((state.overall_confidence or 0) * 100)}%.\n"
            "Write the escalation memo now."
        ),
    )
    state.memo_markdown = memo.strip() + METHODOLOGY_FOOTNOTE

    bus.publish(
        Node.SYNTHESIZER,
        EventType.MEMO,
        {
            "markdown": state.memo_markdown,
            "overall_confidence": state.overall_confidence,
            "verdicts": [
                {
                    "covenant": entry["covenant"],
                    "final_status": entry["final_status"],
                    "overturned": entry["overturned"],
                    "confidence_pct": entry["confidence_pct"],
                }
                for entry in verdict_context
            ],
        },
    )
