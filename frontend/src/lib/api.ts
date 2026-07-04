import type { AgentEvent, ParsedDoc } from "./types";

export async function getAuditDocuments(runId: string): Promise<ParsedDoc[]> {
  const response = await fetch(`/api/audits/${runId}`);
  if (!response.ok) throw new Error(`audit fetch failed: ${response.status}`);
  const state = (await response.json()) as { documents: ParsedDoc[] };
  return state.documents ?? [];
}

export async function startAudit(files: File[]): Promise<string> {
  const body = new FormData();
  for (const file of files) body.append("files", file);
  const response = await fetch("/api/audits", { method: "POST", body });
  if (!response.ok) throw new Error(`audit start failed: ${response.status}`);
  const json = (await response.json()) as { run_id: string };
  return json.run_id;
}

export async function startDemoAudit(): Promise<string> {
  const response = await fetch("/api/audits/demo", { method: "POST" });
  if (!response.ok) throw new Error(`demo start failed: ${response.status}`);
  const json = (await response.json()) as { run_id: string };
  return json.run_id;
}

export async function askAuditor(runId: string, question: string): Promise<string> {
  const response = await fetch(`/api/audits/${runId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) throw new Error(`ask failed: ${response.status}`);
  const json = (await response.json()) as { answer: string };
  return json.answer;
}

export function streamAudit(
  runId: string,
  onEvent: (event: AgentEvent) => void,
  onDone: () => void,
): () => void {
  const source = new EventSource(`/api/audits/${runId}/events`);
  source.onmessage = (message) => {
    const event = JSON.parse(message.data) as AgentEvent;
    onEvent(event);
    if (event.type === "run_completed" || event.type === "run_failed") {
      source.close();
      onDone();
    }
  };
  source.onerror = () => {
    source.close();
    onDone();
  };
  return () => source.close();
}
