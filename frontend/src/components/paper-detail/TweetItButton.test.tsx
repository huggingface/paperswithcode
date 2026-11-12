import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { operationsApi, type XPostRequestStatus } from "@/lib/api/operations";
import { TweetItButton } from "./TweetItButton";

afterEach(() => vi.restoreAllMocks());

const status = (extra: Partial<XPostRequestStatus>): XPostRequestStatus => ({
  state: "none", position: null, requested_at: null, post_url: null, ...extra,
});

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TweetItButton paperId={42} />
    </QueryClientProvider>,
  );
  return client;
}

it("queues the paper and shows its place in line, and a second click cancels", async () => {
  vi.spyOn(operationsApi, "getXPostRequest").mockResolvedValue(status({}));
  const set = vi.spyOn(operationsApi, "setXPostRequest")
    .mockResolvedValueOnce(status({ state: "requested", position: 2 }))
    .mockResolvedValueOnce(status({}));
  const client = renderButton();

  const button = await screen.findByRole("button", { name: "Tweet it" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  const queued = await screen.findByRole("button", { name: "Queued #2" });
  expect(queued).toHaveAttribute("title", "2nd in line to post on X. Click to cancel.");
  expect(set).toHaveBeenCalledWith(42, true);

  fireEvent.click(queued);
  expect(await screen.findByRole("button", { name: "Tweet it" })).toBeInTheDocument();
  expect(set).toHaveBeenLastCalledWith(42, false);
  client.clear();
});

it("links to the post once the paper is on X", async () => {
  vi.spyOn(operationsApi, "getXPostRequest").mockResolvedValue(
    status({ state: "posted", post_url: "https://x.com/paperswithcodee/status/1" }),
  );
  const client = renderButton();
  expect(await screen.findByRole("link", { name: "Posted on X" })).toHaveAttribute(
    "href", "https://x.com/paperswithcodee/status/1",
  );
  client.clear();
});
