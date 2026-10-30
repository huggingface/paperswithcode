import React from "react";
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCode2, FilePlus2, Pencil, Save, Trash2, X } from "lucide-react";

import { chatApi } from "@/lib/api/chat";
import { chatArtifactUrls } from "@/lib/chatArtifactUrls";
import type { LatexPaperVersionDescriptor } from "@/lib/api/chat.types";
import { ApiError } from "@/lib/apiTransport";
import { chatArtifactKeys } from "@/lib/chatSessionQueries";
import { PdfViewer } from "@/components/pdf/PdfViewer";
import { LatexSourceEditor } from "./LatexSourceEditor";
import { useArtifactPanel } from "./useArtifactPanel";

interface Draft {
  parentVersionId: string;
  files: Record<string, string>;
}

/** The backend's `detail.message` for a refused paper change, else the fallback. */
function paperErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : fallback;
  const detail = error.detail;
  return typeof detail === "object" && detail !== null && "message" in detail && typeof detail.message === "string"
    ? detail.message
    : fallback;
}

function draftKey(artifactId: string): string {
  return `pwc:latex-paper-draft:${artifactId}`;
}

function sameFiles(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftPaths = Object.keys(left).sort();
  const rightPaths = Object.keys(right).sort();
  return leftPaths.length === rightPaths.length
    && leftPaths.every((path, index) => path === rightPaths[index] && left[path] === right[path]);
}

function isSupportedPath(path: string): boolean {
  return !path.includes("\\") && /^(?!\/)(?!.*(?:^|\/)\.\.?\/)[^\0]{1,300}\.(?:tex|bib)$/iu.test(path);
}

function provenanceLabel(version: LatexPaperVersionDescriptor): string {
  const action = version.provenance?.action ?? (version.actor_type === "restore" ? "restore" : version.actor_type === "ai" ? "ai_draft" : "human_save");
  const label = {
    human_save: "Human save",
    ai_draft: "AI draft",
    ai_repair: "AI repair",
    restore: "Restore",
  }[action];
  return version.provenance?.model_identity ? `${label} · ${version.provenance.model_identity}` : label;
}

export const LatexPaperPanel: React.FC<{
  artifactId: string;
  title: string;
  forceDialog?: boolean;
  readerFallback?: boolean;
}> = ({ artifactId, title, forceDialog = false }) => {
  const panel = useArtifactPanel();
  const queryClient = useQueryClient();
  const closePanel = panel.close;
  const [narrow, setNarrow] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 760px)").matches,
  );
  const [files, setFiles] = React.useState<Record<string, string>>({});
  const [baseline, setBaseline] = React.useState<Record<string, string>>({});
  const [draftParent, setDraftParent] = React.useState<string | null>(null);
  const [checkedOut, setCheckedOut] = React.useState(false);
  const [staleDraft, setStaleDraft] = React.useState(false);
  const [editorError, setEditorError] = React.useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [historyCursor, setHistoryCursor] = React.useState<string | null>(null);
  const initializedVersion = React.useRef<string | null>(null);
  const panelRef = React.useRef<HTMLElement>(null);
  const pushedHistoryRef = React.useRef(false);
  const dialog = forceDialog || narrow;
  const draftIsDirty = draftParent !== null && !sameFiles(files, baseline);

  React.useEffect(() => {
    const query = window.matchMedia?.("(max-width: 760px)");
    if (!query) return;
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  React.useEffect(() => {
    if (!dialog) return;
    panelRef.current?.querySelector<HTMLElement>("[data-artifact-close]")?.focus();
    window.history.pushState({ ...window.history.state, pwcArtifactPanel: true }, "");
    pushedHistoryRef.current = true;
    const onPopState = () => {
      if (draftIsDirty && !window.confirm("Leave this view? Unsaved paper edits remain in this browser.")) {
        window.history.pushState({ ...window.history.state, pwcArtifactPanel: true }, "");
        pushedHistoryRef.current = true;
        return;
      }
      pushedHistoryRef.current = false;
      closePanel();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (draftIsDirty && !window.confirm("Leave this view? Unsaved paper edits remain in this browser.")) return;
      closePanel();
      if (pushedHistoryRef.current) { pushedHistoryRef.current = false; window.history.back(); }
    };
    window.addEventListener("popstate", onPopState);
    document.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("popstate", onPopState); document.removeEventListener("keydown", onKeyDown); };
  }, [closePanel, dialog, draftIsDirty]);
  React.useEffect(() => {
    if (!dialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = [...panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [contenteditable="true"], [tabindex]:not([tabindex="-1"])',
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
  }, [dialog]);
  React.useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!draftIsDirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [draftIsDirty]);
  React.useEffect(() => {
    const onArtifactNavigation = (event: Event) => {
      if (draftIsDirty && !window.confirm("Leave this view? Unsaved paper edits remain in this browser.")) event.preventDefault();
    };
    window.addEventListener("pwc:artifact-navigation", onArtifactNavigation);
    return () => window.removeEventListener("pwc:artifact-navigation", onArtifactNavigation);
  }, [draftIsDirty]);

  const descriptorQuery = useQuery({
    queryKey: chatArtifactKeys.latexPaper(artifactId),
    queryFn: () => chatApi.getLatexPaper(artifactId),
    staleTime: 5_000,
  });
  const descriptor = descriptorQuery.data;
  const source = descriptor?.source_head;
  const preview = descriptor?.preview_head;
  const historyQuery = useQuery({
    queryKey: chatArtifactKeys.history(artifactId, historyCursor),
    queryFn: () => chatApi.getLatexPaperHistory(artifactId, historyCursor),
    enabled: historyOpen, staleTime: Number.POSITIVE_INFINITY,
  });
  const sourceVersionId = source?.version_id;
  const filesTabVersionId = panel.state.tab === "files" ? sourceVersionId : undefined;
  const manifestQuery = useQuery({
    queryKey: chatArtifactKeys.manifest(artifactId, sourceVersionId),
    queryFn: filesTabVersionId
      ? () => chatApi.getLatexPaperManifest(artifactId, filesTabVersionId)
      : skipToken,
    staleTime: Number.POSITIVE_INFINITY,
  });
  const textFiles = manifestQuery.data?.files.filter((file) => (
    file.media_type === "text/x-tex" || file.media_type === "application/x-bibtex"
  )) ?? [];
  const figureFiles = manifestQuery.data?.files.filter((file) => (
    file.media_type === "image/png" || file.media_type === "image/jpeg" || file.media_type === "application/pdf"
  )) ?? [];
  const sourceFilesQuery = useQuery({
    queryKey: chatArtifactKeys.sourceFiles(artifactId, sourceVersionId),
    queryFn: filesTabVersionId && textFiles.length
      ? async () => Object.fromEntries(await Promise.all(textFiles.map(async (file) => (
          [file.path, await chatApi.getArtifactSource(artifactId, filesTabVersionId, file.path)] as const
        ))))
      : skipToken,
    staleTime: Number.POSITIVE_INFINITY,
  });
  React.useEffect(() => { setCheckedOut(false); }, [source?.version_id]);
  React.useEffect(() => {
    if (!source?.version_id || !sourceFilesQuery.data || initializedVersion.current === source.version_id) return;
    const serverFiles = sourceFilesQuery.data;
    let recovered = serverFiles;
    let stale = false;
    let recoveredParent = source.version_id;
    try {
      const stored = window.localStorage.getItem(draftKey(artifactId));
      const draft = stored ? JSON.parse(stored) as Draft : null;
      if (draft?.files && typeof draft.files === "object") {
        recovered = draft.files;
        stale = draft.parentVersionId !== source.version_id;
        recoveredParent = draft.parentVersionId;
      }
    } catch { /* An invalid local draft must not prevent a safe server checkout. */ }
    initializedVersion.current = source.version_id;
    setFiles(recovered);
    setBaseline(serverFiles);
    setDraftParent(recoveredParent);
    setStaleDraft(stale);
    setCheckedOut(true);
    if (stale) setEditorError("This local draft is based on an older paper version. Copy or discard it before saving the latest version.");
    if (!panel.state.sourceFile || !recovered[panel.state.sourceFile]) panel.setSourceFile(manifestQuery.data?.root_document ?? null);
  }, [artifactId, manifestQuery.data?.root_document, panel, source?.version_id, sourceFilesQuery.data]);
  React.useEffect(() => {
    if (!draftParent) return;
    const key = draftKey(artifactId);
    if (!draftIsDirty) { window.localStorage.removeItem(key); return; }
    window.localStorage.setItem(key, JSON.stringify({ parentVersionId: draftParent, files } satisfies Draft));
  }, [artifactId, draftIsDirty, draftParent, files]);

  const showSaved = (saved: typeof descriptor) => {
    queryClient.setQueryData(chatArtifactKeys.latexPaper(artifactId), saved);
    void queryClient.invalidateQueries({ queryKey: chatArtifactKeys.manifest(artifactId) });
    void queryClient.invalidateQueries({ queryKey: chatArtifactKeys.sourceFiles(artifactId) });
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!source?.version_id) throw new Error("Paper source is not ready to save");
      return chatApi.saveLatexPaper(artifactId, source.version_id, files);
    },
    onSuccess: (saved) => {
      showSaved(saved);
      initializedVersion.current = saved.source_head?.version_id ?? null;
      setBaseline(files);
      setDraftParent(saved.source_head?.version_id ?? null);
      window.localStorage.removeItem(draftKey(artifactId));
      setEditorError(null);
      setStaleDraft(false);
      panel.setTab("preview");
    },
    onError: (error) => setEditorError(paperErrorMessage(error, "Could not save paper")),
  });

  const restoreMutation = useMutation({
    mutationFn: (sourceVersionId: string) => {
      if (!source?.version_id) throw new Error("Paper source is not ready to restore");
      return chatApi.restoreLatexPaperVersion(artifactId, sourceVersionId, source.version_id);
    },
    onSuccess: (restored) => {
      showSaved(restored);
      void queryClient.invalidateQueries({ queryKey: chatArtifactKeys.history(artifactId) });
      initializedVersion.current = null;
      setCheckedOut(false);
      setHistoryCursor(null);
      setEditorError(null);
      panel.setTab("preview");
    },
    onError: (error) => setEditorError(paperErrorMessage(error, "Could not restore paper version")),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      if (!source?.version_id) throw new Error("Paper source is not ready to upload a figure");
      if (draftIsDirty) throw new Error("Save or discard text edits before uploading a figure");
      return chatApi.uploadLatexPaperFigure(artifactId, source.version_id, file);
    },
    onSuccess: (uploaded) => {
      showSaved(uploaded);
      setEditorError(null);
    },
    onError: (error) => setEditorError(paperErrorMessage(error, "Could not upload figure")),
  });

  const refreshMutation = useMutation({
    mutationFn: () => chatApi.refreshLatexPaperCompile(artifactId),
    onSuccess: (updated) => queryClient.setQueryData(chatArtifactKeys.latexPaper(artifactId), updated),
  });
  const refreshCompile = refreshMutation.mutate;
  const sourceCompileStatus = source?.compile_status;
  React.useEffect(() => {
    if (!sourceVersionId || !["queued", "compiling"].includes(sourceCompileStatus ?? "")) return;
    const timer = window.setTimeout(() => refreshCompile(), 2_000);
    return () => window.clearTimeout(timer);
  }, [refreshCompile, sourceCompileStatus, sourceVersionId]);

  const sourcePath = panel.state.sourceFile ?? manifestQuery.data?.root_document ?? null;
  const canEdit = descriptor?.editing_enabled === true && Boolean(source?.version_id) && checkedOut && !staleDraft && !saveMutation.isPending;
  const historyVersionNumbers = new Map(
    historyQuery.data?.items.map((version) => [version.version_id, version.version]) ?? [],
  );
  const previewUrl = preview ? chatArtifactUrls.preview(artifactId, preview.version_id) : null;
  const outOfDate = Boolean(source && preview && source.version_id !== preview.version_id);
  const guardDirty = () => !draftIsDirty || window.confirm("Leave this view? Unsaved paper edits remain in this browser.");
  const selectTab = (tab: "preview" | "files") => {
    if (tab !== panel.state.tab && !guardDirty()) return false;
    panel.setTab(tab);
    return true;
  };
  const moveBetweenTabs = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (!(["ArrowLeft", "ArrowRight", "Home", "End"] as string[]).includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "ArrowLeft" || event.key === "Home" ? "preview" : "files";
    if (!selectTab(next)) return;
    event.currentTarget.parentElement?.querySelector<HTMLElement>(`#paper-${next}-tab`)?.focus();
  };
  const selectFile = (path: string) => {
    if (path !== sourcePath && draftIsDirty && !window.confirm("Switch files? Unsaved edits stay in this browser.")) return;
    panel.setSourceFile(path);
  };
  const addFile = () => {
    const path = window.prompt("New TeX or BibTeX file name", "section.tex");
    if (!path) return;
    if (!isSupportedPath(path) || files[path]) { setEditorError("Choose a new safe .tex or .bib filename."); return; }
    if (Object.keys(files).length >= 100) { setEditorError("A paper can contain at most 100 files."); return; }
    setFiles({ ...files, [path]: "" }); setEditorError(null); panel.setSourceFile(path);
  };
  const renameFile = () => {
    if (!sourcePath || sourcePath === manifestQuery.data?.root_document) return;
    const path = window.prompt("Rename file", sourcePath);
    if (!path || path === sourcePath) return;
    if (!isSupportedPath(path) || files[path]) { setEditorError("Choose a new safe .tex or .bib filename."); return; }
    const next = { ...files, [path]: files[sourcePath] }; delete next[sourcePath]; setFiles(next); panel.setSourceFile(path);
  };
  const deleteFile = () => {
    if (!sourcePath || sourcePath === manifestQuery.data?.root_document) return;
    if (!window.confirm(`Delete ${sourcePath}?`)) return;
    const next = { ...files }; delete next[sourcePath]; setFiles(next); panel.setSourceFile(manifestQuery.data?.root_document ?? null);
  };
  const discardStaleDraft = () => {
    if (!staleDraft || !window.confirm("Discard this stale local draft?")) return;
    window.localStorage.removeItem(draftKey(artifactId));
    setFiles(baseline);
    setDraftParent(source?.version_id ?? null);
    setStaleDraft(false);
    setEditorError(null);
  };
  const close = () => {
    if (!guardDirty()) return;
    closePanel();
    if (dialog && pushedHistoryRef.current) { pushedHistoryRef.current = false; window.history.back(); }
  };
  const askAiToFix = () => {
    if (!source || source.compile_status !== "failed" || source.repair_exhausted) return;
    const diagnostics = (source.compile_diagnostics ?? []).slice(0, 20).map((item) => (
      `${item.file ?? "project"}${item.line ? `:${item.line}` : ""}: ${item.message}`
    )).join("\n");
    panel.askAiToFix(
      `Repair the failed paper source version ${source.version_id}. Use pwc-paper to inspect and repair it; make no more than three attempts. Compiler diagnostics:\n${diagnostics || "No compiler diagnostic was available."}`,
    );
  };
  const selectDiagnostic = (path?: string | null) => {
    if (!path || !selectTab("files")) return;
    panel.setSourceFile(path);
  };

  return <section
    ref={panelRef}
    className={`chat-artifact-panel${dialog ? " is-dialog" : " is-docked"}`}
    role={dialog ? "dialog" : "complementary"}
    aria-modal={dialog ? true : undefined}
    aria-labelledby="latex-paper-title"
    data-testid="latex-paper-panel"
  >
    <header>
      <div>
        <span>Private paper</span>
        <h2 id="latex-paper-title">{title}</h2>
        <p className="chat-paper-status" role="status" aria-live="polite">
          {source ? `Source v${source.version} · ${source.compile_status}` : "Preparing paper source"}
          {outOfDate ? " · Preview out of date" : ""}
        </p>
        <p className="chat-paper-privacy-note">This paper is private to this chat. Source, figures, and PDFs are stored privately; AI-authored text needs your review.</p>
      </div>
      <div className="chat-artifact-header-actions">
        <button type="button" aria-expanded={historyOpen} aria-controls="paper-version-history" onClick={() => { setHistoryCursor(null); setHistoryOpen(!historyOpen); }}>Version history</button>
        <button type="button" data-artifact-close aria-label={dialog ? "Back to conversation" : "Close paper"} onClick={close}><X /></button>
      </div>
    </header>
    <nav aria-label="Paper views" role="tablist">
      <button type="button" id="paper-preview-tab" role="tab" aria-selected={panel.state.tab === "preview"} aria-controls="paper-preview-panel" tabIndex={panel.state.tab === "preview" ? 0 : -1} className={panel.state.tab === "preview" ? "active" : ""} onClick={() => selectTab("preview")} onKeyDown={moveBetweenTabs}>Preview</button>
      <button type="button" id="paper-files-tab" role="tab" aria-selected={panel.state.tab === "files"} aria-controls="paper-files-panel" tabIndex={panel.state.tab === "files" ? 0 : -1} className={panel.state.tab === "files" ? "active" : ""} onClick={() => selectTab("files")} onKeyDown={moveBetweenTabs}>Files</button>
    </nav>
    <div id={panel.state.tab === "preview" ? "paper-preview-panel" : "paper-files-panel"} role="tabpanel" aria-labelledby={panel.state.tab === "preview" ? "paper-preview-tab" : "paper-files-tab"} className="chat-artifact-panel-body">
      {panel.state.tab === "preview"
        ? descriptorQuery.isError
          ? <div role="alert">Could not load paper details. <button type="button" onClick={() => void descriptorQuery.refetch()}>Retry paper details</button></div>
          : previewUrl
            ? <PdfViewer key={preview?.version_id} url={previewUrl} downloadUrl={chatArtifactUrls.pdfExport(artifactId)} paperKey={`${artifactId}:${preview?.version_id}`} paperTitle={title} paperHref="/chat" chrome="canvas" />
            : !source
              ? <p role="status">Paper source and compiled preview are not available yet.</p>
              : source.compile_status === "failed"
                ? <p role="alert">No compiled preview is available for this failed source version. Review the diagnostics or fix the paper in Files.</p>
                : ["queued", "compiling"].includes(source.compile_status)
                  ? <p role="status">Preview is compiling. The stored source is available in Files.</p>
                  : <p role="alert">No compiled preview is available for this source version.</p>
        : <div className="chat-artifact-source-workspace">
            <nav aria-label="Paper source files">
              {textFiles.map((file) => <button type="button" key={file.path} aria-pressed={sourcePath === file.path} onClick={() => selectFile(file.path)}>{file.path}</button>)}
              {canEdit && <button type="button" className="latex-file-action" aria-label="Add TeX file" onClick={addFile}><FilePlus2 /> Add file</button>}
              {canEdit && <label className="latex-file-action">Upload figure<input aria-label="Upload figure" type="file" accept="image/png,image/jpeg,application/pdf,.png,.jpg,.jpeg,.pdf" disabled={uploadMutation.isPending} onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (file) uploadMutation.mutate(file);
              }} /></label>}
              {figureFiles.map((file) => source && <a key={file.path} href={chatArtifactUrls.file(artifactId, source.version_id, "figures", file.path)} download>{file.path}</a>)}
            </nav>
            <div className="latex-editor-column">
              {sourcePath && files[sourcePath] !== undefined
                ? <LatexSourceEditor path={sourcePath} value={files[sourcePath]} readOnly={!canEdit} onChange={(content) => setFiles({ ...files, [sourcePath]: content })} />
                : <p>{sourceFilesQuery.isError ? "Source could not be loaded." : "Loading source…"}</p>}
              {canEdit && sourcePath && sourcePath !== manifestQuery.data?.root_document && <div className="latex-file-buttons">
                <button type="button" onClick={renameFile}><Pencil /> Rename</button>
                <button type="button" onClick={deleteFile}><Trash2 /> Delete</button>
              </div>}
            </div>
          </div>}
      {historyOpen && <section id="paper-version-history" className="chat-artifact-history" aria-label="Paper version history">
        <h3>Version history</h3>
        {historyQuery.isLoading && <p>Loading history…</p>}
        {historyQuery.isError && <p role="alert">Paper history could not be loaded.</p>}
        {historyQuery.data?.items.map((version) => <article key={version.version_id}>
          <strong>v{version.version} · {version.compile_status}</strong>
          <span>{provenanceLabel(version)}</span>
          {version.created_at && <time dateTime={version.created_at}>{version.created_at}</time>}
          {version.parent_version_id && <span>Parent {historyVersionNumbers.has(version.parent_version_id) ? `v${historyVersionNumbers.get(version.parent_version_id)}` : version.parent_version_id}</span>}
          {version.provenance?.changed_files.length ? <span>Changed: {version.provenance.changed_files.join(", ")}</span> : null}
          {version.provenance?.restored_from_version_id && <span>Restored from {version.provenance.restored_from_version_id}</span>}
          {version.provenance?.change_summary && <p>{version.provenance.change_summary}</p>}
          {version.provenance?.reference_changes.map((change) => <p key={change}>{change}</p>)}
          <a href={chatArtifactUrls.sourceZip(artifactId, version.version_id)} download>Source ZIP</a>
          {descriptor?.editing_enabled && source?.version_id && version.version_id !== source.version_id && <button type="button" disabled={restoreMutation.isPending || draftIsDirty} onClick={() => restoreMutation.mutate(version.version_id)}>Restore version {version.version}</button>}
        </article>)}
        {historyQuery.data?.next_cursor && <button type="button" onClick={() => setHistoryCursor(historyQuery.data?.next_cursor ?? null)}>Load older versions</button>}
      </section>}
    </div>
    <footer>
      <div className="chat-artifact-metadata" aria-live="polite">
        {outOfDate && <strong>Out of date</strong>}
        {source?.compile_diagnostics?.map((diagnostic, index) => <button
          type="button"
          key={`${diagnostic.file ?? "global"}:${diagnostic.line ?? ""}:${index}`}
          onClick={() => selectDiagnostic(diagnostic.file)}
          className="latex-compile-diagnostic"
        >{diagnostic.file ? `${diagnostic.file}${diagnostic.line ? `:${diagnostic.line}` : ""}: ` : ""}{diagnostic.message}</button>)}
        {editorError && <span role="alert">{editorError}</span>}
        {staleDraft && <button type="button" onClick={discardStaleDraft}>Discard stale local draft</button>}
      </div>
      <div className="chat-artifact-actions">
        {source?.compile_status === "failed" && !source.repair_exhausted && <button type="button" onClick={askAiToFix}>Ask AI to fix</button>}
        {source?.compile_status === "failed" && source.repair_exhausted && <span role="status">AI repair attempts exhausted</span>}
        {panel.state.tab === "files" && canEdit && <button type="button" disabled={!draftIsDirty} onClick={() => saveMutation.mutate()}><Save />{saveMutation.isPending ? "Saving…" : "Save & Compile"}</button>}
        {source && <a href={chatArtifactUrls.sourceZip(artifactId, source.version_id)} download><FileCode2 /> Source ZIP</a>}
      </div>
    </footer>
  </section>;
};
