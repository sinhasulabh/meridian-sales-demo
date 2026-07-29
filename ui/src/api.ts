import { AGENT_URL } from "../config";
import type { RunResponse } from "./types";

// The UI never holds the Anthropic key and never talks to the MCP server
// directly (spec §11A) — this is the only network call it makes.
export async function askAgent(
  question: string,
  viewer: string,
  sessionId: string | null
): Promise<RunResponse> {
  const res = await fetch(`${AGENT_URL}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, viewer, session_id: sessionId ?? undefined }),
  });
  if (!res.ok) {
    throw new Error(`Agent service returned ${res.status}`);
  }
  return res.json();
}
