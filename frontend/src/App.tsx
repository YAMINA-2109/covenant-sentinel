import { useEffect, useRef, useState } from "react";
import { startAudit, startDemoAudit, streamAudit } from "./lib/api";
import type { AgentEvent } from "./lib/types";
import { TraceEventRow } from "./components/Trace";
import { MemoPanel } from "./components/MemoPanel";

export default function App() {
  const [files, setFiles] = useState<File[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const stopRef = useRef<(() => void) | null>(null);
  const traceEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!running) return;
    const startedAt = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [running]);

  useEffect(() => {
    traceEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  async function launch(start: () => Promise<string>) {
    if (running) return;
    setEvents([]);
    setElapsed(0);
    setRunning(true);
    try {
      const runId = await start();
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
        <div className="text-right text-xs text-slate-500">
          <div>Vultr Serverless Inference · Qwen3.5-397B</div>
          <div>VultronRetrieverPrime hybrid retrieval · LangGraph</div>
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
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Agent reasoning — live
            {running && (
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            )}
          </h2>
          <div className="max-h-[75vh] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/60 py-2">
            {events.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-slate-500">
                Run the ACME demo case (credit agreement + Q2 report + treasury pack) and watch
                the agent plan, retrieve, compute, challenge itself, and write the memo.
              </div>
            ) : (
              events.map((event) => <TraceEventRow key={event.seq} event={event} />)
            )}
            <div ref={traceEndRef} />
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
    </div>
  );
}
