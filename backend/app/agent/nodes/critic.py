"""CRITIC — the adversarial second reviewer (the system's signature).

For every finding it (a) mechanically verifies each citation quote against
the actual document text — no LLM involved — and (b) challenges the finding
with an independent LLM pass on freshness, definition basis and consistency,
armed with the governing clauses retrieved for that rule. Its checklist
outcomes feed the deterministic confidence score.
"""

import asyncio
import json

from app.agent.prompts import CRITIC_SYSTEM
from app.agent.schemas import CriticOutput
from app.agent.state import AuditState, CriticCheck, Finding, SourceRef, Verdict
from app.agent.nodes.common import metric_components, normalize, snippets_block
from app.core.events import EventType, Node
from app.tools.confidence import score_verdict


def _verify_citations(finding: Finding, ctx) -> CriticCheck:
    """Mechanical check: every quoted citation must literally appear in the
    cited document. This one is code, not model output — it cannot be charmed."""
    checked = failed = 0
    failures: list[str] = []
    doc_texts: dict[str, str] = {}
    for doc, section in ctx.store.entries:
        doc_texts.setdefault(doc.doc_id, "")
        doc_texts[doc.doc_id] += "\n" + section.text
    for source in finding.sources:
        if not source.quote:
            continue
        checked += 1
        haystack = normalize(doc_texts.get(source.doc_id, ""))
        if normalize(source.quote) not in haystack:
            failed += 1
            failures.append(f"{source.section}: quote not found in {source.doc_id}")
    if checked == 0:
        return CriticCheck(check="citation_valid", passed=True, note="no verbatim quotes to verify")
    if failed:
        return CriticCheck(check="citation_valid", passed=False, note="; ".join(failures)[:300])
    return CriticCheck(check="citation_valid", passed=True, note=f"{checked}/{checked} quotes located verbatim in source documents")


async def run_critic(state: AuditState, ctx) -> None:
    bus = ctx.bus
    bus.publish(Node.CRITIC, EventType.NODE_STARTED, {"findings_to_challenge": len(state.findings)})

    async def challenge(finding: Finding) -> Verdict:
        rule = next((r for r in state.rules if r.rule_id == finding.rule_id), None)
        components = set(metric_components(rule.metric)) if rule else set()
        related = [
            fact
            for fact in state.facts
            if fact.metric in components
            or any(fact.metric in c or c in fact.metric for c in components)
        ]
        if not related:  # naming drift between rule metric and fact metric must
            related = state.facts  # never make the Critic believe there is no data
        related_facts = [
            f"- {fact.metric}={fact.value} ({fact.unit}, period={fact.period or '?'}, basis={fact.basis})"
            for fact in related
        ]
        clause_snippets = [s for s in state.snippets if s.tag == f"clause:{finding.rule_id}"]
        causes = [c for c in state.causes if c.rule_id == finding.rule_id]

        context = (
            f"FINDING under challenge:\n{json.dumps(finding.model_dump(exclude={'sources', 'trend'}), indent=1)}\n\n"
            f"COVENANT: {rule.name if rule else finding.covenant} — requirement "
            f"{finding.required}; measurement basis notes: "
            f"{rule.definition_notes if rule else 'unknown'}\n\n"
            f"ALL FACTS on this metric family (note the bases):\n"
            + ("\n".join(related_facts) or "none")
            + "\n\nGOVERNING CLAUSES retrieved:\n"
            + (snippets_block(clause_snippets) or "none")
            + "\n\nDOCUMENTED CAUSES:\n"
            + ("\n".join(f"- {c.description} (EUR {c.amount}m, documented={c.matched})" for c in causes) or "none")
        )
        output = await ctx.llm.chat_json(CRITIC_SYSTEM, context, CriticOutput)

        checks = [_verify_citations(finding, ctx)]
        checks += [
            CriticCheck(check=c.check, passed=c.passed, note=c.note)
            for c in output.checks
            if c.check != "citation_valid"  # the mechanical result above wins
        ]
        for check in checks:
            bus.publish(
                Node.CRITIC,
                EventType.CRITIC_CHECK,
                {"covenant": finding.covenant, "check": check.check, "passed": check.passed, "note": check.note},
            )

        original = finding.status
        final_status = output.final_status
        overturned = output.overturned or (
            final_status != original and not (original == "conflict" and final_status == "breach")
        )

        sources = list(finding.sources)
        if output.key_source_quote:
            snippet_pool = clause_snippets or state.snippets
            for snippet in snippet_pool:
                if normalize(output.key_source_quote)[:80] in normalize(snippet.text):
                    sources.append(
                        SourceRef(
                            doc_id=snippet.doc_id,
                            section=snippet.section,
                            page=snippet.page,
                            quote=output.key_source_quote[:300],
                        )
                    )
                    break

        confidence = score_verdict(
            checks,
            state.cause_coverage.get(finding.rule_id),
            projected=final_status == "at_risk",
        )
        verdict = Verdict(
            rule_id=finding.rule_id,
            original_status=original,
            final_status=final_status,
            overturned=overturned,
            checks=checks,
            confidence=confidence,
            rationale=output.rationale,
            sources=sources,
        )
        bus.publish(
            Node.CRITIC,
            EventType.VERDICT,
            {
                "covenant": finding.covenant,
                "original_status": original,
                "final_status": final_status,
                "overturned": overturned,
                "confidence": confidence,
                "rationale": output.rationale[:400],
                "citations": [
                    {"doc_id": s.doc_id, "section": s.section, "page": s.page, "quote": s.quote}
                    for s in sources[:5]
                    if s.quote
                ],
            },
        )
        return verdict

    # Findings are challenged concurrently — each is an independent review.
    state.verdicts = list(await asyncio.gather(*(challenge(f) for f in state.findings)))
