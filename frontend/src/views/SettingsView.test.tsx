import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SettingsView from "@/views/SettingsView";

const mockAuth = vi.hoisted(() => ({
  state: {
    user: { username: "nielsr", hf_subject: "hf-user-1" } as {
      username: string;
      hf_subject: string;
    } | null,
    isLoading: false,
  },
}));
const mockCanPersist = vi.hoisted(() => ({ value: true }));
const mockPreferencesLoading = vi.hoisted(() => ({ value: false }));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "system", setTheme: vi.fn() }),
}));

vi.mock("@/lib/authContext", () => ({
  useAuth: () => mockAuth.state,
  useOptionalAuth: () => mockAuth.state,
}));

vi.mock("@/lib/preferences", () => ({
  usePreferences: () => ({
    preferences: { hideClosedSourceEvals: false },
    setHideClosedSourceEvals: vi.fn(),
    canPersist: mockCanPersist.value,
    isLoading: mockPreferencesLoading.value,
  }),
}));

type Provider = "huggingface" | "openrouter" | "openai";

type BillingStatus = {
  connected: boolean;
  account_type: string | null;
  monthly_credits_usd: number | null;
  pay_as_you_go: boolean;
  usage_url: string;
  token_url: string;
  bill_to: string | null;
  organizations: Array<{ name: string; display_name: string }>;
};

const personalStatus: BillingStatus = {
  connected: true,
  account_type: "PRO",
  monthly_credits_usd: 2,
  pay_as_you_go: true,
  usage_url: "https://huggingface.co/settings/inference-providers",
  token_url: "https://huggingface.co/settings/tokens/new",
  bill_to: null,
  organizations: [
    { name: "huggingface", display_name: "Hugging Face" },
  ],
};

const openRouterUsage = {
  used_percent: 4,
  remaining_percent: 96,
  resets_at: "2026-09-01T00:00:00Z",
  available: true,
  unavailable_reason: null,
  as_of: "2026-08-02T00:00:00Z",
};

const openRouterCredential = {
  connected: false,
  verified_at: null,
  fallback_enabled: false,
};

function jsonResponse(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function providerModels(providers: Provider[]) {
  return {
    items: providers.map((provider, index) => ({
      id: `${provider}-model-${index}`,
      label: `${provider} model`,
      provider,
      reasoning_efforts: ["low", "high", "max"],
    })),
    default_model: `${providers[0]}-model-0`,
  };
}

function mockProviderRequests(
  providers: Provider[],
  options: {
    billing?: BillingStatus;
    connectKeyError?: boolean;
  } = {},
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/me/follows")) return jsonResponse([]);
    if (url.includes("/me/research-email")) return jsonResponse({ enabled: false, email: null, suppressed: false, delivery_ready: false });
    if (url.includes("/chat/models")) return jsonResponse(providerModels(providers));
    if (url.includes("/me/inference-billing")) {
      if (init?.method === "PATCH") {
        return jsonResponse({
          ...(options.billing ?? personalStatus),
          account_type: "Organization",
          monthly_credits_usd: null,
          bill_to: "huggingface",
        });
      }
      return jsonResponse(options.billing ?? personalStatus);
    }
    if (url.includes("/chat/usage")) return jsonResponse(openRouterUsage);
    if (url.includes("/chat/openrouter-key") && init?.method === "PUT" && options.connectKeyError) {
      return jsonResponse({
        detail: {
          code: "fresh_auth_required",
          message: "Refresh your Hugging Face sign-in before changing your OpenRouter key.",
        },
      }, 401);
    }
    if (url.includes("/chat/openrouter-key")) return jsonResponse(openRouterCredential);
    return jsonResponse({ detail: "unexpected request" }, 500);
  });
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><SettingsView /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SettingsView provider-aware chat billing", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("VITE_CHAT_ENABLED", "1");
    mockAuth.state = {
      user: { username: "nielsr", hf_subject: "hf-user-1" },
      isLoading: false,
    };
    mockCanPersist.value = true;
    mockPreferencesLoading.value = false;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("shows only Hugging Face when only Inference Providers is enabled", async () => {
    const fetchMock = mockProviderRequests(["huggingface"]);

    renderSettings();

    expect(await screen.findByRole("heading", { name: "Inference Providers" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "OpenRouter" })).not.toBeInTheDocument();
    expect(await screen.findByText("Personal account · @nielsr")).toBeVisible();
    expect(screen.queryByText("Re-sign in with Hugging Face")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/me/inference-billing"))).toBe(true);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/chat/usage"))).toBe(false);
  });

  it("shows only OpenRouter when only OpenRouter is enabled", async () => {
    const fetchMock = mockProviderRequests(["openrouter"]);

    renderSettings();

    expect(await screen.findByRole("heading", { name: "OpenRouter" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Inference Providers" })).not.toBeInTheDocument();
    expect(await screen.findByText("96% left")).toBeVisible();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/me/inference-billing"))).toBe(false);
  });

  it("shows both cards when both providers are enabled", async () => {
    mockProviderRequests(["huggingface", "openrouter", "openai"]);

    renderSettings();

    expect(await screen.findByRole("heading", { name: "Inference Providers" })).toBeVisible();
    expect(await screen.findByRole("heading", { name: "OpenRouter" })).toBeVisible();
    // Billing cards only; the research topic editor has its own h3.
    expect(screen.getAllByRole("heading", { level: 3 }).filter(h => h.textContent !== "Topic")).toHaveLength(2);
    expect(await screen.findByText("96% left")).toBeVisible();
    expect(screen.getByText(/Direct OpenAI usage is provided by Papers With Code/i)).toBeVisible();
    expect(screen.queryByLabelText(/OpenAI API key/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "OpenAI" })).not.toBeInTheDocument();
  });

  it("reveals settings atomically after all provider data is ready", async () => {
    let resolveBilling!: (response: Response) => void;
    let billingRequested = false;
    const billingResponse = new Promise<Response>((resolve) => {
      resolveBilling = resolve;
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
    if (url.includes("/me/follows")) return jsonResponse([]);
    if (url.includes("/me/research-email")) return jsonResponse({ enabled: false, email: null, suppressed: false, delivery_ready: false });
      if (url.includes("/chat/models")) {
        return jsonResponse(providerModels(["huggingface"]));
      }
      if (url.includes("/me/inference-billing")) {
        billingRequested = true;
        return billingResponse;
      }
      return jsonResponse({ detail: "unexpected request" }, 500);
    });

    renderSettings();
    await waitFor(() => expect(billingRequested).toBe(true));

    expect(screen.getByRole("status")).toHaveTextContent("Loading settings…");
    expect(screen.queryByRole("heading", { name: "Catalog access" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Inference Providers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Appearance" })).not.toBeInTheDocument();

    act(() => resolveBilling(jsonResponse(personalStatus)));

    expect(await screen.findByRole("heading", { name: "Inference Providers" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("lets a connected HF user select an organization billing account", async () => {
    const fetchMock = mockProviderRequests(["huggingface"]);

    renderSettings();
    const selector = await screen.findByRole("combobox", { name: "Bill chat usage to" });
    expect(selector).toHaveValue("");

    await userEvent.selectOptions(selector, "huggingface");

    await waitFor(() => expect(selector).toHaveValue("huggingface"));
    expect(screen.getByText("Organization · huggingface")).toBeVisible();
    expect(fetchMock.mock.calls.some(([, init]) => (
      init?.method === "PATCH" && init.body === JSON.stringify({ bill_to: "huggingface" })
    ))).toBe(true);
  });

  it("uses OAuth authorization instead of asking for a manual HF token", async () => {
    mockProviderRequests(["huggingface"], {
      billing: {
        ...personalStatus,
        connected: false,
        account_type: null,
        monthly_credits_usd: null,
        organizations: [],
      },
    });

    renderSettings();

    expect(await screen.findByText(/Reconnect with Hugging Face/)).toBeVisible();
    expect(screen.getByText("Re-sign in with Hugging Face").closest("button")).toBeVisible();
    expect(screen.queryByLabelText("Hugging Face token")).not.toBeInTheDocument();
  });

  it("offers a security refresh when connecting an OpenRouter key needs fresh auth", async () => {
    mockProviderRequests(["openrouter"], { connectKeyError: true });

    renderSettings();
    const keyInput = await screen.findByLabelText("OpenRouter API key");
    await userEvent.type(keyInput, "sk-or-test");
    await userEvent.click(screen.getByRole("button", { name: "Connect key" }));

    expect(await screen.findByText(/account is signed in/i)).toBeVisible();
    expect(screen.getByText("Re-authenticate with Hugging Face").closest("button")).toBeVisible();
  });

  it("does not flash the sign-in prompt while authentication is loading", () => {
    mockAuth.state = { user: null, isLoading: true };
    mockCanPersist.value = false;
    const fetchMock = vi.spyOn(globalThis, "fetch");

    renderSettings();

    expect(screen.getByRole("status")).toHaveTextContent("Loading settings…");
    expect(screen.queryByRole("button", { name: "Sign in with Hugging Face" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a provider-neutral sign-in prompt after authentication resolves signed out", () => {
    mockAuth.state = { user: null, isLoading: false };
    mockCanPersist.value = false;

    renderSettings();

    expect(screen.getByText(/manage billing and credentials for the enabled chat providers/i)).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Sign in with Hugging Face" })).toHaveLength(3);
  });
});

describe("SettingsView chat-disabled boundary", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubEnv("VITE_CHAT_ENABLED", "0");
    mockAuth.state = {
      user: { username: "nielsr", hf_subject: "hf-user-1" },
      isLoading: false,
    };
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("hides chat settings and does not request provider data", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");

    renderSettings();

    expect(screen.queryByRole("heading", { name: "Chat usage & billing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Inference Providers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "OpenRouter" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeVisible();
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes("/me/follows") || String(url).includes("/me/research-email"))).toBe(true);
  });
});
