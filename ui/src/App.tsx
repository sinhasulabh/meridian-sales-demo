import { useState } from "react";
import { Login } from "./components/Login";
import { ChatView } from "./components/ChatView";
import type { Viewer } from "./types";

export default function App() {
  const [viewer, setViewer] = useState<Viewer | null>(null);

  if (!viewer) {
    return <Login onLogin={setViewer} />;
  }

  return <ChatView viewer={viewer} onSwitchUser={() => setViewer(null)} />;
}
