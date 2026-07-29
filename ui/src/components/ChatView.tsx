import { useRef, useState } from "react";
import { Banner } from "./Banner";
import { ChatCard } from "./ChatCard";
import { SUGGESTED_QUESTIONS } from "../../config";
import { askAgent } from "../api";
import type { ChatMessage, Viewer } from "../types";

interface Props {
  viewer: Viewer;
  onSwitchUser: () => void;
}

export function ChatView({ viewer, onSwitchUser }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const sessionId = useRef<string | null>(null);
  const busy = messages.some((m) => m.status === "pending");

  async function send(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    const id = crypto.randomUUID();
    setMessages((prev) => [...prev, { id, question: trimmed, status: "pending" }]);
    setInput("");

    try {
      const result = await askAgent(trimmed, viewer.id, sessionId.current);
      sessionId.current = result.session_id;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id
            ? { ...m, status: "done", answer: result.answer, stamp: result.stamp, receipts: result.receipts }
            : m
        )
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === id
            ? {
                ...m,
                status: "error",
                error: "The pipeline data service is unavailable right now.",
              }
            : m
        )
      );
    }
  }

  return (
    <div className="app-shell">
      <Banner />
      <div className="viewer-bar">
        <span className="viewer-chip">
          <span className="viewer-dot" />
          Viewing as: <strong>{viewer.label}</strong>
        </span>
        <button className="link-button" onClick={onSwitchUser}>
          Switch user / Sign out
        </button>
      </div>

      <div className="chat-scroll">
        {messages.length === 0 && (
          <div className="empty-state">
            Ask about segment attainment, at-risk reps, open pipeline, or a deal's loss reason.
          </div>
        )}
        {messages.map((m) => (
          <ChatCard message={m} key={m.id} />
        ))}
      </div>

      <div className="chips-row">
        {SUGGESTED_QUESTIONS.map((q) => (
          <button
            key={q.label}
            className={`chip${q.dashed ? " dashed" : ""}`}
            onClick={() => send(q.question)}
            disabled={busy}
          >
            {q.label}
          </button>
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <div className="composer-inner">
          <input
            className="composer-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about Q1 2026 pipeline…"
            disabled={busy}
          />
          <button className="send-button" type="submit" disabled={busy || !input.trim()}>
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}
