import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "@/lib/authContext";
import StagingAccessRequestView from "./StagingAccessRequestView";

describe("StagingAccessRequestView", () => {
  afterEach(() => vi.restoreAllMocks());

  it("submits the verified Hugging Face identity and discloses email collection", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hf_subject: "hf-subject",
          username: "verified-user",
          name: "Verified User",
          avatar_url: null,
          is_admin: false,
          role: null,
          can_contribute: false,
          can_directly_edit_catalog: false,
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          hf_username: "verified-user",
          status: "pending",
        }),
      } as Response);

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider>
          <StagingAccessRequestView />
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(await screen.findByDisplayValue("verified-user")).toHaveAttribute("readonly");
    expect(screen.getByText(/Username and email verified through Hugging Face/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "https://paperswithcode.co/privacy",
    );
    fireEvent.click(screen.getByRole("button", { name: "Request access" }));

    await screen.findByRole("heading", { name: "Request received" });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      credentials: "include",
    });
  });
});
