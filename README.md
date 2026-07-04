# CovenantSentinel

**An agentic covenant-compliance auditor for credit teams — it reads the credit agreement, reads the borrower's financials, computes ratios with deterministic tools, challenges its own findings with an adversarial Critic, and outputs a cited escalation memo with an evidence-based confidence score.**

> 🏗️ Built from scratch during the **RAISE Summit Hackathon 2026** (July 4–5, Paris) — **Vultr Enterprise Agent track**. Every commit in this repository was made during the event.

## The problem

Banks and private-credit funds monitor loan covenants by hand: open a 40-page credit agreement, find the covenant clauses, open the quarterly report, find the right figures (LTM, not quarterly!), compute, compare — repeated across hundreds of borrowers every quarter. It is slow, error-prone, and a missed breach is a real financial risk.

## What the agent does

1. **Plans** which covenants to test after reading the agreement's covenant section
2. **Retrieves** the rules (thresholds, definitions) from the credit agreement — with citations
3. **Retrieves** the figures from the financial report and treasury pack — with citations
4. **Calls deterministic tools** to compute ratios, headroom and trend projections — the LLM never does arithmetic
5. **Decides**: breach / at-risk (drifting toward breach) / ok / conflicting evidence
6. **Retrieves again** when analysis exposes a gap (e.g. the covenant requires *LTM* EBITDA but the first pass found the quarterly figure), and cross-checks debt transactions to explain *why* a metric moved
7. **Critic pass** — a second, adversarial agent re-checks every finding (data freshness, definition basis, citation validity) and kills false positives
8. **Synthesizes** an escalation memo: confirmed breaches, discarded false positives, early warnings, per-finding citations, recommended actions, and a **deterministically computed confidence score**

## Architecture

```
[Upload docs] → PLANNER → RETRIEVER ⇄ ANALYZER (deterministic tools) → CRITIC → SYNTHESIZER → Cited memo + confidence
                              ↑ multi-turn retrieval loop whenever analysis exposes a gap
        Every step streams live to the UI over SSE — you watch the agent reason.
```

## Stack

- **LLM**: Vultr Serverless Inference (`Qwen/Qwen3.5-397B-A17B`), streaming with retry — no dependency on native function-calling (JSON-schema prompting + Pydantic validation)
- **Retrieval**: hybrid two-stage — BM25 candidate recall, then semantic reranking by `vultr/VultronRetrieverPrime-Qwen3.5-8B` via Vultr's `/v1/rerank` (pure-BM25 fallback so a network hiccup never kills a run)
- **Orchestration**: LangGraph over a typed Pydantic state
- **Backend**: FastAPI + SSE (live reasoning trace, replayable — every run persisted to `traces/`)
- **Frontend**: React + Vite + TypeScript + Tailwind

## Run it

### Backend

```
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Unix)
pip install -r requirements.txt
copy .env.example .env          # then put your VULTR_API_KEY inside
uvicorn app.main:app --reload --port 8000
```

### Frontend

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and upload the three documents from `fixtures/`.

## Demo scenario

See [`fixtures/README.md`](fixtures/README.md): one real breach (leverage 3.70x vs a 3.50x cap, cause-matched to an acquisition drawdown), one false positive the Critic eliminates (preliminary vs final cash figures), and one early warning (interest coverage drifting toward its floor, with a projected breach quarter).

## License

MIT
