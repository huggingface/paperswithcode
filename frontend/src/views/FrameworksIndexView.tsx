import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Icon } from "@/components/Icon";
import { catalogApi } from "@/lib/api/catalog";
import type { Framework, FrameworkPlatform } from "@/lib/api/catalog.types";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { PLATFORM_LABELS } from "@/lib/frameworks";

const categoryTitleStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 13,
  fontWeight: 600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "var(--ink)",
  marginBottom: 6,
};

const PlatformChip: React.FC<{ platform: FrameworkPlatform }> = ({ platform }) => {
  const c = chipColors(hueFromSlug(platform));
  return (
    <span
      className="framework-platform-chip"
      style={{
        background: c.bg,
        color: c.text,
      }}
    >
      {PLATFORM_LABELS[platform]}
    </span>
  );
};

export const FrameworkCard: React.FC<{ framework: Framework }> = ({ framework }) => {
  const navigate = useNavigate();
  const papersPath = `/papers?framework=${encodeURIComponent(framework.slug)}`;

  return (
    <article
      id={`framework-${framework.slug}`}
      className="framework-card framework-card-clickable"
      role="link"
      tabIndex={0}
      aria-label={`View papers implemented by ${framework.name}`}
      onClick={(event) => {
        if ((event.target as Element).closest("a, button")) return;
        navigate(papersPath);
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          navigate(papersPath);
        }
      }}
    >
      <div className="framework-card-head">
        <div>
          <h3 className="framework-card-name">{framework.name}</h3>
          {framework.organization_name && (
            <div className="framework-card-org">{framework.organization_name}</div>
          )}
        </div>
        {framework.platforms && framework.platforms.length > 0 && (
          <div className="framework-platform-row">
            {framework.platforms.map((platform) => (
              <PlatformChip key={platform} platform={platform} />
            ))}
          </div>
        )}
      </div>

      <p className="framework-card-desc">{framework.description}</p>

      {framework.when_to_use && (
        <div className="framework-card-when">
          <span className="framework-card-when-label">When to use</span>
          {framework.when_to_use}
        </div>
      )}

      {(framework.github_url ||
        framework.docs_url ||
        framework.introducing_paper_arxiv_id) && (
        <div className="framework-card-links">
          {framework.introducing_paper_arxiv_id && (
            <Link
              to={`/paper/${framework.introducing_paper_arxiv_id}`}
              className="framework-link"
            >
              Introducing paper
            </Link>
          )}
          {framework.github_url && framework.paper_count > 0 && (
            <Link
              to={papersPath}
              className="framework-link"
            >
              Implements {framework.paper_count} {framework.paper_count === 1 ? "paper" : "papers"}
            </Link>
          )}
          {framework.github_url && framework.paper_count === 0 && (
            <span
              className="framework-link framework-link-disabled"
              aria-disabled="true"
            >
              Implements 0 papers
            </span>
          )}
          {framework.github_url && (
            <a
              href={framework.github_url}
              target="_blank"
              rel="noopener noreferrer"
              className="framework-link"
            >
              <Icon name="github" size={13} />
              GitHub
            </a>
          )}
          {framework.docs_url && framework.docs_url !== framework.github_url && (
            <a
              href={framework.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="framework-link"
            >
              Docs
            </a>
          )}
        </div>
      )}
    </article>
  );
};

const FrameworksIndexView: React.FC = () => {
  const catalogQuery = useQuery({
    queryKey: ["framework-catalog"],
    queryFn: () => catalogApi.frameworkCatalog(),
  });
  const domains = catalogQuery.data?.domains ?? [];
  const totalFrameworks = domains.reduce(
    (sum, domain) =>
      sum + domain.categories.reduce((catSum, category) => catSum + category.frameworks.length, 0),
    0,
  );

  React.useEffect(() => {
    const frameworkId = window.location.hash.slice(1);
    if (frameworkId) {
      document.getElementById(frameworkId)?.scrollIntoView();
    }
  }, [catalogQuery.data]);

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            AI <em>Frameworks</em>
          </h1>
          <div className="feed-subtitle">
            Curated libraries and tools to run, serve, and train models — pick the right stack for
            your hardware and workload.
          </div>
        </div>
      </div>

      {catalogQuery.isLoading && <div className="empty">Loading frameworks…</div>}
      {catalogQuery.isError && <div className="empty">Could not load frameworks.</div>}

      {domains.map((domain) => (
        <section key={domain.slug} style={{ marginBottom: 56 }}>
          <div className="area-section-head">
            <div>
              <h2 className="area-section-title">{domain.name}</h2>
              <div className="area-section-description">{domain.description}</div>
            </div>
            <div className="area-section-meta">
              {domain.categories.length}{" "}
              {domain.categories.length === 1 ? "category" : "categories"} ·{" "}
              {domain.categories.reduce((s, c) => s + c.frameworks.length, 0)} frameworks
            </div>
          </div>

          {domain.categories.map((category) => (
            <div key={category.slug} className="framework-category">
              <div className="framework-category-head">
                <div>
                  <h3 style={categoryTitleStyle}>{category.name}</h3>
                  {category.description && (
                    <p className="framework-category-blurb">{category.description}</p>
                  )}
                  {category.guide_url && (
                    <a
                      href={category.guide_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="framework-guide-link"
                    >
                      {category.guide_label ?? "Read guide"} →
                    </a>
                  )}
                </div>
                <div className="framework-category-meta">
                  {category.frameworks.length}{" "}
                  {category.frameworks.length === 1 ? "framework" : "frameworks"}
                </div>
              </div>

              <div className="framework-grid">
                {category.frameworks.map((framework) => (
                  <FrameworkCard key={framework.slug} framework={framework} />
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}

      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--ink-faint)",
          marginTop: 8,
        }}
      >
        {totalFrameworks} frameworks across {domains.length}{" "}
        {domains.length === 1 ? "domain" : "domains"}. More areas coming soon.
      </div>
    </div>
  );
};

export default FrameworksIndexView;
