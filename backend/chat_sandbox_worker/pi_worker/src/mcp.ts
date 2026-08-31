import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import { createMcpAdapter, MCP_STATUS_EVENT, type McpStatusSnapshot } from "pi-mcp-adapter";
import {
  EXCALIDRAW_ENDPOINT,
  EXCALIDRAW_MODEL_TOOLS,
  excalidrawEnabled,
} from "./mcp_app_registry.js";

export type ExcalidrawTransport =
  | { url: string }
  | { command: string; args: string[] };

export type ExcalidrawViewTransport = { command: string; args: string[] };

export function mcpDirectToolsList(excalidraw: ExcalidrawTransport | false): string[] {
  const tools = ["exa/search_web"];
  if (!excalidraw) return tools;
  if ("url" in excalidraw) {
    tools.push("excalidraw/read_me", "excalidraw_view/create_view");
  } else {
    tools.push(...EXCALIDRAW_MODEL_TOOLS.map((tool) => `excalidraw/${tool}`));
  }
  return tools;
}

export function createWebMcpExtension(
  command = process.execPath,
  args = [new URL("./exa_mcp_server.js", import.meta.url).pathname],
  options?: {
    excalidraw?: ExcalidrawTransport | false;
    excalidrawView?: ExcalidrawViewTransport;
    onStatus?: (snapshot: McpStatusSnapshot) => void;
    exaEnv?: Record<string, string>;
  },
): ExtensionFactory {
  const excalidraw = options?.excalidraw === false ? false : (options?.excalidraw ?? (excalidrawEnabled() ? { url: EXCALIDRAW_ENDPOINT } : false));
  const localView = options?.excalidrawView ?? {
    command: process.execPath,
    args: [new URL("./excalidraw_view_mcp_server.js", import.meta.url).pathname],
  };
  const remoteOnly = Boolean(excalidraw && "url" in excalidraw);
  const adapter = createMcpAdapter({
    config: {
      mcpServers: {
        exa: {
          command,
          args,
          ...(options?.exaEnv ? { env: options.exaEnv } : {}),
          lifecycle: "lazy",
          directTools: ["search_web"],
          toolPrefix: "none",
          includeTools: ["search_web"],
          exposeResources: false,
          requestTimeoutMs: 4_000,
        },
        ...(excalidraw ? {
          excalidraw: {
            // The adapter owns only model-visible calls.  Its built-in viewer
            // is loopback-only inside Modal and must never be projected.
            ...("url" in excalidraw
              ? { url: excalidraw.url }
              : { command: excalidraw.command, args: excalidraw.args }),
            lifecycle: "eager",
            auth: false,
            oauth: false,
            httpTransport: "streamable-http",
            // Remote create_view returns MCP App protocol payloads that crash
            // the persistent worker.  Live URL transports keep read_me only;
            // create_view is a local stdio ack.  Command fixtures already
            // implement a tiny create_view, so they keep both tools.
            directTools: remoteOnly ? ["read_me"] : [...EXCALIDRAW_MODEL_TOOLS],
            toolPrefix: "none",
            includeTools: remoteOnly ? ["read_me"] : [...EXCALIDRAW_MODEL_TOOLS],
            exposeResources: false,
            requestTimeoutMs: remoteOnly ? 8_000 : 12_000,
          },
        } : {}),
        ...(remoteOnly ? {
          excalidraw_view: {
            command: localView.command,
            args: localView.args,
            lifecycle: "eager",
            directTools: ["create_view"],
            toolPrefix: "none",
            includeTools: ["create_view"],
            exposeResources: false,
            requestTimeoutMs: 4_000,
          },
        } : {}),
      },
      settings: {
        disableProxyTool: true,
        hostConfigDiscovery: "off",
        mcpFooterStatus: "off",
        notifyOnStartupConnect: false,
        outputGuard: { maxBytes: 128 * 1024, maxLines: 2_000, detailsMaxBytes: 16_384 },
        sampling: false,
        elicitation: false,
        scriptMode: false,
        showStatusIcon: false,
        autoAuth: false,
      },
    },
  });
  return (pi) => {
    const previous = process.env.MCP_DIRECT_TOOLS;
    process.env.MCP_DIRECT_TOOLS = mcpDirectToolsList(excalidraw).join(",");
    try {
      adapter(pi);
      if (options?.onStatus) {
        pi.events.on(MCP_STATUS_EVENT, (data: unknown) => {
          options.onStatus?.(data as McpStatusSnapshot);
        });
      }
    } finally {
      if (previous === undefined) delete process.env.MCP_DIRECT_TOOLS;
      else process.env.MCP_DIRECT_TOOLS = previous;
    }
  };
}
