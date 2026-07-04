"""HTTP surface: start an audit, stream its reasoning trace, fetch final state."""

import asyncio
import uuid

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

        from app.agent.graph import run_audit  # imported lazily: lands in next commits

        await run_audit(state, bus)
    except ModuleNotFoundError:
        bus.publish(
            Node.SYSTEM,
            EventType.RUN_COMPLETED,
            {"note": "Ingestion online — agent graph lands in the next commits."},
        )
    except Exception as exc:  # surface real failures to the UI, never hang the stream
        bus.publish(Node.SYSTEM, EventType.RUN_FAILED, {"error": str(exc)})


@router.post("/audits")
async def create_audit(files: list[UploadFile]) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="upload at least one document")
    run_id = uuid.uuid4().hex[:12]
    state = AuditState(run_id=run_id)
    for index, upload in enumerate(files):
        data = await upload.read()
        doc = parse_upload(f"doc{index}", upload.filename or f"doc{index}.txt", data)
        state.documents.append(doc)

    context = RunContext(state, RunBus(run_id))
    _RUNS[run_id] = context
    context.task = asyncio.create_task(run_pipeline(context))
    return {"run_id": run_id}


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
