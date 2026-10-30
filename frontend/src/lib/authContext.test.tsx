import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authApi, type AuthUser } from "./api/auth";
import { AuthProvider, useAuth } from "./authContext";

const alice: AuthUser = {
  hf_subject: "alice-id",
  username: "alice",
  name: "Alice",
  avatar_url: null,
  is_admin: false,
  role: null,
  can_contribute: false,
  can_directly_edit_catalog: false,
};

function Probe() {
  const { user, isLoading, logout } = useAuth();
  const bookmarks = useQuery({ queryKey: ["my-bookmark-ids"], queryFn: () => Promise.resolve(user ? "alice's" : "none"), enabled: !isLoading });
  return <>
    <output data-testid="user">{isLoading ? "loading" : user?.username ?? "guest"}</output>
    <output data-testid="bookmarks">{bookmarks.data}</output>
    <button type="button" onClick={() => void logout()}>Sign out</button>
  </>;
}

function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider><Probe /></AuthProvider></QueryClientProvider>);
  return client;
}

afterEach(() => vi.restoreAllMocks());

describe("AuthProvider", () => {
  it("drops the signed-out user's cached data on logout without refetching the session", async () => {
    const me = vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(alice);
    const logout = vi.spyOn(authApi, "logout").mockResolvedValue();
    renderAuth();
    expect(screen.getByTestId("user")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("alice"));
    await waitFor(() => expect(screen.getByTestId("bookmarks")).toHaveTextContent("alice's"));

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("guest"));
    await waitFor(() => expect(screen.getByTestId("bookmarks")).toHaveTextContent("none"));
    expect(logout).toHaveBeenCalledOnce();
    expect(me).toHaveBeenCalledOnce();
  });

  it("signs out when the API reports a stale session", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(alice);
    renderAuth();
    expect(await screen.findByText("alice")).toBeInTheDocument();

    act(() => {
      window.dispatchEvent(new CustomEvent("pwc:auth-stale"));
    });

    await waitFor(() => expect(screen.getByTestId("user")).toHaveTextContent("guest"));
  });
});
