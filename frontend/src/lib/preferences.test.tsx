import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { accountApi } from "./api/account";
import { usePreferences } from "./preferences";

const auth = vi.hoisted(() => ({ user: { hf_subject: "alice-id" } as { hf_subject: string } | null }));
vi.mock("./authContext", () => ({ useAuth: () => auth }));

function Toggle() {
  const { preferences, setHideClosedSourceEvals } = usePreferences();
  return <input
    type="checkbox"
    aria-label="Hide closed-source"
    checked={preferences.hide_closed_source_evals}
    onChange={(event) => setHideClosedSourceEvals(event.target.checked)}
  />;
}

function renderToggle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><Toggle /></QueryClientProvider>);
}

afterEach(() => {
  vi.restoreAllMocks();
  auth.user = { hf_subject: "alice-id" };
});

describe("usePreferences", () => {
  it("applies a change at once and rolls it back when saving fails", async () => {
    vi.spyOn(accountApi, "getPreferences").mockResolvedValue({ hide_closed_source_evals: false });
    let fail = (_error: Error) => {};
    const update = vi.spyOn(accountApi, "updatePreferences").mockReturnValue(
      new Promise((_, reject) => { fail = reject; }),
    );
    renderToggle();
    const toggle = await screen.findByRole("checkbox", { name: "Hide closed-source" });
    await waitFor(() => expect(toggle).toBeEnabled());

    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    expect(update).toHaveBeenCalledWith({ hide_closed_source_evals: true });

    fail(new Error("offline"));
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it("keeps a guest's change locally without saving it", async () => {
    auth.user = null;
    const get = vi.spyOn(accountApi, "getPreferences");
    const update = vi.spyOn(accountApi, "updatePreferences");
    renderToggle();
    const toggle = screen.getByRole("checkbox", { name: "Hide closed-source" });

    fireEvent.click(toggle);

    await waitFor(() => expect(toggle).toBeChecked());
    expect(get).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });
});
