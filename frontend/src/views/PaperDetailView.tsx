import React, { useEffect, useMemo, useRef, useState } from "react";
import "./PaperDetailView.css";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Icon, PaperPreview, SotaBadges } from "@/components";
import LatexTitle from "@/components/LatexTitle";
import { evaluationsApi } from "@/lib/api/evaluations";
import { papersApi } from "@/lib/api/papers";
import {
  assetUrl,
  isNativePdfReaderEnabled,
  isPaperReaderChatEnabled,
  isStagingEnvironment,
} from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { paperEditSubmitMode } from "@/lib/contributorCapabilities";
import { toSotaRanks } from "@/lib/transform";
import { leaderboardBadgeMarkdown } from "@/lib/leaderboardBadges";
import { paperReaderRoute, resetReaderSession } from "@/lib/paperReader";
import { usePaperDetailPageModel } from "@/hooks/usePaperDetailPageModel";
import {
  parseFreshAuthEditSection,
  usePaperEditState,
} from "@/hooks/usePaperEditState";
import type { PaperEditSection } from "@/hooks/usePaperEditState";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

import { PaperAgentEdits } from "@/components/paper-detail/PaperAgentEdits";
import { PaperDetailEditors } from "@/components/paper-detail/PaperDetailEditors";
import { PaperResultsSection } from "@/components/paper-detail/PaperResultsSection";
import { PaperResourceSidebar } from "@/components/paper-detail/PaperResourceSidebar";
import { PaperMetadataSections } from "@/components/paper-detail/PaperMetadataSections";
import { SignInToEditDialog } from "@/components/paper-detail/SignInToEditDialog";
import { SavePaperButton } from "@/components/paper-detail/SavePaperButton";
import { EditableActionButton } from "@/components/paper-detail/EditableActionButton";
import { CodexEnrichPaperDialog } from "@/components/paper-detail/CodexEnrichPaperDialog";
import { isCodexEnrichPaperEnabled } from "@/lib/codexAddEvals";
import { organizationShortName } from "@/lib/organizationNames";
import { AuthorAvatar } from "@/components/AuthorAvatar";

const EDIT_SECTION_LABEL: Record<PaperEditSection, string> = {
  tasks: "tasks",
  methods: "methods",
  results: "evaluation results",
  repositories: "GitHub repositories",
  "project-pages": "project pages",
  "hf-artifacts": "Hugging Face artifacts",
  organizations: "organizations",
  "source-url": "source URL",
  "x-threads": "X threads",
};

function formatLongDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}

function formatResourceLinkLabel(url: string, fallback: string): string {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.replace(/\/$/, "").split("/").filter(Boolean);
    const slug = parts.at(-1);
    if (slug) return slug.replace(/[-_]+/g, " ");
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return fallback;
  }
}

const PaperDetailView: React.FC = () => {
  const { arxivId: rawArxivId } = useParams<{ arxivId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();
  // Admins can save edits directly. Linked authors and everyone else go
  // through the pending-edit queue for admin review.
  const isAdmin = user?.is_admin ?? false;
  const isSignedIn = !!user;
  const editSubmitMode = paperEditSubmitMode(user);

  const {
    arxivId,
    evaluations,
    evaluationsByTask,
    evaluationsLoading,
    paper,
    paperError: error,
    paperLoading: isLoading,
    presentation,
    refetchEvaluations,
    refetchPaper: refetch,
    relatedQuery: relatedQ,
    versions,
    visibleEvaluations,
  } = usePaperDetailPageModel(rawArxivId, editSubmitMode);

  const [showAllAuthors, setShowAllAuthors] = useState(false);

  const { activeEditor, openEditor, setEditorOpen } = usePaperEditState();

  useEffect(() => {
    if (editSubmitMode !== "direct" || !paper?.id) return;
    if (activeEditor && activeEditor !== "results") {
      void papersApi
        .primeCurationState(paper.id)
        .catch(() => undefined);
    }
    if (activeEditor === "results") {
      void evaluationsApi
        .primeCurationState(paper.id)
        .catch(() => undefined);
    }
  }, [activeEditor, editSubmitMode, paper?.id]);

  const [signInSection, setSignInSection] = useState<PaperEditSection | null>(null);
  const freshAuthRecoveryHandled = useRef(false);

  useEffect(() => {
    if (!user || !paper || freshAuthRecoveryHandled.current) return;
    const section = sessionStorage.getItem("pwc:fresh-auth-edit");
    if (!section) return;
    freshAuthRecoveryHandled.current = true;
    const editor = parseFreshAuthEditSection(section);
    const draft = papersApi.freshAuthMutationDraft();
    if (!draft) {
      sessionStorage.removeItem("pwc:fresh-auth-edit");
      if (editor) openEditor(editor);
      return;
    }
    if (
      !window.confirm(
        "You signed in again. Apply the saved destructive catalog edit now? " +
          "The server will recheck the current catalog version before changing anything.",
      )
    ) {
      toast({
        title: "Edit kept locally",
        description: "Nothing was changed. Reload this paper when you are ready to confirm the saved edit.",
      });
      return;
    }
    void papersApi
      .resumeFreshAuthMutation()
      .then(() => {
        toast({ title: "Edit applied", description: "The restored catalog edit was applied." });
        window.location.reload();
      })
      .catch((error: unknown) => {
        toast({
          variant: "destructive",
          title: "Could not apply the saved edit",
          description: error instanceof Error ? error.message : "Please reload and review the edit again.",
        });
      });
  }, [openEditor, paper, toast, user]);

  // Resolve whether the signed-in HF username matches one of the paper's
  // linked authors. Used to surface "you're an author" copy in the pending
  // edit notice; the backend re-checks this at submission time and records
  // `is_author = true` for future auto-approval rules.
  const isLinkedAuthor = useMemo(() => {
    if (!user || !paper?.author_links) return false;
    const me = user.username.toLowerCase();
    return paper.author_links.some(
      (a) =>
        Boolean(a.hf_username) && a.hf_username!.toLowerCase() === me,
    );
  }, [user, paper?.author_links]);

  const openEdit = (section: PaperEditSection): void => {
    if (!isSignedIn) {
      setSignInSection(section);
      return;
    }
    openEditor(section);
  };

  // Auto-index if missing.
  const [indexState, setIndexState] = useState<"idle" | "indexing">("idle");
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indexErrorHint, setIndexErrorHint] = useState<string | null>(null);

  const handleIndex = async () => {
    if (!arxivId) return;
    setIndexState("indexing");
    setIndexError(null);
    setIndexErrorHint(null);
    try {
      await papersApi.indexFromArxiv(arxivId);
      toast({ title: "Indexed", description: "Paper added to database." });
      setTimeout(() => refetch(), 1200);
      setIndexState("idle");
    } catch (e) {
      const err = e as { response?: string; message?: string; status?: number };
      let msg = err.message || "Failed to index paper";
      if (err.response) {
        try {
          msg = JSON.parse(err.response).detail || msg;
        } catch {
          msg = err.response;
        }
      }
      setIndexError(msg);
      if (err.status === 429 || err.status === 503) {
        setIndexErrorHint("Try again later after arXiv has lifted the temporary limit.");
      }
      setIndexState("idle");
    }
  };

  const citationCopy = presentation?.citationCopy ?? "";
  const copyableRanks = presentation?.copyableRanks ?? [];

  const [citationCopied, setCitationCopied] = useState(false);

  const handleCopyCitation = async () => {
    if (!citationCopy) return;
    try {
      await navigator.clipboard.writeText(citationCopy);
      setCitationCopied(true);
      toast({ title: "Citation copied", description: "BibTeX entry copied to clipboard." });
      window.setTimeout(() => setCitationCopied(false), 1500);
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Please copy manually.",
        variant: "destructive",
      });
    }
  };

  const handleCopyLeaderboardBadge = async () => {
    if (!paper) return;
    const paperId = paper.arxiv_id || paper.id;
    const markdown = leaderboardBadgeMarkdown(paperId, copyableRanks);
    if (!markdown) return;
    try {
      await navigator.clipboard.writeText(markdown);
      toast({
        title: "PwC badges copied",
        description: "Each badge follows its current leaderboard result.",
      });
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not access the clipboard. Please try again.",
        variant: "destructive",
      });
    }
  };

  // ── render ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-3/4 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="page">
        <div className="breadcrumb">
          <Link to="/papers">Papers</Link>
          <span className="sep">/</span>
          <span style={{ color: "var(--ink)" }}>arXiv:{arxivId}</span>
        </div>
        <h1 className="detail-title">Paper not indexed yet</h1>
        <p style={{ fontFamily: "var(--serif)", color: "var(--ink-soft)", marginTop: 16, maxWidth: 640 }}>
          We don't have <span style={{ fontFamily: "var(--mono)" }}>arXiv:{arxivId}</span> in the database.
          You can index it from arXiv right now.
        </p>
        {indexError && (
          <Alert variant="destructive" className="mt-4 max-w-xl">
            <AlertDescription>
              <div>{indexError}</div>
              {indexErrorHint && <div className="mt-2">{indexErrorHint}</div>}
            </AlertDescription>
          </Alert>
        )}
        <div className="action-row">
          {isAdmin && (
            <button className="action-btn" onClick={handleIndex} disabled={indexState === "indexing"}>
              <Icon name="sparkle" size={12} />
              {indexState === "indexing" ? "Indexing…" : "Index from arXiv"}
            </button>
          )}
          <Button variant="outline" onClick={() => navigate("/papers")}>
            Browse Papers
          </Button>
        </div>
      </div>
    );
  }

  if (!presentation) return null;
  const {
    allHfArtifactUrls,
    authorEntries,
    citationDisplay,
    hasIntroducedItems,
    hasLineageItems,
    hfArtifactViewer,
    introducedBenchmarks,
    introducedFrameworks,
    introducedMethods,
    introducedSummary,
    numPages,
    paperSourceLabel,
    predecessorPapers,
    projectPages,
    safeAbstractUrl,
    safeConferenceUrl,
    safePdfUrl,
    successorPapers,
  } = presentation;
  const authorLimit = 12;
  const readerRoute = paperReaderRoute(paper, arxivId);
  const readerChatRoute = readerRoute && isNativePdfReaderEnabled() && isPaperReaderChatEnabled()
    && (!isStagingEnvironment() || isAdmin)
    ? readerRoute
    : null;
  const organizations = paper.organizations || [];
  const renderTitleOrg = (o: NonNullable<typeof paper.organizations>[number]) => {
    const orgLabel = organizationShortName(o) ?? o.name;
    return (
      <Link
        key={o.id}
        to={`/orgs/${o.slug}`}
        className={`detail-title-org${o.logo_url ? " detail-title-org--logo" : ""}`}
        title={o.name}
        aria-label={o.name}
      >
        {o.logo_url ? (
          <img
            src={o.logo_url}
            alt=""
            onError={(e) => {
              e.currentTarget.parentElement?.classList.remove("detail-title-org--logo");
              e.currentTarget.replaceWith(orgLabel);
            }}
          />
        ) : (
          orgLabel
        )}
      </Link>
    );
  };
  const visibleAuthors = showAllAuthors || authorEntries.length <= authorLimit
    ? authorEntries
    : authorEntries.slice(0, authorLimit);
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Trending</Link>
        <span className="sep">/</span>
        {paper.arxiv_id && safeAbstractUrl ? (
          <a
            className="breadcrumb-external"
            href={safeAbstractUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="Open on arXiv"
          >
            {paperSourceLabel}
            <span aria-hidden="true">↗</span>
          </a>
        ) : (
          <span>{paperSourceLabel}</span>
        )}
      </div>

      <div className="detail-grid">
        <div>
          <div className="detail-hero">
            <div className="detail-hero-main">
          <h1 className="detail-title">
            <LatexTitle title={paper.title} />
            {organizations.slice(0, -1).map(renderTitleOrg)}
            {/* Keep the pencil on the last org's line so it stays pinned to that logo. */}
            <span className="detail-title-tail">
              {organizations.slice(-1).map(renderTitleOrg)}
              <button
                type="button"
                className="detail-title-edit"
                onClick={() => openEdit("organizations")}
                title="Edit organizations"
                aria-label="Edit organizations"
              >
                <Icon name="pencil" size={11} />
              </button>
            </span>
          </h1>
          <div className="detail-meta">
            <span>Submitted {formatLongDate(paper.published)}</span>
            {numPages && (
              <>
                <span>·</span>
                <span>{numPages} pages</span>
              </>
            )}
            {paper.citation_count != null && (
              <>
                <span>·</span>
                <span>{paper.citation_count.toLocaleString()} citations</span>
              </>
            )}
            {(paper.proceeding || paper.conference_slug) && (
              <>
                <span>·</span>
                {paper.conference_slug ? (
                  <a
                    href={`/conferences/${paper.conference_slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "var(--accent-text)" }}
                  >
                    {(paper.proceeding || paper.conference_name || "").replace(/\s+\d{1,2}$/, "")}
                  </a>
                ) : (
                  <span>{paper.proceeding!.replace(/\s+\d{1,2}$/, "")}</span>
                )}
              </>
            )}
            {versions.length > 1 && (
              <>
                <span>·</span>
                <select
                  className="version-select"
                  value={paper.version}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (!paper.arxiv_id) return;
                    navigate(`/paper/${paper.arxiv_id.replace(/v\d+$/, "")}${v ? `?version=${v}` : ""}`);
                  }}
                >
                  {versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      {v.version} — {formatLongDate(v.published)}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
          <div className="detail-authors">
            {visibleAuthors.map((a, i) => (
              <React.Fragment key={i}>
                {a.hf_username && (
                  <AuthorAvatar className="detail-author-avatar" url={a.hf_avatar_url} />
                )}
                {a.id ? (
                  <Link to={`/authors/${a.id}`}>{a.name}</Link>
                ) : a.hf_username ? (
                  <a
                    href={`https://huggingface.co/${a.hf_username}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`@${a.hf_username} on Hugging Face`}
                  >
                    {a.name}
                  </a>
                ) : (
                  <a>{a.name}</a>
                )}
                {i < visibleAuthors.length - 1 ? ", " : ""}
              </React.Fragment>
            ))}
            {paper.authors.length > authorLimit && (
              <button
                className="show-more-authors"
                onClick={() => setShowAllAuthors((v) => !v)}
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  fontFamily: "var(--mono)",
                  fontSize: 12,
                }}
              >
                {showAllAuthors ? "show fewer" : `+${paper.authors.length - authorLimit} more`}
              </button>
            )}
          </div>

          <div className="action-row">
            {readerRoute && isNativePdfReaderEnabled()
              && (!isStagingEnvironment() || user?.is_admin) ? (
              <Link
                className="action-btn"
                to={readerRoute}
                onClick={() => resetReaderSession(readerRoute)}
              >
                <Icon name="pdf" size={12} /> Read paper
                <span className="nav-new-badge" aria-hidden="true">New</span>
              </Link>
            ) : safePdfUrl ? (
              <a className="action-btn" href={safePdfUrl} target="_blank" rel="noopener noreferrer">
                <Icon name="pdf" size={12} /> View PDF
              </a>
            ) : null}
            {safeAbstractUrl && paper.source === "external" && (
              <EditableActionButton
                showEdit
                onEdit={() => openEdit("source-url")}
                editAriaLabel="Edit source URL"
              >
                <a
                  className="action-btn-segment action-btn-main"
                  href={safeAbstractUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="external" size={12} /> Source page
                </a>
              </EditableActionButton>
            )}
            {projectPages.length === 1 ? (
              <EditableActionButton
                showEdit
                onEdit={() => openEdit("project-pages")}
                editAriaLabel="Edit project pages"
              >
                <a
                  className="action-btn-segment action-btn-main"
                  href={projectPages[0].safeHref ?? undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="globe" size={12} /> Project page
                </a>
              </EditableActionButton>
            ) : null}
            {projectPages.length > 1 ? (
              <EditableActionButton
                showEdit
                onEdit={() => openEdit("project-pages")}
                editAriaLabel="Edit project pages"
              >
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className="action-btn-segment action-btn-main"
                    >
                      <Icon name="globe" size={12} /> Project page
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="project-page-menu">
                    {projectPages.map((page, index) => (
                      <DropdownMenuItem key={page.url} asChild>
                        {page.safeHref ? (
                          <a href={page.safeHref} target="_blank" rel="noopener noreferrer">
                            {formatResourceLinkLabel(page.url, `Project page ${index + 1}`)}
                          </a>
                        ) : (
                          <span>{formatResourceLinkLabel(page.url, `Project page ${index + 1}`)}</span>
                        )}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </EditableActionButton>
            ) : null}
            {projectPages.length === 0 && isSignedIn ? (
              <button
                type="button"
                className="action-btn"
                onClick={() => openEdit("project-pages")}
                title="Add project page"
              >
                <Icon name="globe" size={12} /> Add project page
              </button>
            ) : null}
            {safeConferenceUrl && (
              <a className="action-btn" href={safeConferenceUrl} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> Conference
              </a>
            )}
            <PaperAgentEdits paperId={Number(paper.id)} />
            {isAdmin && isCodexEnrichPaperEnabled() && (
              <CodexEnrichPaperDialog
                paperId={Number(paper.id)}
                paperTitle={paper.title}
                onComplete={() => void refetch()}
              />
            )}
            <SavePaperButton paperId={paper.id} />
          </div>

          {paper.leaderboard_ranks && paper.leaderboard_ranks.length > 0 && (
            <SotaBadges
              wrap
              paperHref={`/paper/${paper.arxiv_id || paper.id}`}
              ranks={toSotaRanks(paper.leaderboard_ranks)}
            />
          )}
            </div>

            <div className="detail-hero-thumb detail-thumb-wrap">
              <PaperPreview
                paperId={paper.arxiv_id || paper.id}
                title={paper.title}
                thumbnailUrl={assetUrl(paper.thumbnail_url)}
                priority
              />
            </div>
          </div>

          {hasIntroducedItems && (
            <div
              className={`introduced-banner${
                introducedFrameworks.length > 0 ? " introduced-banner--framework" : ""
              }`}
            >
              <span className="introduced-label">Introduced</span>
              <div className="introduced-methods">
                {introducedMethods.map((m) => (
                  <button
                    key={`method-${m.id}`}
                    type="button"
                    className="introduced-pill"
                    onClick={() => navigate(`/methods/${m.slug || m.id}`)}
                  >
                    {m.name}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
                {introducedBenchmarks.map((b) => (
                  <button
                    key={`benchmark-${b.id}`}
                    type="button"
                    className="introduced-pill"
                    onClick={() => navigate(`/benchmark/${b.slug || b.id}`)}
                  >
                    {b.name}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
                {introducedFrameworks.map((framework) => (
                  <button
                    key={`framework-${framework.slug}`}
                    type="button"
                    className="introduced-pill"
                    onClick={() => navigate(`/frameworks#framework-${framework.slug}`)}
                  >
                    {framework.name}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
              </div>
              <span className="introduced-note">
                This paper is the canonical source for {introducedSummary}.
              </span>
            </div>
          )}

          {hasLineageItems && (
            <div className="introduced-banner lineage-banner">
              {successorPapers.length > 0 && (
                <div className="lineage-row">
                  <span className="introduced-label lineage-label">
                    {successorPapers.length === 1 ? "Follow-up paper" : "Follow-up papers"}
                  </span>
                  <div className="introduced-methods">
                    {successorPapers.map((p) => (
                      <button
                        key={`successor-${p.id}`}
                        type="button"
                        className="introduced-pill lineage-pill"
                        onClick={() => navigate(`/paper/${p.route_identifier}`)}
                      >
                        <LatexTitle title={p.title} />
                        <span className="introduced-arrow">→</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {predecessorPapers.length > 0 && (
                <div className="lineage-row">
                  <span className="introduced-label lineage-label">
                    {predecessorPapers.length === 1 ? "Predecessor paper" : "Predecessor papers"}
                  </span>
                  <div className="introduced-methods">
                    {predecessorPapers.map((p) => (
                      <button
                        key={`predecessor-${p.id}`}
                        type="button"
                        className="introduced-pill lineage-pill"
                        onClick={() => navigate(`/paper/${p.route_identifier}`)}
                      >
                        <span className="introduced-arrow lineage-arrow-back">←</span>
                        <LatexTitle title={p.title} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <PaperMetadataSections
            canEdit
            onEditMethods={() => openEdit("methods")}
            onEditTasks={() => openEdit("tasks")}
            paper={paper}
            readerChatRoute={readerChatRoute}
          />
          <PaperResultsSection
            canCopyBadge={copyableRanks.length > 0}
            canEdit
            evaluationsByTask={evaluationsByTask}
            evaluationsLoading={evaluationsLoading}
            isAdmin={isAdmin}
            onCopyBadge={handleCopyLeaderboardBadge}
            onEdit={() => openEdit("results")}
            onRefresh={() => void refetchEvaluations()}
            paper={paper}
            visibleEvaluationCount={visibleEvaluations?.length ?? 0}
          />

        </div>

        <PaperResourceSidebar
          allHfArtifactUrls={allHfArtifactUrls}
          citationCopied={citationCopied}
          citationDisplay={citationDisplay}
          hfArtifactViewer={hfArtifactViewer}
          onCopyCitation={handleCopyCitation}
          onEditHfArtifacts={() => openEdit("hf-artifacts")}
          onEditRepositories={() => openEdit("repositories")}
          onEditXThreads={() => openEdit("x-threads")}
          paper={paper}
          relatedIsLoading={relatedQ.isLoading}
          relatedPapers={relatedQ.data}
          user={user}
        />
      </div>

      <PaperDetailEditors
        activeEditor={activeEditor}
        arxivId={arxivId}
        editSubmitMode={editSubmitMode}
        evaluations={evaluations ?? []}
        isAdmin={isAdmin}
        isLinkedAuthor={isLinkedAuthor}
        onOpenChange={setEditorOpen}
        paper={paper}
      />
      <SignInToEditDialog
        open={signInSection !== null}
        onOpenChange={(open) => {
          if (!open) setSignInSection(null);
        }}
        sectionLabel={
          signInSection ? EDIT_SECTION_LABEL[signInSection] : "this paper"
        }
        returnTo={typeof window !== "undefined" ? window.location.pathname : "/"}
      />
    </div>
  );
};

export default PaperDetailView;
