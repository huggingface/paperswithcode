/* eslint-disable react-refresh/only-export-components */
import React from "react";
import { skipToken, useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, FileCode2, X } from "lucide-react";

import { chatApi } from "@/lib/api/chat";
import { chatArtifactUrls } from "@/lib/chatArtifactUrls";
import type { ArtifactBlock } from "@/lib/chat";
import { chatArtifactKeys } from "@/lib/chatSessionQueries";
import { LatexPaperPanel } from "./LatexPaperPanel";
import { useArtifactPanel } from "./useArtifactPanel";

const POSTERLY_SOURCE = "https://github.com/Chenruishuo/posterly/tree/b9f42e5578a49a27525a68f85376bb3bb25af86f";

function publicShareId(): string | null {
  if (typeof window === "undefined") return null;
  const match = window.location.pathname.match(/^\/share\/([^/]+)/u);
  return match ? decodeURIComponent(match[1]) : null;
}

export function artifactUrls(block: ArtifactBlock) {
  if (block.scope === "public") {
    const share = publicShareId();
    if (!share || !block.public_capability) return null;
    const root = chatArtifactUrls.sharedRoot(share, block.public_capability);
    return {
      preview: `${root}/preview`,
      png: `${root}/download/png`,
      pdf: `${root}/download/pdf`,
      owner: null,
    };
  }
  const { artifact_id: artifactId, version_id: versionId } = block;
  if (!artifactId || !versionId) return null;
  const fileUrl = (kind: "source" | "download", path: string) => chatArtifactUrls.file(artifactId, versionId, kind, path);
  return {
    preview: chatArtifactUrls.preview(artifactId, versionId),
    png: fileUrl("download", "poster.png"),
    pdf: null,
    owner: {
      artifactId,
      versionId,
      source: (path: string) => fileUrl("source", path),
      download: (path: string) => fileUrl("download", path),
    },
  };
}

export const gateLabel = (status?: ArtifactBlock["gate_status"]) => ({
  passed: "Passed",
  warnings: "Passed with warnings",
  failed: "Draft—checks failed",
}[status ?? "passed"]);

function useNarrowDialog(): boolean {
  const [narrow, setNarrow] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 760px)").matches,
  );
  React.useEffect(() => {
    const query = window.matchMedia?.("(max-width: 760px)");
    if (!query) return;
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return narrow;
}

const PosterArtifactPanel: React.FC<{ forceDialog?: boolean; readerFallback?: boolean }> = ({
  forceDialog = false,
  readerFallback = false,
}) => {
  const panel = useArtifactPanel();
  const closePanel = panel.close;
  const { state } = panel;
  const block = state.selected;
  const narrow = useNarrowDialog();
  const dialog = forceDialog || narrow;
  const panelRef = React.useRef<HTMLElement>(null);
  const pushedHistoryRef = React.useRef(false);

  const ownedArtifactId = state.open && block?.scope === "owner" ? block.artifact_id : undefined;
  const versionsQuery = useQuery({
    queryKey: chatArtifactKeys.posterVersions(ownedArtifactId),
    queryFn: ownedArtifactId ? () => chatApi.getPosterVersions(ownedArtifactId) : skipToken,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const selectedVersion = versionsQuery.data?.find(
    (version) => version.version_id === state.selectedVersionId,
  );
  const effective = block && selectedVersion ? {
    ...block,
    version_id: selectedVersion.version_id,
    version: selectedVersion.version,
    gate_status: selectedVersion.gate_status,
    total_bytes: selectedVersion.total_bytes,
  } : block;
  const links = effective ? artifactUrls(effective) : null;
  const owned = state.open ? links?.owner ?? null : null;
  const manifestQuery = useQuery({
    queryKey: chatArtifactKeys.manifest(owned?.artifactId, owned?.versionId),
    queryFn: owned ? () => chatApi.getPosterManifest(owned.artifactId, owned.versionId) : skipToken,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const manifest = manifestQuery.data;
  const sourcePath = state.sourceFile ?? manifest?.entrypoint ?? null;
  const sourceQuery = useQuery({
    queryKey: chatArtifactKeys.source(owned?.artifactId, owned?.versionId, sourcePath),
    queryFn: owned && state.tab === "source" && sourcePath
      ? () => chatApi.getArtifactSource(owned.artifactId, owned.versionId, sourcePath)
      : skipToken,
    staleTime: Number.POSITIVE_INFINITY,
  });

  React.useEffect(() => {
    if (!state.open || !dialog) return;
    panelRef.current?.querySelector<HTMLElement>("[data-artifact-close]")?.focus();
    window.history.pushState({ ...window.history.state, pwcArtifactPanel: true }, "");
    pushedHistoryRef.current = true;
    const onPopState = () => {
      pushedHistoryRef.current = false;
      closePanel();
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [closePanel, dialog, state.open]);

  React.useEffect(() => {
    if (!state.open || !dialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closePanel();
        if (pushedHistoryRef.current) {
          pushedHistoryRef.current = false;
          window.history.back();
        }
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = [...panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closePanel, dialog, state.open]);

  if (!state.open || !effective || !links) return null;
  const close = () => {
    closePanel();
    if (dialog && pushedHistoryRef.current) {
      pushedHistoryRef.current = false;
      window.history.back();
    }
  };
  const pdfPath = manifest?.downloads[0]?.path;
  const pdfUrl = effective.scope === "public"
    ? links.pdf
    : pdfPath && links.owner
      ? links.owner.download(pdfPath)
      : null;

  return <section
    ref={panelRef}
    className={`chat-artifact-panel${dialog ? " is-dialog" : " is-docked"}${readerFallback ? " is-reader-fallback" : ""}`}
    role={dialog ? "dialog" : "complementary"}
    aria-modal={dialog ? true : undefined}
    aria-label={effective.title}
    data-testid="artifact-panel"
  >
    <header>
      <div><span>Posterly artifact</span><h2>{effective.title}</h2></div>
      {(versionsQuery.data?.length ?? 0) > 1 && <label className="chat-artifact-version">Version
        <select
          aria-label="Poster version"
          value={effective.version_id}
          onChange={(event) => panel.setVersion(event.target.value)}
        >
          {[...(versionsQuery.data ?? [])].reverse().map((version) => (
            <option value={version.version_id} key={version.version_id}>v{version.version}</option>
          ))}
        </select>
      </label>}
      <button type="button" data-artifact-close aria-label={dialog ? "Back to conversation" : "Close poster"} onClick={close}><X /></button>
    </header>
    <nav aria-label="Poster views">
      <button type="button" aria-pressed={state.tab === "preview"} className={state.tab === "preview" ? "active" : ""} onClick={() => panel.setTab("preview")}>Preview</button>
      {effective.scope === "owner" && <button type="button" aria-pressed={state.tab === "source"} className={state.tab === "source" ? "active" : ""} onClick={() => panel.setTab("source")}>Source</button>}
    </nav>
    <div className="chat-artifact-panel-body">
      {state.tab === "preview"
        ? <img src={links.preview} alt={`Full preview of ${effective.title}`} />
        : <div className="chat-artifact-source-workspace">
            {manifest?.source_files && manifest.source_files.length > 1 && <nav aria-label="Poster source files">
              {manifest.source_files.map((path) => <button type="button" key={path} aria-pressed={sourcePath === path} onClick={() => panel.setSourceFile(path)}>{path}</button>)}
            </nav>}
            <pre><code>{sourceQuery.isError ? "Source could not be loaded." : sourceQuery.data ?? "Loading source…"}</code></pre>
          </div>}
    </div>
    <footer>
      <div className="chat-artifact-metadata">
        <strong>{gateLabel(effective.gate_status)}</strong>
        {manifest && <span>{manifest.canvas.width} × {manifest.canvas.height} {manifest.canvas.unit} · {manifest.canvas.orientation} · {manifest.direction}</span>}
        {manifest?.gate_summary.map((warning) => <span key={warning}>{warning}</span>)}
      </div>
      <div className="chat-artifact-actions">
        <a href={links.png} download><Download /> PNG</a>
        {effective.gate_status !== "failed" && pdfUrl && <a href={pdfUrl} download><Download /> PDF</a>}
        {effective.scope === "owner" && manifest && links.owner && <a href={links.owner.source(manifest.entrypoint)} download><FileCode2 /> HTML</a>}
        {effective.scope === "owner" && manifest && links.owner && <a href={links.owner.source(manifest.gate_report)} download>Gate report</a>}
        <a href={POSTERLY_SOURCE} target="_blank" rel="noreferrer"><ExternalLink /> Posterly source · AGPL-3.0</a>
      </div>
    </footer>
  </section>;
};

export const ArtifactPanel: React.FC<{ forceDialog?: boolean; readerFallback?: boolean }> = (props) => {
  const { state } = useArtifactPanel();
  const selected = state.selected;
  // Paper artifacts are always created from a descriptor, so they carry an ID.
  if (selected?.artifact_kind === "latex_paper" && selected.artifact_id) {
    return <LatexPaperPanel artifactId={selected.artifact_id} title={selected.title} {...props} />;
  }
  return <PosterArtifactPanel {...props} />;
};
