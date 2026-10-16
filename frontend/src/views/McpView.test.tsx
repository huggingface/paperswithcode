import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import McpView from "@/views/McpView";

const renderView = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <McpView />
    </QueryClientProvider>,
  );
};

afterEach(() => vi.restoreAllMocks());

describe("McpView", () => {
  it("shows the connection URL and degrades cleanly when health fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    renderView();

    expect(
      screen.getByRole("heading", { name: "Use Papers With Code in your AI assistant" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/\/mcp$/).length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("Status unavailable")).toBeInTheDocument());
  });

  it("links the pwc-cli repository at the top of the page", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    renderView();

    const banner = screen.getByRole("link", { name: /huggingface\/pwc-cli/ });
    expect(banner).toHaveAttribute("href", "https://github.com/huggingface/pwc-cli");
  });

  it("reports healthy version and protocol without blocking the page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          service: "pwc-mcp",
          version: "0.2.1",
          protocol: "2025-11-25",
        }),
        { status: 200 },
      ),
    );
    renderView();

    await waitFor(() => expect(screen.getByText(/Operational · v0.2.1/)).toBeInTheDocument());
    expect(screen.getByText(/Primary protocol: 2025-11-25/)).toBeInTheDocument();
  });

  it("documents every agreed tool and resource", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    renderView();

    for (const tool of [
      "search_papers",
      "list_papers",
      "get_paper_info",
      "read_paper",
      "list_recent_papers",
      "get_related_papers",
      "list_trending_papers",
      "get_paper_evaluations",
      "get_paper_lineage",
      "get_task",
      "list_tasks",
      "get_method",
      "list_methods",
      "get_conference",
      "list_conferences",
      "get_organization",
      "list_organizations",
      "get_framework",
      "list_frameworks",
      "list_benchmarks",
      "get_benchmark",
    ]) {
      expect(screen.getByText(tool)).toBeInTheDocument();
    }
    for (const resource of [
      "pwc://papers/{paper}",
      "pwc://papers/{paper}/markdown",
      "pwc://tasks/{task}",
      "pwc://benchmarks/{benchmark}",
    ]) {
      expect(screen.getByText(resource)).toBeInTheDocument();
    }
  });

  it("switches among client instructions and labels qualification honestly", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    renderView();

    expect(screen.getByText(/staging qualification pending/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Claude Code" }));
    expect(screen.getByText(/claude mcp add --transport http/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "VS Code" }));
    expect(screen.getByText(/"type": "http"/)).toBeInTheDocument();
  });

  it("states limits, privacy, examples, and supporting documentation", () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("", { status: 503 }));
    renderView();

    expect(screen.getByText(/60 total requests per minute/)).toBeInTheDocument();
    expect(screen.getByText(/No account, API key, or write access/)).toBeInTheDocument();
    expect(screen.getByText(/MCP telemetry retains tool name/)).toBeInTheDocument();
    expect(screen.getByText(/Trace the predecessor and successor papers/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /CLI repository/ })).toHaveAttribute(
      "href",
      "https://github.com/huggingface/pwc-cli",
    );
    expect(screen.getByRole("link", { name: /llms.txt/ })).toHaveAttribute(
      "href",
      "/llms.txt",
    );
    expect(screen.getByRole("link", { name: /MCP tool schema/ })).toHaveAttribute(
      "href",
      "/mcp/schema",
    );
  });
});
