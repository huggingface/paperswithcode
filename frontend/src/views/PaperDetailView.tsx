import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Icon, MethodChip, TagChip } from "@/components";
import LatexTitle, { LatexText } from "@/components/LatexTitle";
import { apiClient, indexPaperFromArxiv } from "@/lib/api";
import type { Paper } from "@/lib/api";
import { apiUrl } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";
import { summarizeRepos } from "@/lib/transform";
import { formatMetricValue } from "@/lib/utils";
import { usePaper } from "@/hooks/usePapers";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { usePaperEditState } from "@/hooks/usePaperEditState";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

import { EditTasksDialog } from "@/components/paper-detail/EditTasksDialog";
import { EditMethodsDialog } from "@/components/paper-detail/EditMethodsDialog";
import { EditRepositoriesDialog } from "@/components/paper-detail/EditRepositoriesDialog";
import { EditProjectPagesDialog } from "@/components/paper-detail/EditProjectPagesDialog";
import { EditEvaluationsDialog } from "@/components/paper-detail/EditEvaluationsDialog";
import { SavePaperButton } from "@/components/paper-detail/SavePaperButton";

const ABSTRACT_PREVIEW_LEN = 360;
const REPO_PREVIEW_LIMIT = 3;

function formatLongDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}

function formatStars(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatProjectPageLabel(url: string, total: number, index: number): string {
  if (total === 1) return "Project page";

  try {
    const parsed = new URL(url);
    const slug = parsed.pathname.replace(/\/$/, "").split("/").filter(Boolean).pop();
    if (slug) return `Project: ${slug.replace(/[-_]+/g, " ")}`;
    return `Project: ${parsed.hostname.replace(/^www\./, "")}`;
  } catch {
    return `Project page ${index + 1}`;
  }
}

const PaperDetailView: React.FC = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();
  const canEditPaper = user?.is_admin ?? false;

  const { data: paper, isLoading, error, refetch } = usePaper(arxivId || "", !!arxivId);
  const [secondaryQueriesEnabled, setSecondaryQueriesEnabled] = useState(false);

  useEffect(() => {
    setSecondaryQueriesEnabled(false);
    if (!paper?.id) return;

    const timeoutId = window.setTimeout(() => setSecondaryQueriesEnabled(true), 0);
    return () => window.clearTimeout(timeoutId);
  }, [paper?.id]);

  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(
    secondaryQueriesEnabled ? paper?.arxiv_id : undefined,
  );
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByPaper(
    paper?.id,
    secondaryQueriesEnabled && !!paper?.id,
  );
  const explicitHfArtifacts = useMemo(
    () => ({
      models: paper?.hf_models ?? [],
      datasets: paper?.hf_datasets ?? [],
      spaces: paper?.hf_spaces ?? [],
    }),
    [paper?.hf_models, paper?.hf_datasets, paper?.hf_spaces],
  );

  // Group evaluations by task so the results section can show one mini-table
  // per task with a shared heading, instead of repeating the task on every row.
  // The backend returns rows sorted by benchmark popularity (most-evaluated
  // benchmark first); we preserve that order both across groups (insertion
  // order of the Map) and within each group's rows so model variants on the
  // same benchmark stay together.
  const evaluationsByTask = useMemo(() => {
    if (!evaluations) return [];
    type EvalRow = (typeof evaluations)[number];
    const groups = new Map<
      string,
      { taskId: string; taskName: string; taskSlug?: string; rows: EvalRow[] }
    >();
    for (const e of evaluations) {
      const key = e.task_id;
      const existing = groups.get(key);
      if (existing) {
        existing.rows.push(e);
      } else {
        groups.set(key, {
          taskId: key,
          taskName: e.task_name || "—",
          taskSlug: e.task_slug,
          rows: [e],
        });
      }
    }
    return Array.from(groups.values());
  }, [evaluations]);

  // Paper version dropdown (PLAN.md §7.5)
  const versionsQ = useQuery({
    queryKey: ["paper-versions", paper?.arxiv_id],
    queryFn: async () => {
      // Strip any vN suffix to get the canonical id.
      const raw = paper!.arxiv_id!.replace(/v\d+$/, "");
      const resp = await fetch(apiUrl(`/api/v1/papers/arxiv/${raw}/versions`));
      if (!resp.ok) return [] as Paper[];
      return (await resp.json()) as Paper[];
    },
    enabled: secondaryQueriesEnabled && !!paper?.arxiv_id,
    staleTime: 10 * 60 * 1000,
  });

  // Related papers: same first task slug.
  const relatedQ = useQuery({
    queryKey: ["related-papers", paper?.tasks?.[0]?.id],
    queryFn: () =>
      apiClient.getTaskPapers(paper!.tasks![0]!.id, {
        page: 1,
        page_size: 5,
        order_by: "citation_count",
        order_dir: "desc",
        include_resources: false,
      }),
    enabled: secondaryQueriesEnabled && !!paper?.tasks?.[0]?.id,
    staleTime: 10 * 60 * 1000,
    select: (res) => res.results.filter((p) => p.id !== paper?.id).slice(0, 4),
  });

  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const [reposExpanded, setReposExpanded] = useState(false);

  const {
    isEditingTasks,
    setIsEditingTasks,
    isEditingMethods,
    setIsEditingMethods,
    isEditingRepositories,
    setIsEditingRepositories,
    isEditingProjectPages,
    setIsEditingProjectPages,
    isEditingEvaluations,
    setIsEditingEvaluations,
  } = usePaperEditState();

  // Auto-index if missing.
  const [indexState, setIndexState] = useState<"idle" | "indexing" | "error">("idle");
  const [indexError, setIndexError] = useState<string | null>(null);

  const handleIndex = async () => {
    if (!arxivId) return;
    setIndexState("indexing");
    setIndexError(null);
    try {
      await indexPaperFromArxiv(arxivId);
      toast({ title: "Indexed", description: "Paper added to database." });
      setTimeout(() => refetch(), 1200);
      setIndexState("idle");
    } catch (e) {
      const err = e as { response?: string; message?: string };
      let msg = err.message || "Failed to index paper";
      if (err.response) {
        try {
          msg = JSON.parse(err.response).detail || msg;
        } catch {
          msg = err.response;
        }
      }
      setIndexError(msg);
      setIndexState("error");
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
            <AlertDescription>{indexError}</AlertDescription>
          </Alert>
        )}
        <div className="action-row">
          {canEditPaper && (
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

  const versions = versionsQ.data || [];
  const repoSummary = summarizeRepos(paper.repositories);
  const sortedRepos = [...(paper.repositories ?? [])].sort((a, b) => {
    const aOff = a.is_official ? 1 : 0;
    const bOff = b.is_official ? 1 : 0;
    if (aOff !== bOff) return bOff - aOff;
    return (b.num_stars || 0) - (a.num_stars || 0);
  });
  const visibleRepos = reposExpanded ? sortedRepos : sortedRepos.slice(0, REPO_PREVIEW_LIMIT);
  const hfArtifactViewer = paper.arxiv_id
    ? {
        isLoading: hfLoading,
        paperHref: `https://huggingface.co/papers/${paper.arxiv_id.replace(/v\d+$/, "")}`,
        rows: [
          {
            label: "Models",
            href: `https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`,
            count: hfRepos?.models,
            isLimited: hfRepos?.isLimited,
          },
          {
            label: "Datasets",
            href: `https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`,
            count: hfRepos?.datasets,
            isLimited: hfRepos?.isLimited,
          },
          {
            label: "Spaces",
            href: `https://huggingface.co/spaces?other=arxiv:${paper.arxiv_id}`,
            count: hfRepos?.spaces,
            isLimited: hfRepos?.isLimited,
          },
        ],
        footer: `Cite arxiv.org/abs/${paper.arxiv_id} in a HF README to link it here.`,
      }
    : {
        isLoading: false,
        paperHref: null,
        rows: [
          {
            label: "Models",
            href: hfArtifactGroupHref(explicitHfArtifacts.models),
            count: explicitHfArtifacts.models.length,
          },
          {
            label: "Datasets",
            href: hfArtifactGroupHref(explicitHfArtifacts.datasets),
            count: explicitHfArtifacts.datasets.length,
          },
          {
            label: "Spaces",
            href: hfArtifactGroupHref(explicitHfArtifacts.spaces),
            count: explicitHfArtifacts.spaces.length,
          },
        ],
        footer: null,
      };
  const tldr = (paper as Paper & { tldr?: string }).tldr || null;
  const numPages = (paper as Paper & { num_pages?: number }).num_pages || null;
  const abstract = paper.abstract || "";
  const abstractShort = abstract.length > ABSTRACT_PREVIEW_LEN ? abstract.slice(0, ABSTRACT_PREVIEW_LEN) + "…" : abstract;
  const abstractView = abstractExpanded || abstract.length <= ABSTRACT_PREVIEW_LEN ? abstract : abstractShort;
  const introducedMethods = (paper.methods || []).filter((method) => method.source_paper_id === paper.id);
  const introducedBenchmarks = paper.introduced_benchmarks || [];
  const hasIntroducedItems = introducedMethods.length > 0 || introducedBenchmarks.length > 0;
  const paperSourceLabel = paper.arxiv_id ? `arXiv:${paper.arxiv_id}` : "External resource";
  const sourceActionLabel = paper.source === "external" ? "Source page" : "arXiv page";
  const projectPages = paper.project_pages?.filter((page) => page.url) ?? [];
  const introducedSummary = (() => {
    const parts: string[] = [];
    if (introducedMethods.length > 0) {
      parts.push(introducedMethods.length === 1 ? "this method" : "these methods");
    }
    if (introducedBenchmarks.length > 0) {
      parts.push(introducedBenchmarks.length === 1 ? "this benchmark" : "these benchmarks");
    }
    if (parts.length === 0) return "";
    if (parts.length === 1) return parts[0];
    return parts.join(" and ");
  })();

  const AUTHOR_LIMIT = 12;
  const visibleAuthors =
    showAllAuthors || paper.authors.length <= AUTHOR_LIMIT ? paper.authors : paper.authors.slice(0, AUTHOR_LIMIT);

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Trending</Link>
        <span className="sep">/</span>
        <span>{paperSourceLabel}</span>
      </div>

      <div className="detail-grid">
        <div>
          <h1 className="detail-title">
            <LatexTitle title={paper.title} />
          </h1>
          <div className="detail-meta">
            <span>{paperSourceLabel}</span>
            <span>·</span>
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
            {paper.proceeding && (
              <>
                <span>·</span>
                <span>{paper.proceeding.replace(/\s+\d{1,2}$/, "")}</span>
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
                <a>{a}</a>
                {i < visibleAuthors.length - 1 ? ", " : ""}
              </React.Fragment>
            ))}
            {paper.authors.length > AUTHOR_LIMIT && (
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
                {showAllAuthors ? "show fewer" : `+${paper.authors.length - AUTHOR_LIMIT} more`}
              </button>
            )}
          </div>

          <div className="action-row">
            {paper.url_pdf && (
              <a className="action-btn" href={paper.url_pdf} target="_blank" rel="noopener noreferrer">
                <Icon name="pdf" size={12} /> View PDF
              </a>
            )}
            {paper.url_abs && (
              <a className="action-btn" href={paper.url_abs} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> {sourceActionLabel}
              </a>
            )}
            {repoSummary.githubUrl && (
              <a className="action-btn" href={repoSummary.githubUrl} target="_blank" rel="noopener noreferrer">
                <Icon name="github" size={12} /> Code
                {repoSummary.github != null && (
                  <span style={{ opacity: 0.7, marginLeft: 4 }}>· {formatStars(repoSummary.github)} ★</span>
                )}
              </a>
            )}
            {projectPages.map((page, index) => (
              <span key={page.url} className="project-page-action">
                <a
                  className="action-btn project-page-link"
                  href={page.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="globe" size={12} /> {formatProjectPageLabel(page.url, projectPages.length, index)}
                </a>
                {canEditPaper && (
                  <button
                    type="button"
                    className="action-btn project-page-edit"
                    onClick={() => setIsEditingProjectPages(true)}
                    title="Edit project pages"
                    aria-label="Edit project pages"
                  >
                    edit
                  </button>
                )}
              </span>
            ))}
            {canEditPaper && projectPages.length === 0 ? (
              <button
                type="button"
                className="action-btn"
                onClick={() => setIsEditingProjectPages(true)}
                title="Add project page"
              >
                <Icon name="globe" size={12} /> Add project page
              </button>
            ) : null}
            {paper.conference_url_abs && (
              <a className="action-btn" href={paper.conference_url_abs} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> Conference
              </a>
            )}
            <SavePaperButton paperId={paper.id} />
          </div>

          {hasIntroducedItems && (
            <div className="introduced-banner">
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
              </div>
              <span className="introduced-note">
                This paper is the canonical source for {introducedSummary}.
              </span>
            </div>
          )}

          {tldr && (
            <>
              <div className="section-rule">
                <span>TL;DR · AI-generated</span>
              </div>
              <div className="tldr-box">{tldr}</div>
            </>
          )}

          <div className="section-rule">
            <span>Abstract</span>
          </div>
          <p className="abstract-text" style={{ marginBottom: 8 }}>
            <LatexText text={abstractView} />
          </p>
          {abstract.length > ABSTRACT_PREVIEW_LEN && (
            <div className="read-full" onClick={() => setAbstractExpanded((v) => !v)}>
              {abstractExpanded ? "− collapse abstract" : "+ read full abstract"}
            </div>
          )}

          <div className="section-rule">
            <span>Tasks</span>
            <span className="accent">
              {paper.tasks?.length || 0} tagged
              {canEditPaper && (
                <button
                  onClick={() => setIsEditingTasks(true)}
                  className="edit-link"
                  style={{
                    marginLeft: 8,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--accent-text)",
                    textDecoration: "underline",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                  }}
                >
                  edit
                </button>
              )}
            </span>
          </div>
          <div className="paper-tags" style={{ marginBottom: 8 }}>
            {(paper.tasks || []).map((t) => (
              <TagChip key={t.id} slug={t.slug || ""} label={t.name} />
            ))}
          </div>

          <div className="section-rule">
            <span>Methods</span>
            <span className="accent">
              {paper.methods?.length || 0} used
              {canEditPaper && (
                <button
                  onClick={() => setIsEditingMethods(true)}
                  className="edit-link"
                  style={{
                    marginLeft: 8,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--accent-text)",
                    textDecoration: "underline",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                  }}
                >
                  edit
                </button>
              )}
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {(paper.methods || []).map((m) => (
              <MethodChip key={m.id} method={m} />
            ))}
          </div>

          <div className="section-rule">
            <span>Results</span>
            <span className="accent">
              {evaluations?.length || 0} benchmarks
              {canEditPaper && (
                <button
                  onClick={() => setIsEditingEvaluations(true)}
                  className="edit-link"
                  style={{
                    marginLeft: 8,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--accent-text)",
                    textDecoration: "underline",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                  }}
                >
                  edit
                </button>
              )}
            </span>
          </div>
          {evaluationsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : evaluationsByTask.length > 0 ? (
            evaluationsByTask.map((group) => (
              <div key={group.taskId}>
                <div className="section-rule">
                  <span>
                    {group.taskSlug ? (
                      <Link to={`/tasks/${group.taskSlug}`}>{group.taskName}</Link>
                    ) : (
                      group.taskName
                    )}
                  </span>
                  <span className="accent">
                    {group.rows.length} {group.rows.length === 1 ? "result" : "results"}
                  </span>
                </div>
                <table className="results-table">
                  <colgroup>
                    <col style={{ width: "30%" }} />
                    <col style={{ width: "30%" }} />
                    <col style={{ width: "15%" }} />
                    <col style={{ width: "15%" }} />
                    <col style={{ width: "10%" }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Benchmark</th>
                      <th>Model</th>
                      <th>Metric</th>
                      <th>Value</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((e) => (
                      <tr key={e.id}>
                        <td className="benchmark">
                          {e.dataset_slug ? (
                            <Link to={`/benchmark/${e.dataset_slug}`}>{e.dataset_name || "—"}</Link>
                          ) : (
                            e.dataset_name || "—"
                          )}
                        </td>
                        <td className="model" title={e.model_name || undefined}>
                          {e.model_name || "—"}
                        </td>
                        <td className="metric">{e.best_metric}</td>
                        <td className="value">{formatMetricValue(e.metrics?.[e.best_metric || ""])}</td>
                        <td className="compare">
                          {e.dataset_slug && (
                            <Link to={`/benchmark/${e.dataset_slug}?eval=${encodeURIComponent(e.id)}`}>Compare →</Link>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          ) : (
            <p style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)" }}>No benchmark results recorded yet.</p>
          )}

        </div>

        <aside className="detail-sidebar">
          {(sortedRepos.length > 0 || canEditPaper) && (
            <div className="sidebar-card">
              <div className="sidebar-card-title">
                <span>GitHub</span>
                <span className="badge">
                  {sortedRepos.length} repo{sortedRepos.length === 1 ? "" : "s"}
                  {canEditPaper && (
                    <button
                      onClick={() => setIsEditingRepositories(true)}
                      className="edit-link"
                      style={{
                        marginLeft: 8,
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "var(--accent-text)",
                        textDecoration: "underline",
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                      }}
                    >
                      edit
                    </button>
                  )}
                </span>
              </div>
              {visibleRepos.map((r) => (
                <a
                  key={r.id}
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="code-line"
                  style={{ textDecoration: "none" }}
                >
                  <span className="code-line-repo">
                    <Icon name="github" size={12} />
                    <span className="code-line-repo-name">
                      {r.owner}/{r.name}
                    </span>
                    {r.is_official && (
                      <span className="code-line-official">· Official</span>
                    )}
                  </span>
                  <span className="code-line-stars">★ {formatStars(r.num_stars)}</span>
                </a>
              ))}
              {sortedRepos.length === 0 && canEditPaper && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    padding: "6px 0",
                  }}
                >
                  No GitHub repositories linked yet.
                </div>
              )}
              {sortedRepos.length > REPO_PREVIEW_LIMIT && (
                <button
                  type="button"
                  className="bench-show-more"
                  onClick={() => setReposExpanded((v) => !v)}
                >
                  {reposExpanded
                    ? "− show top 3"
                    : `+ show ${sortedRepos.length - REPO_PREVIEW_LIMIT} more repos`}
                </button>
              )}
            </div>
          )}

          {/* Hugging Face block */}
          <HuggingFaceArtifactsCard viewer={hfArtifactViewer} />

          <div className="sidebar-card">
            <div className="sidebar-card-title">Citation</div>
            <pre
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10.5,
                lineHeight: 1.5,
                color: "var(--ink-soft)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
              }}
            >
{paper.arxiv_id ? `@article{${paper.arxiv_id.replace(".", "")},
  title={{${paper.title.slice(0, 60)}${paper.title.length > 60 ? "…" : ""}}},
  author={{${paper.authors[0] || ""}${paper.authors.length > 1 ? " et al." : ""}}},
  year={{${(paper.published || "").slice(0, 4) || "—"}}},
  eprint={{${paper.arxiv_id}}},
  archivePrefix={{arXiv}}
}` : `@misc{paper${paper.id},
  title={{${paper.title.slice(0, 60)}${paper.title.length > 60 ? "…" : ""}}},
  author={{${paper.authors[0] || ""}${paper.authors.length > 1 ? " et al." : ""}}},
  year={{${(paper.published || "").slice(0, 4) || "—"}}},
  url={{${paper.source_url || paper.url_abs || ""}}}
}`}
            </pre>
          </div>

          {(relatedQ.data?.length ?? 0) > 0 && (
            <div className="sidebar-card">
              <div className="sidebar-card-title">Related papers</div>
              {relatedQ.data!.map((p) => (
                <Link
                  key={p.id}
                  to={`/paper/${p.arxiv_id || p.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="related-paper"
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <div className="related-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="related-meta">
                    <span>{p.arxiv_id ? `arXiv:${p.arxiv_id}` : "External resource"}</span>
                    {p.citation_count != null && (
                      <span>{p.citation_count.toLocaleString()} cites</span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </aside>
      </div>

      {/* Admin dialogs */}
      <EditTasksDialog
        open={isEditingTasks}
        onOpenChange={setIsEditingTasks}
        paperId={paper.id}
        arxivId={arxivId}
        initialTaskIds={paper.tasks?.map((t) => parseInt(t.id)) || []}
        initialTasks={paper.tasks || []}
      />
      <EditMethodsDialog
        open={isEditingMethods}
        onOpenChange={setIsEditingMethods}
        paperId={paper.id}
        arxivId={arxivId}
        initialMethodIds={paper.methods?.map((m) => parseInt(m.id)) || []}
        initialMethods={paper.methods || []}
      />
      <EditRepositoriesDialog
        open={isEditingRepositories}
        onOpenChange={setIsEditingRepositories}
        paperId={paper.id}
        arxivId={arxivId}
        initialRepositories={
          paper.repositories?.map((r) => ({ url: r.url, is_official: r.is_official || false })) || []
        }
      />
      <EditProjectPagesDialog
        open={isEditingProjectPages}
        onOpenChange={setIsEditingProjectPages}
        paperId={paper.id}
        arxivId={arxivId}
        initialProjectPages={
          paper.project_pages?.map((p) => ({ url: p.url, is_official: p.is_official || false })) || []
        }
      />
      <EditEvaluationsDialog
        open={isEditingEvaluations}
        onOpenChange={setIsEditingEvaluations}
        paperId={paper.id}
        arxivId={arxivId}
        initialEvaluations={evaluations || []}
      />
    </div>
  );
};

interface HfRowProps {
  label: string;
  href: string;
  count: number | undefined;
  isLimited?: boolean;
}

interface HuggingFaceArtifactsViewer {
  isLoading: boolean;
  paperHref: string | null;
  rows: HfRowProps[];
  footer: string | null;
}

const HuggingFaceArtifactsCard: React.FC<{ viewer: HuggingFaceArtifactsViewer }> = ({ viewer }) => (
  <div className="sidebar-card">
    <div className="sidebar-card-title">
      {viewer.paperHref ? (
        <a
          href={viewer.paperHref}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "inherit", textDecoration: "none" }}
        >
          🤗 Hugging Face
        </a>
      ) : (
        <span>🤗 Hugging Face</span>
      )}
    </div>
    {viewer.isLoading ? (
      <Skeleton className="h-16 w-full" />
    ) : (
      <>
        {viewer.rows.map((row) => (
          <HfRow key={row.label} {...row} />
        ))}
        {viewer.footer && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-faint)", marginTop: 12 }}>
            {viewer.footer}
          </div>
        )}
      </>
    )}
  </div>
);

const HfRow: React.FC<HfRowProps> = ({ label, href, count, isLimited }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "6px 0",
      borderBottom: "1px dashed var(--hairline)",
      fontFamily: "var(--mono)",
      fontSize: 11,
      color: "var(--ink-soft)",
      textDecoration: "none",
    }}
  >
    <span>{label}</span>
    <span style={{ fontWeight: 600, color: count ? "var(--ink)" : "var(--ink-faint)" }}>
      {count != null ? `${count}${isLimited ? "+" : ""}` : "—"}
    </span>
  </a>
);

function hfArtifactGroupHref(urls: string[]): string {
  return urls[0] ?? "https://huggingface.co";
}

export default PaperDetailView;
