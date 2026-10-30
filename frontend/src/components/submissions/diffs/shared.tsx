import React from "react";

import { cn } from "@/lib/utils";
import { safeExternalHref } from "@/lib/safeExternalHref";

export function DiffColumn({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="submission-diff-column">
      <div className="submission-diff-label">{title}</div>
      <div className="submission-diff-pills">{children}</div>
    </div>
  );
}

export function EmptyInline({ children }: { children: React.ReactNode }) {
  return <span className="submission-muted">{children}</span>;
}

/** An external link, or `empty` copy when there is no URL. */
export function ExternalLink({ url, empty, className }: {
  url?: string | null;
  empty?: string;
  className?: string;
}) {
  if (!url) return empty ? <EmptyInline>{empty}</EmptyInline> : null;
  return (
    <a
      className={cn("submission-url-link", className)}
      href={safeExternalHref(url) ?? undefined}
      target="_blank"
      rel="noopener noreferrer"
    >
      {url}
    </a>
  );
}

export function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="submission-diff-label">{label}</div>
      <div className="submission-field-value">{value ?? <span className="submission-muted">Not set</span>}</div>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="submission-json-block">
      <div className="submission-diff-label">{title}</div>
      <pre>
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

export function RawJsonToggle({ currentPayload, proposedPayload }: {
  currentPayload?: object | null;
  proposedPayload: object;
}) {
  const [showRaw, setShowRaw] = React.useState(false);
  return (
    <div className="submission-raw-toggle">
      <button
        type="button"
        className="raw-json-btn"
        onClick={() => setShowRaw((value) => !value)}
      >
        {showRaw ? "Hide raw JSON" : "Show raw JSON"}
      </button>
      {showRaw && (
        <div className="submission-json-grid">
          <JsonBlock title="Current payload" value={currentPayload ?? {}} />
          <JsonBlock title="Proposed payload" value={proposedPayload} />
        </div>
      )}
    </div>
  );
}
