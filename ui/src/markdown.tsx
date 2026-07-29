import type { ReactNode } from "react";

// The agent's system prompt asks for plain prose, but nothing guarantees an
// LLM never reaches for **bold** or a bullet list — so the UI renders the
// common lightweight cases instead of showing literal asterisks. This is
// intentionally not a full markdown parser: no tables, no headings, no
// nested lists. If the model restates a receipt as a table, that's a prompt
// problem to fix, not something this renderer should make look tidy.

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

export function Prose({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\s*\n/);

  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
        const isList = lines.length > 0 && lines.every((l) => /^[-*]\s+/.test(l));

        if (isList) {
          return (
            <ul className="answer-list" key={i}>
              {lines.map((line, j) => (
                <li key={j}>{renderInline(line.replace(/^[-*]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }

        return <p key={i}>{renderInline(lines.join(" "))}</p>;
      })}
    </>
  );
}
