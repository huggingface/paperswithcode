import { queryOptions } from "@tanstack/react-query";

export const MCP_PRODUCTION_ENDPOINT = "https://paperswithcode.co/mcp";
export const MCP_STAGING_ENDPOINT = "https://staging.paperswithcode.co/mcp";

export interface McpHealth {
  status: "ok";
  service: "pwc-mcp";
  version: string;
  protocol: string;
}

export function mcpEndpoint(location?: Pick<Location, "hostname" | "origin">): string {
  const current = location ?? (typeof window === "undefined" ? undefined : window.location);
  if (!current) return MCP_PRODUCTION_ENDPOINT;
  if (current.hostname === "staging.paperswithcode.co") return MCP_STAGING_ENDPOINT;
  if (
    current.hostname === "paperswithcode.co" ||
    current.hostname === "www.paperswithcode.co"
  ) {
    return MCP_PRODUCTION_ENDPOINT;
  }
  return `${current.origin.replace(/\/$/, "")}/mcp`;
}

function parseHealth(payload: unknown): McpHealth {
  if (
    !payload ||
    typeof payload !== "object" ||
    (payload as Record<string, unknown>).status !== "ok" ||
    (payload as Record<string, unknown>).service !== "pwc-mcp" ||
    typeof (payload as Record<string, unknown>).version !== "string" ||
    typeof (payload as Record<string, unknown>).protocol !== "string"
  ) {
    throw new Error("MCP health response is invalid");
  }
  return payload as McpHealth;
}

export async function fetchMcpHealth(signal?: AbortSignal): Promise<McpHealth> {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  const timeout = window.setTimeout(cancel, 5_000);
  try {
    const response = await fetch(`${mcpEndpoint()}/health`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
      credentials: "omit",
    });
    if (!response.ok) throw new Error("MCP service is unavailable");
    return parseHealth(await response.json());
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", cancel);
  }
}

export const mcpHealthQueryOptions = () =>
  queryOptions({
    queryKey: ["mcp", "health"],
    queryFn: ({ signal }) => fetchMcpHealth(signal),
    retry: false,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
