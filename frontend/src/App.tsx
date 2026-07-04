import { useRef, useState } from "react";
import { startAudit, streamAudit } from "./lib/api";
import type { AgentEvent, NodeName } from "./lib/types";

const NODE_STYLE: Record<NodeName, string> = {
  system: "bg-slate-700 text-slate-200",
  planner: "bg-sky-800 text-sky-100",
  retriever: "bg-violet-800 text-violet-100",
  analyzer: "bg-amber-800 text-amber-100",
  critic: "bg-rose-800 text-rose-100",
  synthesizer: "bg-emerald-800 text-emerald-100",
};

export default function App() {
  const [files, setFiles] = useState<File[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const stopRef = useRef<(() => void) | null>(null);

  async function run() {
    if (files.length === 0 || running) return;
    setEvents([]);
    setRunning(true);
    try {
      const runId = await startAudit(files);
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

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">
          Covenant<span className="text-emerald-400">Sentinel</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Agentic covenant-compliance auditor — reads the credit agreement and the
          financials, computes, challenges itself, and writes a cited escalation memo.
        </p>
      </header>

      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <label className="block text-sm font-medium text-slate-300">
          Case documents (credit agreement, financial report, treasury pack)
        </label>
        <input
          type="file"
          multiple
          accept=".txt,.md,.pdf"
          className="mt-3 block w-full text-sm text-slate-400 file:mr-4 file:rounded-md file:border-0 file:bg-emerald-700 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-600"
          onChange={(changeEvent) =>
            setFiles(Array.from(changeEvent.target.files ?? []))
          }
        />
        <button
          onClick={run}
          disabled={files.length === 0 || running}
          className="mt-4 rounded-md bg-emerald-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {running ? "Auditing…" : "Run audit"}
        </button>
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
          Agent reasoning trace
        </h2>
        <ol className="space-y-2">
          {events.map((event) => (
            <li
              key={event.seq}
              className="flex items-start gap-3 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-2.5 text-sm"
            >
              <span
                className={`mt-0.5 rounded px-2 py-0.5 text-[11px] font-semibold uppercase ${NODE_STYLE[event.node]}`}
              >
                {event.node}
              </span>
              <div className="min-w-0">
                <span className="font-medium text-slate-200">{event.type}</span>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-xs text-slate-400">
                  {JSON.stringify(event.payload, null, 1)}
                </pre>
              </div>
            </li>
          ))}
          {events.length === 0 && (
            <li className="rounded-lg border border-dashed border-slate-800 px-4 py-6 text-center text-sm text-slate-500">
              Upload the case documents and run the audit — every step of the
              agent's reasoning will stream here live.
            </li>
          )}
        </ol>
      </section>
    </div>
  );
}
