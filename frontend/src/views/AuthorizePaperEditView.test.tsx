import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuth } from "@/lib/authContext";
import { paperEditsApi } from "@/lib/api/paperEdits";
import AuthorizePaperEditView from "./AuthorizePaperEditView";

vi.mock("@/lib/authContext", () => ({ useAuth: vi.fn() }));
vi.mock("@/lib/api/paperEdits", () => ({ paperEditsApi: { authorization: vi.fn(), approve: vi.fn() } }));
vi.mock("@/components/HfSignInButton", () => ({ default: () => <button>Sign in with Hugging Face</button> }));

function view() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/authorize-paper-edit/grant"]}><Routes>
    <Route path="/authorize-paper-edit/:authorizationId" element={<AuthorizePaperEditView />} />
  </Routes></MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ user: { hf_subject: "alice-id", username: "alice", name: "Alice", avatar_url: null, is_admin: false, role: null, can_contribute: false, can_directly_edit_catalog: true }, isLoading: false, refresh: vi.fn(), logout: vi.fn() });
  vi.mocked(paperEditsApi.authorization).mockResolvedValue({ paper_id: 123, title: "Example paper", user_code: "ABCD1234", approved: false, expires_at: "2026-09-16T12:00:00Z" });
  vi.mocked(paperEditsApi.approve).mockResolvedValue({ status: "approved", expires_at: "2026-09-16T12:00:00Z" });
});

describe("paper edit authorization", () => {
  it("discloses paper, code, immediate publication, and attribution before explicit approval", async () => {
    view();
    const button = await screen.findByRole("button", { name: "Authorize for one hour" });
    expect(screen.getByText("Example paper")).toBeTruthy();
    expect(screen.getByText("ABCD1234")).toBeTruthy();
    expect(screen.getByText(/without further approval/)).toBeTruthy();
    expect(screen.getByText(/publicly under your Hugging Face username/)).toBeTruthy();
    expect(paperEditsApi.approve).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(await screen.findByRole("status")).toHaveTextContent("Access approved");
    expect(paperEditsApi.approve).toHaveBeenCalledWith("grant");
  });

  it("requires browser sign-in", async () => {
    vi.mocked(useAuth).mockReturnValue({ user: null, isLoading: false, refresh: vi.fn(), logout: vi.fn() });
    view();
    expect(await screen.findByRole("button", { name: "Sign in with Hugging Face" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Authorize for one hour" })).toBeNull();
    expect(paperEditsApi.approve).not.toHaveBeenCalled();
  });
});
