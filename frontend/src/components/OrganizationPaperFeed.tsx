import ResearchFollowButton from "@/components/ResearchFollowButton";
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import MarkdownText from "@/components/MarkdownText";
import { OrganizationContributionGraph } from "@/components/OrganizationContributionGraph";
import { PaperFeedList, PaperFeedToolbar } from "@/components/PaperFeed";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  SearchableSelect,
  type SearchableSelectOption,
} from "@/components/ui/searchable-select";
import { Skeleton } from "@/components/ui/skeleton";
import { usePaperFeedParams } from "@/hooks/usePaperFeedParams";
import { usePaperFeedQuery } from "@/hooks/usePapers";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isNotFound } from "@/lib/apiErrors";
import { paperQueryKeys } from "@/lib/paperQueryKeys";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { isLongOrganizationName, organizationShortName } from "@/lib/organizationNames";
import NotFound from "@/pages/NotFound";
import { catalogQueryKeys, TEN_MINUTES } from "@/lib/api/queryKeys";

export const OrganizationPaperFeed: React.FC<{
  organizationSlug: string;
  taskSlug?: string;
}> = ({ organizationSlug, taskSlug }) => {
  const navigate = useNavigate();
  const feed = usePaperFeedParams();
  const { searchParams } = feed;
  const [logoFailed, setLogoFailed] = useState(false);
  const organizationQ = useQuery({
    queryKey: catalogQueryKeys.organization(organizationSlug),
    queryFn: () => catalogApi.getOrganization(organizationSlug),
    staleTime: TEN_MINUTES,
  });
  const taxonomyQ = useQuery({
    queryKey: ["organization-areas-with-tasks", organizationSlug],
    queryFn: () => catalogApi.organizationAreasWithTasks(organizationSlug),
    staleTime: TEN_MINUTES,
  });
  const papersQ = usePaperFeedQuery(
    [...paperQueryKeys.feeds.organization, organizationSlug, taskSlug, feed.filters],
    (page) =>
      papersApi.forOrganization(organizationSlug, { ...feed.filters, task: taskSlug, page, page_size: 12 }),
    { enabled: !!organizationSlug },
  );

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
  const shortName = organization ? organizationShortName(organization) : null;
  const totalCount = papersQ.data?.pages[0]?.count ?? 0;

  if ([organizationQ.error, taxonomyQ.error, papersQ.error].some(isNotFound)) {
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
          <h1
            className={`feed-title organization-hero-title${
              organization && !shortName && isLongOrganizationName(organization.name)
                ? " organization-hero-title--long"
                : ""
            }`}
          >
            {organization?.logo_url && !logoFailed ? (
              <img
                src={organization.logo_url}
                alt=""
                width={58}
                height={58}
                onError={() => setLogoFailed(true)}
              />
            ) : organization ? (
              <span className="organization-hero-monogram" aria-hidden="true">
                {(shortName ?? organization.name).slice(0, 1).toUpperCase()}
              </span>
            ) : null}
            {organization ? (
              <span className="organization-hero-name">
                {shortName ?? organization.name}
                {shortName && (
                  <span className="organization-hero-full-name">{organization.name}</span>
                )}
              </span>
            ) : (
              <Skeleton className="h-12 w-64" />
            )}
          </h1>
          {organization && <ResearchFollowButton kind="organization" entityId={organization.id} />}
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

      <PaperFeedToolbar
        feed={feed}
        style={{ alignItems: "center", gap: 16 }}
        leading={
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
        }
      >
        <div className="results-count">{totalCount.toLocaleString()} papers</div>
      </PaperFeedToolbar>

      <PaperFeedList
        query={papersQ}
        cards={cards}
        showInstitution={false}
        empty={
          organization?.paper_count === 0
            ? "No papers indexed yet"
            : "No papers found for this selection."
        }
      />
    </div>
  );
};
