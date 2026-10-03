import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { Paper } from "@/lib/api/papers.types";
import { invalidatePaperDetails, refreshPaperQueries } from "./queryInvalidation";

const updatedPaper = { id: "42", arxiv_id: "2401.00001", title: "Updated title" } as Paper;

// Keep these concrete keys independent of the registry: missing a reader family
// from reconciliation must fail this coverage check.
const feeds = [
  ["papers", { page: 1 }],
  ["papers-infinite", { has_code: true }],
  ["paper-search-feed", { q: "old title" }],
  ["task-papers-infinite", "classification"],
  ["conference-papers-infinite", "cvpr-2026"],
  ["organization-papers-infinite", "example"],
  ["method-papers-infinite", "transformer"],
  ["author-papers", "123"],
  ["my-bookmarks"],
  ["related-papers", "99"],
  ["paper-versions", "2401.00001"],
  ["search-papers", "old title"],
  ["chat-paper-mention-search", "old title"],
  ["trending-papers"],
];

describe("paper mutation reconciliation", () => {
  it.each(feeds.map(key => [key[0], key]))("refreshes %s when revisited, without an immediate request", async (_, queryKey) => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000, retry: false } } });
    const queryFn = vi.fn().mockResolvedValue([updatedPaper]);
    const key = queryKey as readonly unknown[];
    client.setQueryData(key, [{ ...updatedPaper, title: "Before edit" }]);
    const observer = new QueryObserver(client, { queryKey: key, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    refreshPaperQueries(client, updatedPaper, ["42"]);
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    expect(queryFn).not.toHaveBeenCalled();
    unsubscribe();
    const revisited = new QueryObserver(client, { queryKey: key, queryFn });
    const leave = revisited.subscribe(() => {});
    await vi.waitFor(() => expect(revisited.getCurrentResult().data).toEqual([updatedPaper]));
    expect(queryFn).toHaveBeenCalledTimes(1);
    leave();
    client.clear();
  });

  it("reconciles detail aliases and previews without refetching unrelated queries", () => {
    const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000 } } });
    const detailKeys = [["paper", "42"], ["paper", "2401.00001"], ["paper-arxiv", "2401.00001"], ["paper-preview", "2401.00001"], ["paper-summary", "42"]];
    const queryFn = vi.fn();
    const unsubscribes = detailKeys.map(queryKey => {
      client.setQueryData(queryKey, { ...updatedPaper, title: "Before edit" });
      return new QueryObserver(client, { queryKey, queryFn }).subscribe(() => {});
    });
    client.setQueryData(["organizations", "curation"], ["untouched"]);
    client.setQueryData(["paper", "99"], { id: "99" });
    refreshPaperQueries(client, updatedPaper, ["42", "2401.00001"]);
    detailKeys.forEach(key => {
      expect(client.getQueryData(key)).toEqual(updatedPaper);
      expect(client.getQueryState(key)?.isInvalidated).toBe(false);
    });
    expect(client.getQueryState(["organizations", "curation"])?.isInvalidated).toBe(false);
    expect(client.getQueryData(["paper", "99"])).toEqual({ id: "99" });
    expect(queryFn).not.toHaveBeenCalled();
    unsubscribes.forEach(unsubscribe => unsubscribe());
    client.clear();
  });
});

it("invalidates all detail aliases after approval without fetching inactive cards", () => {
  const client = new QueryClient();
  const keys = [["paper", "42"], ["paper", "2401.00001"], ["paper-arxiv", "2401.00001"], ["paper-preview", "2401.00001"], ["paper-summary", "42"]];
  keys.forEach(key => client.setQueryData(key, updatedPaper));
  client.setQueryData(["paper", "99"], { id: "99" });
  invalidatePaperDetails(client, ["42", "2401.00001"]);
  keys.forEach(key => expect(client.getQueryState(key)?.isInvalidated).toBe(true));
  expect(client.getQueryState(["paper", "99"])?.isInvalidated).toBe(false);
  client.clear();
});
