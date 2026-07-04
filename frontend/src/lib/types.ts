export type NodeName =
  | "system"
  | "planner"
  | "retriever"
  | "analyzer"
  | "critic"
  | "synthesizer";

export type EventType =
  | "run_started"
  | "doc_parsed"
  | "node_started"
  | "thought"
  | "retrieval_query"
  | "retrieval_hit"
  | "tool_call"
  | "tool_result"
  | "finding"
  | "need_more_retrieval"
  | "critic_check"
  | "verdict"
  | "memo"
  | "run_completed"
  | "run_failed";

export interface AgentEvent {
  run_id: string;
  seq: number;
  ts: number;
  node: NodeName;
  type: EventType;
  payload: Record<string, any>;
}

export interface Citation {
  doc_id: string;
  section: string;
  page: number | null;
  quote: string;
}

export interface DocSection {
  section_id: string;
  title: string;
  page: number | null;
  text: string;
}

export interface ParsedDoc {
  doc_id: string;
  filename: string;
  kind: string;
  sections: DocSection[];
}
