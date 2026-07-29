import type { ChatMessage } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { SourceTrace } from "./SourceTrace";
import { Prose } from "../markdown";

export function ChatCard({ message }: { message: ChatMessage }) {
  return (
    <div className="fade-in">
      <div className="question-bubble">{message.question}</div>

      <div className="answer-card" style={{ marginTop: 8 }}>
        {message.status === "pending" && (
          <span className="computing">
            <span className="dot-flicker" />
            Computing — calling governed tools…
          </span>
        )}

        {message.status === "error" && (
          <div className="answer-error">
            {message.error ?? "The agent service is unavailable. No figure is shown — a guess would violate the trust guarantee."}
          </div>
        )}

        {message.status === "done" && (
          <>
            <div className="answer-card-header">
              {message.stamp && <ConfidenceBadge stamp={message.stamp} />}
            </div>
            <div className="answer-text">
              <Prose text={message.answer ?? ""} />
            </div>
            {message.receipts?.map((r, i) => <SourceTrace receipt={r} key={i} />)}
          </>
        )}
      </div>
    </div>
  );
}
