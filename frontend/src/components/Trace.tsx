import type { AgentEvent, NodeName } from "../lib/types";

const NODE_BADGE: Record<NodeName, string> = {
  system: "bg-slate-700/80 text-slate-200",
  planner: "bg-sky-900 text-sky-200",
  retriever: "bg-violet-900 text-violet-200",
  analyzer: "bg-amber-900 text-amber-200",
  critic: "bg-rose-900 text-rose-200",
  synthesizer: "bg-emerald-900 text-emerald-200",
};

const STATUS_PILL: Record<string, string> = {
  breach: "bg-rose-500/15 text-rose-300 border-rose-500/40",
  at_risk: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  ok: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  conflict: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  data_missing: "bg-slate-500/15 text-slate-300 border-slate-500/40",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide ${STATUS_PILL[status] ?? STATUS_PILL.data_missing}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

function NodeBadge({ node }: { node: NodeName }) {
  return (
    <span
      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${NODE_BADGE[node]}`}
    >
      {node}
    </span>
  );
}

function Row({ event, children }: { event: AgentEvent; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 px-3 py-1.5">
      <NodeBadge node={event.node} />
      <div className="min-w-0 flex-1 text-[13px] leading-relaxed">{children}</div>
    </div>
  );
}

export function TraceEventRow({ event }: { event: AgentEvent }) {
  const p = event.payload as Record<string, any>;
  switch (event.type) {
    case "run_started":
      return (
        <Row event={event}>
          <span className="text-slate-300">
            Case opened —{" "}
            {(p.documents ?? [])
              .map((d: any) => `${d.filename} (${String(d.kind).replace("_", " ")}, ${d.sections} sections)`)
              .join(" · ")}
          </span>
        </Row>
      );
    case "doc_parsed":
      return (
        <Row event={event}>
          <span className="text-slate-400">
            Parsed <span className="text-slate-200">{p.filename}</span> →{" "}
            {(p.sections ?? []).length} locatable sections
          </span>
        </Row>
      );
    case "node_started":
      return (
        <div className="mt-3 mb-1 flex items-center gap-2 px-3">
          <NodeBadge node={event.node} />
          <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">
            {event.node === "retriever" && p.round ? `retrieval round ${p.round} — ${p.engine ?? ""}` : p.task ?? "working"}
          </span>
          <div className="h-px flex-1 bg-slate-800" />
        </div>
      );
    case "thought":
      if (p.cause_coverage !== undefined && p.cause_coverage !== null)
        return (
          <Row event={event}>
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
              <span className="font-semibold text-amber-200">Root cause traced ({p.covenant}):</span>{" "}
              <span className="text-slate-300">
                EUR {p.explained_eur_m}m explained, EUR {p.unexplained_eur_m}m unexplained →
                cause coverage <b>{Math.round(p.cause_coverage * 100)}%</b>
              </span>
            </div>
          </Row>
        );
      return (
        <Row event={event}>
          <span className="italic text-slate-400">
            {p.note ?? (p.plan ? `Plan: ${(p.plan as string[]).join(" → ")}` : JSON.stringify(p))}
          </span>
          {p.covenants && (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(p.covenants as string[]).map((c) => (
                <span key={c} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                  {c}
                </span>
              ))}
            </div>
          )}
        </Row>
      );
    case "retrieval_query":
      return (
        <Row event={event}>
          <span className="text-slate-300">
            🔎 <span className="text-slate-100">“{p.query}”</span>
          </span>
          {p.doc_kind && (
            <span className="ml-2 rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400">
              {String(p.doc_kind).replace("_", " ")}
            </span>
          )}
          {p.reason && (
            <span className="ml-1 rounded bg-slate-800/60 px-1.5 py-0.5 text-[11px] text-slate-500">
              {p.reason}
            </span>
          )}
        </Row>
      );
    case "retrieval_hit":
      return (
        <Row event={event}>
          <span className="text-xs text-slate-500">
            ↳ <span className="text-slate-400">{p.section}</span>
            {p.page ? `, p.${p.page}` : ""} <span className="text-slate-600">(score {p.score})</span>
          </span>
        </Row>
      );
    case "tool_call":
      return (
        <Row event={event}>
          <span className="font-mono text-xs text-slate-400">
            ⚙ {p.tool}(
            {Object.entries(p)
              .filter(([key]) => key !== "tool")
              .map(([key, value]) => `${key}=${Array.isArray(value) ? (value as any[]).join(", ") : value}`)
              .join(", ")}
            )
          </span>
        </Row>
      );
    case "tool_result":
      return (
        <Row event={event}>
          <span className="font-mono text-xs text-emerald-300/90">= {p.formula ?? p.detail}</span>
        </Row>
      );
    case "finding":
      return (
        <Row event={event}>
          <div className="rounded-lg border border-slate-700 bg-slate-900/80 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={p.status} />
              <span className="font-semibold text-slate-100">{p.covenant}</span>
              <span className="font-mono text-xs text-slate-300">
                required {p.required} · actual <b>{p.actual}</b> · headroom {p.headroom}
              </span>
            </div>
            {p.projection && <div className="mt-1 text-xs text-amber-300/90">📈 {p.projection}</div>}
            {p.citations?.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {(p.citations as string[]).map((citation, index) => (
                  <span key={index} className="rounded border border-slate-700 bg-slate-800/80 px-1.5 py-0.5 text-[11px] text-sky-300">
                    § {citation}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Row>
      );
    case "need_more_retrieval":
      return (
        <Row event={event}>
          <div className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-2">
            <span className="font-semibold text-sky-200">↻ Agent decided it needs more evidence</span>
            <span className="text-slate-300"> — {p.why ?? ""}</span>
            {p.covenant && <span className="text-slate-400"> ({p.covenant})</span>}
          </div>
        </Row>
      );
    case "critic_check":
      return (
        <Row event={event}>
          <span className={`font-mono text-xs ${p.passed ? "text-emerald-300" : "text-rose-300"}`}>
            {p.passed ? "✓" : "✗"} {p.check}
          </span>
          <span className="ml-2 text-xs text-slate-400">
            {p.covenant ? `[${p.covenant}] ` : ""}
            {p.note}
          </span>
        </Row>
      );
    case "verdict": {
      const cleared = p.overturned && p.final_status === "ok";
      return (
        <Row event={event}>
          <div
            className={`rounded-lg border px-3 py-2 ${
              cleared ? "border-emerald-500/50 bg-emerald-500/10" : "border-slate-700 bg-slate-900/80"
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-100">{p.covenant}</span>
              {p.overturned ? (
                <>
                  <span className="line-through decoration-rose-400/70">
                    <StatusPill status={p.original_status} />
                  </span>
                  <span className="text-slate-500">→</span>
                  <StatusPill status={p.final_status} />
                  {cleared && (
                    <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] font-bold uppercase text-emerald-300">
                      false positive eliminated
                    </span>
                  )}
                </>
              ) : (
                <>
                  <StatusPill status={p.final_status} />
                  <span className="text-[11px] uppercase tracking-wide text-slate-500">confirmed</span>
                </>
              )}
              <span className="ml-auto font-mono text-xs text-slate-300">
                confidence {Math.round((p.confidence ?? 0) * 100)}%
              </span>
            </div>
            {p.rationale && <div className="mt-1 text-xs text-slate-400">{p.rationale}</div>}
          </div>
        </Row>
      );
    }
    case "memo":
      return (
        <Row event={event}>
          <span className="font-semibold text-emerald-300">📝 Escalation memo drafted → see the panel on the right</span>
        </Row>
      );
    case "run_completed":
      return (
        <Row event={event}>
          <span className="font-semibold text-emerald-300">
            ✅ Audit complete — {p.retrieval_rounds} retrieval rounds
            {p.overall_confidence != null && <> · overall confidence {Math.round(p.overall_confidence * 100)}%</>}
          </span>
        </Row>
      );
    case "run_failed":
      return (
        <Row event={event}>
          <span className="font-semibold text-rose-300">✗ Run failed: {p.error}</span>
        </Row>
      );
    default:
      return (
        <Row event={event}>
          <span className="text-xs text-slate-500">{JSON.stringify(p).slice(0, 160)}</span>
        </Row>
      );
  }
}
