export type Stamp = "verified" | "assumption" | "cannot_verify";

export interface Receipt {
  metric: string;
  definition: string;
  sql: string;
  assumptions: string[];
  rows: Record<string, unknown>[];
  row_count: string;
}

export interface RunResponse {
  answer: string;
  stamp: Stamp;
  receipts: Receipt[];
  session_id: string;
}

export interface ChatMessage {
  id: string;
  question: string;
  status: "pending" | "done" | "error";
  answer?: string;
  stamp?: Stamp;
  receipts?: Receipt[];
  error?: string;
}

export interface Viewer {
  id: string;
  label: string;
}
