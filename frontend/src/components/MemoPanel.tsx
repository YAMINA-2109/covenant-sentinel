import { useState } from "react";
import { askAuditor } from "../lib/api";
import { renderMarkdown } from "../lib/markdown";

function AskAuditor({ runId }: { runId: string }) {
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);

  async function submit() {
    const asked = question.trim();
    if (!asked || busy) return;
    setBusy(true);
    setQuestion("");
    try {
      const answer = await askAuditor(runId, asked);
      setThread((previous) => [...previous, { q: asked, a: answer }]);
    } catch (error) {
      setThread((previous) => [...previous, { q: asked, a: `Error: ${String(error)}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Ask the auditor
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Answers come only from this audit's record — verdicts, facts, causes and clauses.
      </p>
      <div className="slim-scroll mt-3 max-h-[22vh] space-y-3 overflow-y-auto pr-1">
        {thread.map((entry, index) => (
          <div key={index} className="text-[13px]">
            <div className="font-medium text-sky-300">Q: {entry.q}</div>
            <div className="mt-1 whitespace-pre-wrap leading-relaxed text-slate-300">
              {entry.a}
            </div>
          </div>
        ))}
        {busy && <div className="text-xs italic text-slate-500">consulting the audit record…</div>}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={question}
          onChange={(changeEvent) => setQuestion(changeEvent.target.value)}
          onKeyDown={(keyEvent) => keyEvent.key === "Enter" && submit()}
          placeholder='e.g. "Why did you clear the liquidity flag?"'
          className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-emerald-500 focus:outline-none"
        />
        <button
          onClick={submit}
          disabled={busy || !question.trim()}
          className="rounded-md bg-slate-700 px-4 py-2 text-sm font-medium text-slate-100 transition hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Ask
        </button>
      </div>
    </div>
  );
}

interface VerdictSummary {
  covenant: string;
  final_status: string;
  overturned: boolean;
  confidence_pct: number;
}

const STATUS_COLOR: Record<string, string> = {
  breach: "text-rose-300 border-rose-500/40 border-l-4 border-l-rose-500 bg-rose-500/5",
  at_risk: "text-amber-300 border-amber-500/40 border-l-4 border-l-amber-500 bg-amber-500/5",
  ok: "text-emerald-300 border-emerald-500/40 border-l-4 border-l-emerald-500 bg-emerald-500/5",
  data_missing: "text-slate-300 border-slate-500/40 border-l-4 border-l-slate-500 bg-slate-500/5",
};

export function MemoPanel({
  memoMarkdown,
  verdicts,
  overallConfidence,
  runId,
}: {
  memoMarkdown: string;
  verdicts: VerdictSummary[];
  overallConfidence: number | null;
  runId: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">Verdicts</h3>
          {overallConfidence != null && (
            <div className="text-right">
              <div className="text-2xl font-bold text-emerald-300">{Math.round(overallConfidence * 100)}%</div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">overall confidence</div>
            </div>
          )}
        </div>
        <div className="mt-3 space-y-2">
          {verdicts.map((verdict) => (
            <div
              key={verdict.covenant}
              className={`flex items-center justify-between rounded-lg border px-3 py-2 ${STATUS_COLOR[verdict.final_status] ?? STATUS_COLOR.data_missing}`}
            >
              <div>
                <div className="text-sm font-semibold text-slate-100">{verdict.covenant}</div>
                <div className="text-xs">
                  {verdict.final_status.replace("_", " ").toUpperCase()}
                  {verdict.overturned && verdict.final_status === "ok" && (
                    <span className="ml-2 text-emerald-400">· false positive eliminated by the Critic</span>
                  )}
                </div>
              </div>
              <div className="font-mono text-sm text-slate-300">{verdict.confidence_pct}%</div>
            </div>
          ))}
        </div>
      </div>

      {runId && <AskAuditor runId={runId} />}

      <div className="rounded-xl border border-emerald-500/30 bg-slate-900/60 p-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-emerald-300">
          Escalation memo
        </h3>
        <div className="slim-scroll max-h-[40vh] overflow-y-auto rounded-lg border border-slate-800/60 bg-slate-950/40 p-3 pr-2">
          <div
            className="memo-prose"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(memoMarkdown) }}
          />
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(memoMarkdown)}
          className="mt-4 rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
        >
          Copy memo (markdown)
        </button>
      </div>
    </div>
  );
}
