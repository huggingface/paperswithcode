import { useEffect, useState } from "react";

export function CompactionStatus() {
  const [extended, setExtended] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setExtended(true), 15_000);
    return () => window.clearTimeout(timer);
  }, []);
  return <div className="chat-waiting chat-compaction-status" role="status" aria-live="polite">
    <span className="chat-thinking">Summarizing earlier context…</span>
    {extended && <span className="chat-compaction-explanation">This conversation is long. Preserving its details may take up to a minute.</span>}
  </div>;
}
