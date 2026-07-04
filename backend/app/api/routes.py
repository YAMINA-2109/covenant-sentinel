"""HTTP surface: start an audit, stream its reasoning trace, fetch final state."""

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.agent.state import AuditState
from app.core.events import EventType, Node, RunBus
from app.ingest.parser import parse_upload

router = APIRouter(prefix="/api")


class RunContext:
    def __init__(self, state: AuditState, bus: RunBus) -> None:
        self.state = state
        self.bus = bus
        self.task: asyncio.Task | None = None


_RUNS: dict[str, RunContext] = {}


async def run_pipeline(context: RunContext) -> None:
    """Pipeline entrypoint. The agent graph (planner → retriever ⇄ analyzer →
    critic → synthesizer) is wired in app/agent/graph.py; ingestion below is
    already live."""
    state, bus = context.state, context.bus
    try:
        bus.publish(
            Node.SYSTEM,
            EventType.RUN_STARTED,
            {
                "documents": [
                    {"filename": d.filename, "kind": d.kind, "sections": len(d.sections)}
                    for d in state.documents
                ]
            },
        )
        for doc in state.documents:
            bus.publish(
                Node.SYSTEM,
                EventType.DOC_PARSED,
                {
                    "doc_id": doc.doc_id,
                    "filename": doc.filename,
                    "kind": doc.kind,
                    "sections": [s.title for s in doc.sections],
                },
            )

        from app.agent.graph import run_audit  # lazy: keeps API importable if deps are mid-install

        await run_audit(state, bus)
    except Exception as exc:  # surface real failures to the UI, never hang the stream
        bus.publish(Node.SYSTEM, EventType.RUN_FAILED, {"error": str(exc)})


def _start_run(named_blobs: list[tuple[str, bytes]]) -> dict:
    run_id = uuid.uuid4().hex[:12]
    state = AuditState(run_id=run_id)
    for index, (filename, data) in enumerate(named_blobs):
        state.documents.append(parse_upload(f"doc{index}", filename, data))
    context = RunContext(state, RunBus(run_id))
    _RUNS[run_id] = context
    context.task = asyncio.create_task(run_pipeline(context))
    return {"run_id": run_id}


@router.post("/audits")
async def create_audit(files: list[UploadFile]) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="upload at least one document")
    named_blobs = [
        (upload.filename or f"doc{index}.txt", await upload.read())
        for index, upload in enumerate(files)
    ]
    return _start_run(named_blobs)


@router.post("/audits/demo")
async def create_demo_audit() -> dict:
    """One-click demo: audit the bundled ACME case (see fixtures/README.md)."""
    fixtures = Path(__file__).resolve().parents[3] / "fixtures"
    names = [
        "acme_credit_agreement.txt",
        "acme_q2_2026_financial_report.txt",
        "acme_treasury_pack_q2_2026.txt",
    ]
    named_blobs = []
    for name in names:
        path = fixtures / name
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"fixture not found: {name}")
        named_blobs.append((name, path.read_bytes()))
    return _start_run(named_blobs)


@router.get("/audits/{run_id}/events")
async def stream_events(run_id: str) -> EventSourceResponse:
    context = _RUNS.get(run_id)
    if context is None:
        raise HTTPException(status_code=404, detail="unknown run")

    async def generator():
        async for event in context.bus.subscribe():
            yield {"data": event.model_dump_json()}

    return EventSourceResponse(generator())


@router.get("/audits/{run_id}")
async def get_audit(run_id: str) -> AuditState:
    context = _RUNS.get(run_id)
    if context is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return context.state
