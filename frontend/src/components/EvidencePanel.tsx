import { useEffect } from "react";
import type { Citation, ParsedDoc } from "../lib/types";

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Render section text with the cited quote highlighted, tolerant to
 * whitespace differences between the quote and the source layout. */
function HighlightedText({ text, quote }: { text: string; quote: string }) {
  if (quote) {
    const pattern = quote.trim().split(/\s+/).map(escapeRegExp).join("\\s+");
    try {
      const match = new RegExp(pattern, "i").exec(text);
      if (match) {
        const start = match.index;
        const end = start + match[0].length;
        return (
          <>
            {text.slice(0, start)}
            <mark className="rounded bg-amber-400/25 px-0.5 py-0.5 font-medium text-amber-100">
              {text.slice(start, end)}
            </mark>
            {text.slice(end)}
          </>
        );
      }
    } catch {
      /* fall through to plain text */
    }
  }
  return <>{text}</>;
}

export interface EvidenceTarget {
  citation: Citation;
  documents: ParsedDoc[];
}

export function EvidencePanel({
  target,
  onClose,
}: {
  target: EvidenceTarget;
  onClose: () => void;
}) {
  const { citation, documents } = target;

  useEffect(() => {
    function onKey(keyEvent: KeyboardEvent) {
      if (keyEvent.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const doc = documents.find((candidate) => candidate.doc_id === citation.doc_id);
  const wanted = citation.section.toLowerCase();
  let section = doc?.sections.find((candidate) => {
    const title = candidate.title.toLowerCase();
    return title.includes(wanted) || wanted.includes(title);
  });
  if (!section && doc && citation.quote) {
    const needle = citation.quote.toLowerCase().split(/\s+/).slice(0, 6).join(" ");
    section = doc.sections.find((candidate) =>
      candidate.text.toLowerCase().replace(/\s+/g, " ").includes(needle),
    );
  }
  const quoteLocated =
    !!section && !!citation.quote &&
    new RegExp(citation.quote.trim().split(/\s+/).map(escapeRegExp).join("\\s+"), "i").test(section.text);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative flex h-full w-[32rem] max-w-[92vw] flex-col border-l border-slate-700 bg-slate-950 shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-widest text-emerald-400">
              Source evidence
            </div>
            <h3 className="mt-1 truncate text-sm font-semibold text-slate-100">
              {doc?.filename ?? citation.doc_id}
            </h3>
            <div className="mt-0.5 text-xs text-slate-400">
              {citation.section}
              {citation.page ? ` · p.${citation.page}` : ""}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close evidence panel"
            className="rounded-md border border-slate-700 px-2.5 py-1 text-sm text-slate-300 transition hover:bg-slate-800"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {section ? (
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-300">
              <HighlightedText text={section.text} quote={citation.quote} />
            </p>
          ) : (
            <div className="text-sm text-slate-400">
              Section not found in the parsed document.
              {citation.quote && (
                <blockquote className="mt-3 border-l-2 border-amber-500/60 pl-3 text-slate-300">
                  “{citation.quote}”
                </blockquote>
              )}
            </div>
          )}
        </div>

        <footer className="border-t border-slate-800 px-5 py-3 text-xs">
          {quoteLocated ? (
            <span className="text-emerald-300">
              ✓ Quote located verbatim in the source — the same mechanical check the Critic runs.
            </span>
          ) : (
            <span className="text-slate-500">
              Every citation is verified against the source documents by the Critic's mechanical
              citation check.
            </span>
          )}
        </footer>
      </aside>
    </div>
  );
}
