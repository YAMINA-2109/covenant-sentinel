import { renderMarkdown } from "../lib/markdown";

interface VerdictSummary {
  covenant: string;
  final_status: string;
  overturned: boolean;
  confidence_pct: number;
}

const STATUS_COLOR: Record<string, string> = {
  breach: "text-rose-300 border-rose-500/40",
  at_risk: "text-amber-300 border-amber-500/40",
  ok: "text-emerald-300 border-emerald-500/40",
  data_missing: "text-slate-300 border-slate-500/40",
};

export function MemoPanel({
  memoMarkdown,
  verdicts,
  overallConfidence,
}: {
  memoMarkdown: string;
  verdicts: VerdictSummary[];
  overallConfidence: number | null;
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
              className={`flex items-center justify-between rounded-lg border bg-slate-950/60 px-3 py-2 ${STATUS_COLOR[verdict.final_status] ?? STATUS_COLOR.data_missing}`}
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

      <div className="rounded-xl border border-emerald-500/30 bg-slate-900/60 p-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-emerald-300">
          Escalation memo
        </h3>
        <div
          className="memo-prose"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(memoMarkdown) }}
        />
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
