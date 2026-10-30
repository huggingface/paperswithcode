/** Stable cache families shared by paper readers and mutation reconciliation. */
export const paperQueryKeys = {
  detail: (id: string | undefined) => ["paper", id] as const,
  arxiv: (id: string | undefined) => ["paper-arxiv", id] as const,
  preview: (id: string) => ["paper-preview", id] as const,
  summary: (id: string) => ["paper-summary", id] as const,
  feeds: {
    list: ["papers"],
    infinite: ["papers-infinite"],
    xTrending: ["x-trending-papers-infinite"],
    following: ["research-feed"],
    search: ["paper-search-feed"],
    task: ["task-papers-infinite"],
    conference: ["conference-papers-infinite"],
    organization: ["organization-papers-infinite"],
    method: ["method-papers-infinite"],
    saved: ["my-bookmarks"],
    related: ["related-papers"],
    versions: ["paper-versions"],
    searchOverlay: ["search-papers"],
    mentions: ["chat-paper-mention-search"],
    trending: ["trending-papers"],
  },
} as const;
