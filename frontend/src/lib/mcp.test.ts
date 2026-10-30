import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MCP_PRODUCTION_ENDPOINT,
  MCP_STAGING_ENDPOINT,
  fetchMcpHealth,
  mcpEndpoint,
  mcpHealthQueryOptions,
} from "@/lib/mcp";

afterEach(() => vi.restoreAllMocks());

describe("MCP endpoint selection", () => {
  it("uses the canonical production and staging endpoints", () => {
    expect(
      mcpEndpoint({ hostname: "paperswithcode.co", origin: "https://paperswithcode.co" }),
    ).toBe(MCP_PRODUCTION_ENDPOINT);
    expect(
      mcpEndpoint({
        hostname: "staging.paperswithcode.co",
        origin: "https://staging.paperswithcode.co",
      }),
    ).toBe(MCP_STAGING_ENDPOINT);
  });

  it("keeps local development on its current origin", () => {
    expect(mcpEndpoint({ hostname: "localhost", origin: "http://localhost:5173" })).toBe(
      "http://localhost:5173/mcp",
    );
  });
});

describe("MCP health", () => {
  it("parses bounded public health JSON without credentials", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          service: "pwc-mcp",
          version: "0.1.0",
          protocol: "2026-07-28",
        }),
        { status: 200 },
      ),
    );

    await expect(fetchMcpHealth()).resolves.toMatchObject({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/mcp\/health$/),
      expect.objectContaining({ credentials: "omit" }),
    );
  });

  it("fails closed for unavailable and malformed health responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("", { status: 503 }));
    await expect(fetchMcpHealth()).rejects.toThrow("unavailable");

    vi.mocked(globalThis.fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    await expect(fetchMcpHealth()).rejects.toThrow("invalid");
  });

  it("uses a bounded, non-aggressive query policy", () => {
    const options = mcpHealthQueryOptions();
    expect(options.retry).toBe(false);
    expect(options.staleTime).toBe(30_000);
    expect(options.refetchInterval).toBe(60_000);
  });
});
