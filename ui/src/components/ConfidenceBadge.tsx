import type { Stamp } from "../types";

const LABELS: Record<Stamp, string> = {
  verified: "Verified",
  assumption: "Assumption",
  cannot_verify: "Cannot verify",
};

export function ConfidenceBadge({ stamp }: { stamp: Stamp }) {
  return <span className={`badge badge-${stamp}`}>{LABELS[stamp]}</span>;
}
