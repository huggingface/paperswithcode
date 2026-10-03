import { createMcpExtension, type ExtensionFactory } from "@earendil-works/pi-coding-agent";

export const WEB_SEARCH_TOOL = "mcp__exa__search_web";

/** Preserve the public chat event and policy names across native MCP namespacing. */
export function chatToolName(name: string): string {
  return name === WEB_SEARCH_TOOL ? "search_web" : name;
}

/** Native Pi MCP, with only the reviewed gateway-backed server configuration. */
export function createWebMcpExtension(
  command = process.execPath,
  args = [new URL("./exa_mcp_server.js", import.meta.url).pathname],
  options?: { exa?: boolean; exaEnv?: Record<string, string> },
): ExtensionFactory {
  return createMcpExtension({
    // Never discover user/project MCP files in a multi-user chat worker.
    loadConfig: () => ({
      errors: [],
      autoEnableCodemode: false,
      servers: options?.exa === false ? [] : [{
        name: "exa",
        source: "pwc-web-search",
        scope: "extension",
        config: {
          command,
          args,
          ...(options?.exaEnv ? { env: options.exaEnv } : {}),
          timeout: 8,
          exposure: "hidden",
          toolExposure: { search_web: "direct" },
        },
      }],
    }),
    startupWaitMs: 10_000,
  });
}
