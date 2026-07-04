"""Offline integration tests: everything deterministic must work without any
API key — document parsing on the real fixtures, section locators, and BM25
retrieval landing on the sections the demo scenario depends on."""

import asyncio
from pathlib import Path

from app.ingest.parser import parse_upload
from app.rag.store import BM25Retriever, DocumentStore

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _load_store() -> DocumentStore:
    store = DocumentStore()
    for index, name in enumerate(
        [
            "acme_credit_agreement.txt",
            "acme_q2_2026_financial_report.txt",
            "acme_treasury_pack_q2_2026.txt",
        ]
    ):
        raw = (FIXTURES / name).read_bytes()
        store.add(parse_upload(f"doc{index}", name, raw))
    return store


def test_fixtures_parse_into_sections():
    store = _load_store()
    titles = [section.title for _, section in store.entries]
    assert any("7.1" in title for title in titles), "covenant section must be located"
    assert any("NOTE 4" in title.upper() for title in titles), "LTM note must be located"
    assert any("9.4" in title for title in titles), "supersession clause must be located"
    assert any("DEBT MOVEMENT" in title.upper() for title in titles)


def test_bm25_finds_covenants_definitions_and_causes():
    asyncio.run(_run_bm25_checks())


async def _run_bm25_checks():
    retriever = BM25Retriever(_load_store())

    covenant_hits = await retriever.search(
        "financial covenants leverage ratio minimum liquidity interest coverage",
        k=4,
        doc_kind="credit_agreement",
    )
    assert any("7.1" in hit.title for hit in covenant_hits)

    ltm_hits = await retriever.search("LTM EBITDA current and prior quarter values", k=4)
    assert any("NOTE 4" in hit.title.upper() for hit in ltm_hits)

    clause_hits = await retriever.search(
        "measurement supersession preliminary flash estimates final quarter-end figures govern",
        k=3,
        doc_kind="credit_agreement",
    )
    assert any("9.4" in hit.title for hit in clause_hits)

    cause_hits = await retriever.search(
        "total debt increase movement schedule drawdown transactions during the quarter", k=4
    )
    assert any("DEBT MOVEMENT" in hit.title.upper() for hit in cause_hits)

    cash_hits = await retriever.search("unrestricted cash current and prior quarter values", k=4)
    joined = " ".join(hit.text for hit in cash_hits)
    assert "4.2" in joined and "5.3" in joined, "both conflicting cash figures must surface"


def test_agent_graph_imports_cleanly():
    from app.agent.graph import run_audit  # noqa: F401
    from app.main import app  # noqa: F401
