import { BRANDING } from "../../config";

export function Banner() {
  return (
    <header className="banner">
      <div className="banner-identity">
        <span className="banner-client">{BRANDING.clientName}</span>
        <span className="banner-title">{BRANDING.title}</span>
        <span className="banner-context">{BRANDING.contextLine}</span>
      </div>
      <span className="banner-tagline">{BRANDING.tagline}</span>
    </header>
  );
}
