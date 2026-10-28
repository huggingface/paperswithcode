import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");
const globalStyles = source("src/styles.css");

describe("global stylesheet contract", () => {
  it("contains only documented cross-feature foundations", () => {
    const allowedClasses = /^(?:dark|app-header(?:-inner)?|site-announcement(?:-close)?|brand(?:-mark|-name)?|nav|nav-item(?:-with-badge)?|nav-indicator(?:-ready)?|nav-new-badge|active|header-spacer|header-bookmark-btn|header-github-btn|header-feedback-link|search-trigger|icon-btn|hf-signin-btn|user-avatar-btn|page|site-footer(?:-inner)?|layout-with-sidebar|sidebar|sidebar-section|sidebar-label|sidebar-links?|sidebar-link-more|count|breadcrumb(?:-external)?|sep|detail-title(?:-org(?:--logo)?|-tail|-edit)?|action-btn|primary|no-results|icon|icon-sm|mobile-menu-btn|mobile-search-btn|mobile-nav-drawer|mobile-nav-panel|mobile-nav-link(?:-with-badge)?|mobile-nav-search|mobile-nav-close)$/;
    const selectors = globalStyles.replace(/@import[^;]+;/g, "");
    const classNames = new Set(
      [...selectors.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((match) => match[1]),
    );
    expect([...classNames].filter((name) => !allowedClasses.test(name))).toEqual([]);
    expect(globalStyles.startsWith("/* Shared foundations only:")).toBe(true);
  });

  it("keeps representative feature selectors with their named owners", () => {
    const owners = {
      "access-request": ".access-request-page",
      home: ".ask-home",
      legal: ".legal-page",
      methods: ".method-hero-grid",
      organizations: ".organization-contributions",
      "paper-list": ".paper-card",
      "saved-papers": ".saved-area-section",
      search: ".search-overlay",
      settings: ".settings-section",
      tasks: ".task-page-grid",
      taxonomy: ".framework-grid",
    };
    for (const [owner, selector] of Object.entries(owners)) {
      expect(source(`src/styles/features/${owner}.css`)).toContain(selector);
      expect(globalStyles).not.toContain(selector);
    }
  });

  it("removes obsolete and duplicate rules found during migration", () => {
    const settings = source("src/styles/features/settings.css");
    expect(globalStyles).not.toMatch(/\.(?:banner|banner-tag|banner-link|section-label)\b/);
    expect(settings.match(/\.settings-billing-help\s*\{/g)).toHaveLength(1);
  });
});
