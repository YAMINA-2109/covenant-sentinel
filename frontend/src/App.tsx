import { useEffect, useRef, useState } from "react";
import { getAuditDocuments, startAudit, startDemoAudit, streamAudit } from "./lib/api";
import type { AgentEvent, Citation, NodeName, ParsedDoc } from "./lib/types";
import { TraceEventRow } from "./components/Trace";
import { MemoPanel } from "./components/MemoPanel";
import { EvidencePanel, type EvidenceTarget } from "./components/EvidencePanel";

const PHASES: { node: NodeName; label: string }[] = [
  { node: "planner", label: "Plan" },
  { node: "retriever", label: "Retrieve" },
  { node: "analyzer", label: "Analyze" },
  { node: "critic", label: "Verify" },
  { node: "synthesizer", label: "Report" },
];

function PhaseStepper({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const started = events.filter((event) => event.type === "node_started");
  const seen = new Set(started.map((event) => event.node));
  const current = running && started.length > 0 ? started[started.length - 1].node : null;
  if (events.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5">
      {PHASES.map((phase, index) => {
        const isCurrent = phase.node === current;
        const isDone = seen.has(phase.node) && !isCurrent;
        return (
          <span key={phase.node} className="flex items-center gap-1.5">
            {index > 0 && <span className="h-px w-3 bg-slate-700" />}
            <span
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                isCurrent
                  ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
                  : isDone
                    ? "border-slate-700 bg-slate-800/60 text-slate-300"
                    : "border-slate-800 text-slate-600"
              }`}
            >
              {isCurrent && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />}
              {isDone && <span className="text-emerald-400">✓</span>}
              {phase.label}
            </span>
          </span>
        );
      })}
    </div>
  );
}

export default function App() {
  const [files, setFiles] = useState<File[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const stopRef = useRef<(() => void) | null>(null);
  const traceRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const runIdRef = useRef<string | null>(null);
  const docsCacheRef = useRef<{ runId: string; docs: ParsedDoc[] } | null>(null);
  const [evidence, setEvidence] = useState<EvidenceTarget | null>(null);

  async function openCitation(citation: Citation) {
    const runId = runIdRef.current;
    if (!runId) return;
    let docs =
      docsCacheRef.current?.runId === runId ? docsCacheRef.current.docs : null;
    if (!docs) {
      try {
        docs = await getAuditDocuments(runId);
        docsCacheRef.current = { runId, docs };
      } catch {
        docs = [];
      }
    }
    setEvidence({ citation, documents: docs });
  }

  useEffect(() => {
    if (!running) return;
    const startedAt = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);

  useEffect(() => {
    const container = traceRef.current;
    if (container && stickToBottomRef.current) {
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }, [events.length]);

  function handleTraceScroll() {
    const container = traceRef.current;
    if (!container) return;
    stickToBottomRef.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < 140;
  }

  async function launch(start: () => Promise<string>) {
    if (running) return;
    setEvents([]);
    setElapsed(0);
    setEvidence(null);
    docsCacheRef.current = null;
    stickToBottomRef.current = true;
    setRunning(true);
    try {
      const runId = await start();
      runIdRef.current = runId;
      stopRef.current = streamAudit(
        runId,
        (event) => setEvents((previous) => [...previous, event]),
        () => setRunning(false),
      );
    } catch (error) {
      setRunning(false);
      setEvents([
        {
          run_id: "-",
          seq: 0,
          ts: Date.now() / 1000,
          node: "system",
          type: "run_failed",
          payload: { error: String(error) },
        },
      ]);
    }
  }

  const memoEvent = events.find((event) => event.type === "memo");
  const completed = events.find((event) => event.type === "run_completed");
  const memoPayload = memoEvent?.payload as
    | { markdown: string; overall_confidence: number | null; verdicts: any[] }
    | undefined;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Covenant<span className="text-emerald-400">Sentinel</span>
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            An agentic covenant-compliance auditor: it reads the credit agreement and the
            borrower's financials, computes with deterministic tools, challenges its own findings,
            and writes a cited escalation memo.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-xs font-semibold text-sky-300">
            ⚡ Powered by Vultr Serverless Inference
          </span>
          <div className="text-right text-[11px] text-slate-500">
            Qwen3.5-397B · VultronRetrieverPrime hybrid retrieval · LangGraph
          </div>
        </div>
      </header>

      <section className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <button
          onClick={() => launch(startDemoAudit)}
          disabled={running}
          className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {running ? `Auditing… ${elapsed}s` : "▶ Run the ACME demo case"}
        </button>
        <span className="text-xs text-slate-500">or audit your own case:</span>
        <input
          type="file"
          multiple
          accept=".txt,.md,.pdf"
          className="block text-sm text-slate-400 file:mr-3 file:rounded-md file:border-0 file:bg-slate-700 file:px-3 file:py-2 file:text-xs file:font-medium file:text-white hover:file:bg-slate-600"
          onChange={(changeEvent) => setFiles(Array.from(changeEvent.target.files ?? []))}
        />
        <button
          onClick={() => launch(() => startAudit(files))}
          disabled={files.length === 0 || running}
          className="rounded-md border border-slate-600 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Run audit
        </button>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_26rem]">
        <section className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
              Agent reasoning — live
              {running && (
                <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-300">
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                  LIVE · {elapsed}s
                </span>
              )}
            </h2>
            <PhaseStepper events={events} running={running} />
          </div>
          <div
            ref={traceRef}
            onScroll={handleTraceScroll}
            className="max-h-[75vh] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/60 py-2"
          >
            {events.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-slate-500">
                Run the ACME demo case (credit agreement + Q2 report + treasury pack) and watch
                the agent plan, retrieve, compute, challenge itself, and write the memo.
              </div>
            ) : (
              events.map((event) => (
                <TraceEventRow key={event.seq} event={event} onCitation={openCitation} />
              ))
            )}
          </div>
        </section>

        <section className="min-w-0">
          {memoPayload ? (
            <MemoPanel
              memoMarkdown={memoPayload.markdown}
              verdicts={memoPayload.verdicts ?? []}
              overallConfidence={memoPayload.overall_confidence ?? null}
            />
          ) : (
            <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-600">
              The verified verdicts and the cited escalation memo will appear here
              {running ? "…" : "."}
              {completed && !memoPayload && " (run finished without a memo)"}
            </div>
          )}
        </section>
      </div>

      {evidence && <EvidencePanel target={evidence} onClose={() => setEvidence(null)} />}
    </div>
  );
}
