import { Banner } from "./Banner";
import { LEADERSHIP_IDENTITY, REP_ROSTER } from "../../config";
import type { Viewer } from "../types";

interface Props {
  onLogin: (viewer: Viewer) => void;
}

// The app opens here, not the chat (spec §11A) — no password, identity is
// a stubbed claim (§11B). Real access control is enforced downstream in
// the governed tier regardless of what this screen lets someone click.
export function Login({ onLogin }: Props) {
  return (
    <div className="app-shell">
      <Banner />
      <div className="centered-shell">
        <div className="login-card fade-in">
          <div className="login-heading">Who's asking?</div>
          <div className="login-sub">
            Pick an identity to continue. No password — this is a stubbed claim for the demo;
            see the README for the honest cut.
          </div>

          <div className="identity-group-label">Unrestricted</div>
          <div className="identity-list">
            <button
              className="identity-option leadership"
              onClick={() => onLogin(LEADERSHIP_IDENTITY)}
            >
              {LEADERSHIP_IDENTITY.label}
            </button>
          </div>

          <div className="identity-group-label">Scoped to one rep's own deals</div>
          <div className="identity-list">
            {REP_ROSTER.map((rep) => (
              <button key={rep.id} className="identity-option" onClick={() => onLogin(rep)}>
                {rep.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
