import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperCard } from "@/components";
import MarkdownText from "@/components/MarkdownText";
import { OrganizationContributionGraph } from "@/components/OrganizationContributionGraph";
import { PaperFeedFilters } from "@/components/PaperFeedFilters";
import { PaperDateFilter } from "@/components/PaperDateFilter";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  SearchableSelect,
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { Skeleton } from "@/components/ui/skeleton";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { useInfiniteOrganizationPapers } from "@/hooks/usePapers";
import { catalogApi } from "@/lib/api/catalog";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import NotFound from "@/pages/NotFound";
import { readPaperDateRange, withPaperDateRange } from "@/lib/paperDateRange";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const parseOrderBy = (value: string | null): OrderBy =>
  value === "date_published" || value === "citation_count" ? value : "trending";

export const OrganizationPaperFeed: React.FC<{
  organizationSlug: string;
  taskSlug?: string;
}> = ({ organizationSlug, taskSlug }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [logoFailed, setLogoFailed] = useState(false);
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const hasCode = searchParams.get("has_code") === "true";
  const hasHfArtifacts = searchParams.get("has_hf_artifacts") === "true";
  const dateRange = readPaperDateRange(searchParams);
  const organizationQ = useQuery({
    queryKey: ["organization", organizationSlug],
    queryFn: () => catalogApi.getOrganization(organizationSlug),
    staleTime: 10 * 60 * 1000,
  });
  const taxonomyQ = useQuery({
    queryKey: ["organization-areas-with-tasks", organizationSlug],
    queryFn: () => catalogApi.organizationAreasWithTasks(organizationSlug),
    staleTime: 10 * 60 * 1000,
  });
  const papersQ = useInfiniteOrganizationPapers({
    organizationSlug,
    taskSlug,
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    has_code: hasCode,
    has_hf_artifacts: hasHfArtifacts,
    start_date: dateRange.startDate,
    end_date: dateRange.endDate,
    enabled: !!organizationSlug,
  });
  const { targetRef, isIntersecting } = useIntersectionObserver({
    rootMargin: "200px",
  });

  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setLogoFailed(false);
  }, [organizationSlug, taskSlug]);

  const tasks = useMemo(
    () =>
      (taxonomyQ.data?.results ?? []).flatMap((area) =>
        area.tasks.filter((task) => !!task.slug).map((task) => ({
          ...task,
          slug: task.slug!,
          label: displayTaskName(task.name, task.slug),
        })),
      ),
    [taxonomyQ.data],
  );
  const activeTask = tasks.find((task) => task.slug === taskSlug);
  const cards = useMemo(
    () =>
      (papersQ.data?.pages ?? []).flatMap((page) =>
        page.results.map(transformPaperForCard),
      ),
    [papersQ.data],
  );
  const organization = organizationQ.data ?? taxonomyQ.data?.organization;
  const totalCount = papersQ.data?.pages[0]?.count ?? 0;

  if (
    (organizationQ.error as { status?: number } | null)?.status === 404 ||
    (taxonomyQ.error as { status?: number } | null)?.status === 404 ||
    (papersQ.error as { status?: number } | null)?.status === 404
  ) {
    return <NotFound />;
  }
  if (taxonomyQ.error || papersQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load organization papers. Please try again.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const taskOptions = (query: string): SearchableSelectOption[] => {
    const needle = query.trim().toLocaleLowerCase();
    return tasks
      .filter((task) =>
        `${task.label} ${task.slug}`.toLocaleLowerCase().includes(needle),
      )
      .map((task) => ({
        value: task.slug,
        label: task.label,
        description: `${task.paper_count.toLocaleString()} ${
          task.paper_count === 1 ? "paper" : "papers"
        }`,
      }));
  };

  const selectTask = (value: string) => {
    const pathname =
      value === "__all__"
        ? `/orgs/${organizationSlug}`
        : `/orgs/${organizationSlug}/${value}`;
    const search = searchParams.toString();
    navigate({ pathname, search: search ? `?${search}` : "" });
  };

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <Link to="/organizations">Organizations</Link>
        <span> / </span>
        <span>{organization?.name ?? organizationSlug}</span>
        {activeTask && (
          <>
            <span> / </span>
            <span>{displayTaskName(activeTask.name, activeTask.slug)}</span>
          </>
        )}
      </nav>

      <header className="organization-hero">
        <div className="organization-hero-profile">
          <div className="organizations-eyebrow">ORGANIZATION</div>
          <h1 className="feed-title organization-hero-title">
            {organization?.logo_url && !logoFailed ? (
              <img
                src={organization.logo_url}
                alt=""
                width={58}
                height={58}
                onError={() => setLogoFailed(true)}
              />
            ) : organization ? (
              <span
                className="organization-logo organization-logo--fallback"
                aria-hidden="true"
              >
                {organization.name.slice(0, 1).toUpperCase()}
              </span>
            ) : null}
            {organization?.name ?? <Skeleton className="h-12 w-64" />}
          </h1>
          {organization && (
            <div className="feed-subtitle">
              {organization.paper_count?.toLocaleString() ?? 0} papers
              {(organization.organization_trending_score ?? 0) > 0 &&
                organization.trending_rank && (
                  <> · #{organization.trending_rank} trending this month</>
                )}
            </div>
          )}
          {organization?.description && (
            <MarkdownText
              className="method-description"
              text={organization.description}
            />
          )}
          {organization && (
            <div className="organization-hero-links">
              {organization.website_url && (
                <a
                  href={organization.website_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Website ↗
                </a>
              )}
              {organization.hf_url && (
                <a href={organization.hf_url} target="_blank" rel="noreferrer">
                  Hugging Face ↗
                </a>
              )}
              {organization.github_url && (
                <a
                  href={organization.github_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub ↗
                </a>
              )}
            </div>
          )}
        </div>
        <OrganizationContributionGraph
          organizationSlug={organizationSlug}
          organizationName={organization?.name ?? organizationSlug}
        />
      </header>

      <div className="sort-bar" style={{ alignItems: "center", gap: 16 }}>
        <div style={{ minWidth: 260 }}>
          <SearchableSelect
            value={taskSlug ?? "__all__"}
            onChange={selectTask}
            placeholder="All tasks"
            searchPlaceholder="Search organization tasks..."
            emptyMessage="No matching tasks."
            ariaLabel="Filter papers by task"
            selectedOption={
              activeTask
                ? {
                    value: activeTask.slug,
                    label: activeTask.label,
                    description: `${activeTask.paper_count.toLocaleString()} ${
                      activeTask.paper_count === 1 ? "paper" : "papers"
                    }`,
                  }
                : {
                    value: "__all__",
                    label: "All tasks",
                    description: `${organization?.paper_count?.toLocaleString() ?? 0} papers`,
                  }
            }
            queryKey={["organization-task-options", organizationSlug]}
            queryFn={async (query) => [
              {
                value: "__all__",
                label: "All tasks",
                description: `${organization?.paper_count?.toLocaleString() ?? 0} papers`,
              },
              ...taskOptions(query),
            ]}
            enabled={!taxonomyQ.isLoading}
            className="h-[38px]"
          />
        </div>
        <div className="paper-feed-toolbar-controls">
          <div className="sort-options">
            {SORT_OPTIONS.map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={`sort-btn ${orderBy === value ? "active" : ""}`}
                onClick={() => {
                  const updated = new URLSearchParams(searchParams);
                  if (value === "trending") updated.delete("order_by");
                  else updated.set("order_by", value);
                  setSearchParams(updated);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <PaperFeedFilters
            hasCode={hasCode}
            hasHfArtifacts={hasHfArtifacts}
            onHasCodeChange={(active) => {
              const updated = new URLSearchParams(searchParams);
              if (active) updated.set("has_code", "true");
              else updated.delete("has_code");
              setSearchParams(updated);
            }}
            onHasHfArtifactsChange={(active) => {
              const updated = new URLSearchParams(searchParams);
              if (active) updated.set("has_hf_artifacts", "true");
              else updated.delete("has_hf_artifacts");
              setSearchParams(updated);
            }}
          />
        </div>
        <PaperDateFilter
          startDate={dateRange.startDate}
          endDate={dateRange.endDate}
          onChange={(value) => setSearchParams(withPaperDateRange(searchParams, value))}
        />
        <div className="results-count">{totalCount.toLocaleString()} papers</div>
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">
          {organization?.paper_count === 0
            ? "No papers indexed yet"
            : "No papers found for this selection."}
        </div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((paper, index) => (
              <PaperCard
                key={paper.id}
                paper={paper}
                rank={index + 1}
                showInstitution={false}
              />
            ))}
          </div>
          <div ref={targetRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center" }}>
              Loading more…
            </div>
          )}
        </>
      )}
    </div>
  );
};
