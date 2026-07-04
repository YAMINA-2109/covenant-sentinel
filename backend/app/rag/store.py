"""Retrieval over parsed documents.

Two interchangeable retrievers behind one interface:

- ``EmbeddingRetriever`` — VultronRetriever embeddings served by Vultr
  Serverless Inference (the track's retrieval technology), cosine similarity
  over an in-memory numpy index. Documents here are small; no vector DB
  needed.
- ``BM25Retriever`` — zero-dependency lexical fallback, so a network hiccup
  or an unavailable embedding model never kills a demo run.

Retrieval is multi-turn by design: agent nodes issue new, more specific
queries whenever analysis exposes a gap.
"""

import re

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


class EmbeddingRetriever:
    """VultronRetriever embeddings via the Vultr OpenAI-compatible endpoint."""

    def __init__(self, store: DocumentStore, model: str) -> None:
        from openai import AsyncOpenAI

        from app.core.config import get_settings

        settings = get_settings()
        self.name = f"vultron-embeddings:{model}"
        self._store = store
        self._model = model
        self._client = AsyncOpenAI(
            api_key=settings.vultr_api_key, base_url=settings.vultr_base_url
        )
        self._matrix = None  # built lazily on first search

    async def _embed(self, texts: list[str]):
        import numpy as np

        response = await self._client.embeddings.create(model=self._model, input=texts)
        vectors = np.array([item.embedding for item in response.data], dtype="float32")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.clip(norms, 1e-9, None)

    async def _ensure_index(self) -> None:
        if self._matrix is None and self._store.entries:
            texts = [
                f"{section.title}\n{section.text}" for _, section in self._store.entries
            ]
            self._matrix = await self._embed(texts)

    async def search(
        self, query: str, k: int = 4, doc_kind: str | None = None
    ) -> list[RetrievalHit]:
        await self._ensure_index()
        if self._matrix is None:
            return []
        query_vec = (await self._embed([query]))[0]
        scores = self._matrix @ query_vec
        ranked = sorted(
            zip(self._store.entries, scores.tolist()),
            key=lambda pair: pair[1],
            reverse=True,
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


async def build_retriever(store: DocumentStore):
    """Prefer VultronRetriever embeddings when configured and reachable;
    otherwise fall back to BM25 so the pipeline always runs."""
    from app.core.config import get_settings

    settings = get_settings()
    if settings.vultr_embed_model:
        retriever = EmbeddingRetriever(store, settings.vultr_embed_model)
        try:
            await retriever._embed(["connectivity probe"])
            return retriever
        except Exception:
            pass
    return BM25Retriever(store)
