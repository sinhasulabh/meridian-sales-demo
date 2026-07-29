// Banner/branding + agent endpoint (spec §11A). Personalize this file (or
// override via the VITE_* build-time env vars below) per engagement —
// no other code change is needed to re-skin the client.

export const AGENT_URL: string = import.meta.env.VITE_AGENT_URL ?? "http://localhost:8080";

export const BRANDING = {
  clientName: "Meridian Systems",
  title: "Meridian Systems · Commercial Intelligence",
  contextLine: "Prepared for the Office of the CCO",
  tagline: "Every number sourced.",
};

// Stubbed roster for the login screen (spec §11B): identity is claimed,
// not authenticated, for this demo — see README for the honest cut and
// the promote-without-rewrite path to a real IdP.
export const LEADERSHIP_IDENTITY = { id: "LEADERSHIP", label: "Leadership · all access" };

export const REP_ROSTER: { id: string; label: string }[] = [
  { id: "REP-01", label: "Sarah Chen · REP-01" },
  { id: "REP-02", label: "Marcus Rivera · REP-02" },
  { id: "REP-03", label: "Priya Patel · REP-03" },
  { id: "REP-04", label: "James Okafor · REP-04" },
  { id: "REP-05", label: "Danielle Torres · REP-05" },
  { id: "REP-06", label: "Kevin Marsh · REP-06" },
  { id: "REP-07", label: "Aisha Williams · REP-07" },
  { id: "REP-08", label: "Tom Bradley · REP-08" },
  { id: "REP-09", label: "Lisa Park · REP-09" },
  { id: "REP-10", label: "Ryan Cole · REP-10" },
];

export const SUGGESTED_QUESTIONS: { label: string; question: string; dashed?: boolean }[] = [
  {
    label: "Enterprise attainment",
    question: "How is Enterprise tracking against quota this quarter?",
  },
  { label: "Reps at risk", question: "Which reps are at risk of missing quota?" },
  {
    label: "Open pipeline",
    question: "What's our open pipeline value closing before end of Q1?",
  },
  {
    label: "Why did we lose Ironbridge?",
    question: "Why did we lose the Ironbridge deal?",
    dashed: true,
  },
];
