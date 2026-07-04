"""Shared helpers for agent nodes: source resolution, formatting, parsing."""

import re

from app.agent.state import EvidenceSnippet, SourceRef
from app.rag.store import RetrievalHit


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().casefold()).strip("_")


def metric_components(metric: str) -> list[str]:
    return [slug(part) for part in metric.split("/") if part.strip()]


def pretty_metric(metric: str) -> str:
    return metric.replace("_", " ").strip()


def fmt_value(value: float, unit: str) -> str:
    if unit == "x":
        return f"{value:.2f}x"
    if unit.upper().startswith("EUR"):
        return f"EUR {value:,.1f}m"
    return f"{value:,.2f} {unit}"


def source_from_hits(section_title: str, quote: str, hits: list[RetrievalHit]) -> SourceRef:
    """Resolve the LLM's (section title, quote) claim to a real document locator."""
    wanted = normalize(section_title) if section_title else ""
    for hit in hits:
        title = normalize(hit.title)
        if wanted and (wanted in title or title in wanted):
            return SourceRef(doc_id=hit.doc_id, section=hit.title, page=hit.page, quote=quote[:300])
    if quote:
        needle = normalize(quote)
        for hit in hits:
            if needle and needle in normalize(hit.text):
                return SourceRef(doc_id=hit.doc_id, section=hit.title, page=hit.page, quote=quote[:300])
    if hits:
        first = hits[0]
        return SourceRef(
            doc_id=first.doc_id, section=section_title or first.title, page=first.page, quote=quote[:300]
        )
    return SourceRef(doc_id="unknown", section=section_title, quote=quote[:300])


def source_from_snippets(
    section_title: str, quote: str, snippets: list[EvidenceSnippet]
) -> SourceRef:
    wanted = normalize(section_title) if section_title else ""
    for snippet in snippets:
        title = normalize(snippet.section)
        if wanted and (wanted in title or title in wanted):
            return SourceRef(
                doc_id=snippet.doc_id, section=snippet.section, page=snippet.page, quote=quote[:300]
            )
    if quote:
        needle = normalize(quote)
        for snippet in snippets:
            if needle and needle in normalize(snippet.text):
                return SourceRef(
                    doc_id=snippet.doc_id, section=snippet.section, page=snippet.page, quote=quote[:300]
                )
    if snippets:
        first = snippets[0]
        return SourceRef(
            doc_id=first.doc_id, section=section_title or first.section, page=first.page, quote=quote[:300]
        )
    return SourceRef(doc_id="unknown", section=section_title, quote=quote[:300])


def hits_block(hits: list[RetrievalHit]) -> str:
    parts = []
    for hit in hits:
        page = f" | p.{hit.page}" if hit.page else ""
        parts.append(f"--- [{hit.filename} | {hit.title}{page}]\n{hit.text}")
    return "\n".join(parts)


def snippets_block(snippets: list[EvidenceSnippet]) -> str:
    parts = []
    for snippet in snippets:
        page = f" | p.{snippet.page}" if snippet.page else ""
        parts.append(f"--- [{snippet.doc_id} | {snippet.section}{page}]\n{snippet.text}")
    return "\n".join(parts)
