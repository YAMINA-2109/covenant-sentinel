"""Retrieval over parsed documents.

Two interchangeable retrievers behind one interface:

- ``VultronReranker`` — two-stage hybrid retrieval: BM25 candidate recall
  over all sections, then semantic reranking by a VultronRetriever model on
  Vultr Serverless Inference (`POST /v1/rerank`) — the track's retrieval
  technology used in its intended role.
- ``BM25Retriever`` — zero-dependency lexical fallback, so a network hiccup
  or an unavailable reranker never kills a demo run. A failed rerank call
  degrades to BM25 order for that query instead of failing the run.

Retrieval is multi-turn by design: agent nodes issue new, more specific
queries whenever analysis exposes a gap.
"""

import re

import httpx
from pydantic import BaseModel

from app.agent.state import DocSection, ParsedDoc


class RetrievalHit(BaseModel):
    doc_id: str
    filename: str
    doc_kind: str
    section_id: str
    title: str
    page: int | None = None
    text: str
    score: float


class DocumentStore:
    def __init__(self) -> None:
        self._entries: list[tuple[ParsedDoc, DocSection]] = []

    def add(self, doc: ParsedDoc) -> None:
        for section in doc.sections:
            self._entries.append((doc, section))

    @property
    def entries(self) -> list[tuple[ParsedDoc, DocSection]]:
        return self._entries


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9.]+", text.lower())


class BM25Retriever:
    name = "bm25-local"

    def __init__(self, store: DocumentStore) -> None:
        from rank_bm25 import BM25Okapi

        self._store = store
        corpus = [
            _tokenize(f"{section.title}\n{section.text}")
            for _, section in store.entries
        ]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    async def search(
        self, query: str, k: int = 4, doc_kind: str | None = None
    ) -> list[RetrievalHit]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(
            zip(self._store.entries, scores), key=lambda pair: pair[1], reverse=True
        )
        hits: list[RetrievalHit] = []
        for (doc, section), score in ranked:
            if doc_kind and doc.kind != doc_kind:
                continue
            hits.append(
                RetrievalHit(
                    doc_id=doc.doc_id,
                    filename=doc.filename,
                    doc_kind=doc.kind,
                    section_id=section.section_id,
                    title=section.title,
                    page=section.page,
                    text=section.text,
                    score=round(float(score), 4),
                )
            )
            if len(hits) >= k:
                break
        return hits


class VultronReranker:
    """BM25 candidate recall + VultronRetriever semantic rerank on Vultr."""

    RECALL_POOL = 10

    def __init__(self, store: DocumentStore, model: str) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        self.name = f"hybrid: bm25 recall -> rerank {model}"
        self._bm25 = BM25Retriever(store)
        self._model = model
        self._url = settings.vultr_base_url.rstrip("/") + "/rerank"
        self._headers = {"Authorization": f"Bearer {settings.vultr_api_key}"}

    async def rerank_probe(self) -> None:
        await self._rerank("connectivity probe", ["a", "b"], top_n=1)

    async def _rerank(self, query: str, documents: list[str], top_n: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self._url,
                headers=self._headers,
                json={"model": self._model, "query": query, "documents": documents, "top_n": top_n},
            )
            response.raise_for_status()
            return response.json().get("results", [])

    async def search(
        self, query: str, k: int = 4, doc_kind: str | None = None
    ) -> list[RetrievalHit]:
        candidates = await self._bm25.search(query, k=max(self.RECALL_POOL, k * 3), doc_kind=doc_kind)
        if len(candidates) <= k:
            return candidates
        documents = [f"{hit.title}\n{hit.text}"[:2000] for hit in candidates]
        try:
            results = await self._rerank(query, documents, top_n=k)
        except Exception:
            return candidates[:k]  # degrade to BM25 order, never fail the run
        hits: list[RetrievalHit] = []
        for item in results[:k]:
            index = item.get("index")
            if not isinstance(index, int) or not (0 <= index < len(candidates)):
                continue
            hit = candidates[index].model_copy()
            hit.score = round(float(item.get("relevance_score", 0.0)), 4)
            hits.append(hit)
        return hits or candidates[:k]


async def build_retriever(store: DocumentStore):
    """Prefer the VultronRetriever reranker when configured and reachable;
    otherwise fall back to BM25 so the pipeline always runs."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.vultr_retriever_model:
        retriever = VultronReranker(store, settings.vultr_retriever_model)
        try:
            await retriever.rerank_probe()
            return retriever
        except Exception:
            pass
    return BM25Retriever(store)
