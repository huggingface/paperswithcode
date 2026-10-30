import { cn } from "@/lib/utils";
import type { PendingEditOf, UrlItem } from "@/lib/pendingEdits";
import { DiffColumn, EmptyInline, ExternalLink } from "./shared";

export function ResourceDiff({ label, currentItems, proposedItems }: {
  label: string;
  currentItems: UrlItem[];
  proposedItems: UrlItem[];
}) {
  const currentByUrl = new Map(currentItems.map((item) => [item.url, item]));
  const proposedByUrl = new Map(proposedItems.map((item) => [item.url, item]));
  const urls = Array.from(new Set([...currentByUrl.keys(), ...proposedByUrl.keys()])).sort();

  if (urls.length === 0) {
    return <EmptyInline>No {label} in this submission.</EmptyInline>;
  }

  return (
    <div className="submission-url-list">
      {urls.map((url) => {
        const current = currentByUrl.get(url);
        const proposed = proposedByUrl.get(url);
        const added = !current && proposed;
        const removed = current && !proposed;
        const officialChanged =
          current && proposed && current.is_official !== proposed.is_official;

        return (
          <div
            key={url}
            className={cn(
              "submission-url-row",
              added && "added",
              removed && "removed",
              officialChanged && "changed",
            )}
          >
            <div className="submission-url-content">
              <ExternalLink url={url} className={cn(removed && "removed")} />
              {added && <span className="submission-pill status approved">Added</span>}
              {removed && <span className="submission-pill status rejected">Removed</span>}
              {officialChanged && (
                <span className="submission-pill changed">
                  Official: {String(current.is_official)} {"->"} {String(proposed.is_official)}
                </span>
              )}
              {(proposed ?? current)?.is_official && <span className="submission-pill">Official</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const unofficial = (url: string): UrlItem => ({ url, is_official: false });

export function HfArtifactsDiff({ edit }: { edit: PendingEditOf<"hf_artifacts"> }) {
  const sections = [
    { key: "hf_models", label: "Models" },
    { key: "hf_datasets", label: "Datasets" },
    { key: "hf_spaces", label: "Spaces" },
  ] as const;

  return (
    <div className="submission-hf-artifacts-diff">
      {sections.map(({ key, label }) => (
        <div key={key} className="submission-hf-artifacts-section">
          <div className="submission-diff-label">{label}</div>
          <ResourceDiff
            label={label.toLowerCase()}
            currentItems={(edit.current_payload?.[key] ?? []).map(unofficial)}
            proposedItems={edit.proposed_payload[key].map(unofficial)}
          />
        </div>
      ))}
    </div>
  );
}

export function XThreadsDiff({ edit }: { edit: PendingEditOf<"x_threads"> }) {
  return (
    <ResourceDiff
      label="X threads"
      currentItems={(edit.current_payload?.x_threads ?? []).map(({ url }) => unofficial(url))}
      proposedItems={edit.proposed_payload.x_threads.map(unofficial)}
    />
  );
}

export function SourceUrlDiff({ edit }: { edit: PendingEditOf<"source_url"> }) {
  return (
    <div className="submission-diff-columns">
      <DiffColumn title="Current source URL">
        <ExternalLink url={edit.current_payload?.source_url} empty="No current URL" />
      </DiffColumn>
      <DiffColumn title="Proposed source URL">
        <ExternalLink url={edit.proposed_payload.source_url} empty="No proposed URL" />
      </DiffColumn>
    </div>
  );
}
