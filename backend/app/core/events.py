"""Event contract between the agent pipeline and the UI.

Every meaningful step the agent takes is published as an AgentEvent on a
per-run bus. The API layer streams these over SSE; the frontend renders them
as a live reasoning trace. Events are kept in history so a client that
connects late (or reconnects) replays the full trace — this also gives us a
recorded real trace as a backup for the demo video.
"""

import asyncio
import time
from enum import Enum

from pydantic import BaseModel, Field


class Node(str, Enum):
    SYSTEM = "system"
    PLANNER = "planner"
    RETRIEVER = "retriever"
    ANALYZER = "analyzer"
    CRITIC = "critic"
    SYNTHESIZER = "synthesizer"


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    DOC_PARSED = "doc_parsed"
    NODE_STARTED = "node_started"
    THOUGHT = "thought"
    RETRIEVAL_QUERY = "retrieval_query"
    RETRIEVAL_HIT = "retrieval_hit"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINDING = "finding"
    NEED_MORE_RETRIEVAL = "need_more_retrieval"
    CRITIC_CHECK = "critic_check"
    VERDICT = "verdict"
    MEMO = "memo"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class AgentEvent(BaseModel):
    run_id: str
    seq: int
    ts: float = Field(default_factory=time.time)
    node: Node
    type: EventType
    payload: dict = Field(default_factory=dict)


class RunBus:
    """Single-run event history + fan-out to any number of SSE subscribers."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.history: list[AgentEvent] = []
        self.done = False
        self._subscribers: list[asyncio.Queue] = []
        self._seq = 0

    def publish(self, node: Node, type_: EventType, payload: dict | None = None) -> AgentEvent:
        event = AgentEvent(
            run_id=self.run_id, seq=self._seq, node=node, type=type_, payload=payload or {}
        )
        self._seq += 1
        self.history.append(event)
        if type_ in (EventType.RUN_COMPLETED, EventType.RUN_FAILED):
            self.done = True
        for queue in list(self._subscribers):
            queue.put_nowait(event)
            if self.done:
                queue.put_nowait(None)
        return event

    async def subscribe(self):
        """Yield the full history, then live events until the run finishes."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        last_seq = -1
        try:
            for event in list(self.history):
                yield event
                last_seq = event.seq
            if self.done:
                return
            while True:
                event = await queue.get()
                if event is None:
                    return
                if event.seq <= last_seq:
                    continue
                yield event
                last_seq = event.seq
        finally:
            self._subscribers.remove(queue)
