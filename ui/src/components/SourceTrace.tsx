import { useState } from "react";
import type { Receipt } from "../types";

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return null;
  const columns = Object.keys(rows[0]);
  return (
    <div className="rows-table-wrap">
      <table className="rows-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <td key={c}>{String(row[c] ?? "")}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="sql-block">
      <button
        className="copy-button"
        onClick={() => {
          navigator.clipboard?.writeText(sql);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
      {sql}
    </div>
  );
}

// The one signature UI element the spec calls for (§11A): the exact SQL
// that ran, the assumptions applied, and the rows behind the figure —
// everything a receipt carries, rendered so it can be reconciled by hand.
export function SourceTrace({ receipt }: { receipt: Receipt }) {
  return (
    <details className="source-trace">
      <summary>Source trace — {receipt.metric}</summary>

      <div className="trace-block">
        <div className="trace-label">Definition</div>
        <div className="trace-definition">{receipt.definition}</div>
      </div>

      <div className="trace-block">
        <div className="trace-label">Exact SQL executed</div>
        <SqlBlock sql={receipt.sql} />
      </div>

      {receipt.assumptions.length > 0 && (
        <div className="trace-block">
          <div className="trace-label">Assumptions</div>
          {receipt.assumptions.map((a, i) => (
            <div className="assumption-callout" key={i}>
              <span>⚠</span>
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}

      <div className="trace-block">
        <div className="trace-label">Rows</div>
        <RowsTable rows={receipt.rows} />
        <div className="row-count">{receipt.row_count}</div>
      </div>
    </details>
  );
}
