import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { apiUrl } from "@/lib/apiUrl";

const EXCALIDRAW_ENDPOINT = "https://mcp.excalidraw.com/mcp";
const EXCALIDRAW_HOSTNAME = "mcp.excalidraw.com";
const EXCALIDRAW_HOST_PATH = "/api/v1/chat/mcp-apps/excalidraw";
export const EXCALIDRAW_HOST_HTML_PATH = "/api/v1/chat/mcp-apps/excalidraw/html";
const EXCALIDRAW_RESOURCE_URI = "ui://excalidraw/mcp-app.html";
const EXCALIDRAW_MODEL_TOOLS = ["read_me", "create_view"] as const;
const EXCALIDRAW_APP_TOOLS = new Set([
  "export_to_excalidraw", "save_checkpoint", "read_checkpoint",
]);
const MAX_APP_CALL_BYTES = 256 * 1024;
const MAX_APP_SESSION_BYTES = 1024 * 1024;
const MAX_APP_HTML_BYTES = 1024 * 1024;
const MIN_FRAME_HEIGHT = 240;
const MAX_FRAME_HEIGHT = 720;
const DEFAULT_FRAME_HEIGHT = 525;

export function inlineFrameHeight(width: number): number {
  if (!Number.isFinite(width) || width <= 0) return DEFAULT_FRAME_HEIGHT;
  return Math.max(MIN_FRAME_HEIGHT, Math.min(MAX_FRAME_HEIGHT, Math.round(width * 3 / 4)));
}

export interface McpAppProvider {
  id: "excalidraw";
  endpoint: typeof EXCALIDRAW_ENDPOINT;
  hostname: typeof EXCALIDRAW_HOSTNAME;
  resourceUri: typeof EXCALIDRAW_RESOURCE_URI;
  modelTools: readonly (typeof EXCALIDRAW_MODEL_TOOLS)[number][];
  appTools: ReadonlySet<string>;
}

const MCP_APP_PROVIDERS: Readonly<Record<string, McpAppProvider>> = {
  excalidraw: {
    id: "excalidraw", endpoint: EXCALIDRAW_ENDPOINT, hostname: EXCALIDRAW_HOSTNAME,
    resourceUri: EXCALIDRAW_RESOURCE_URI, modelTools: EXCALIDRAW_MODEL_TOOLS,
    appTools: EXCALIDRAW_APP_TOOLS,
  },
};

export function appsHostEnabled(): boolean {
  const value = import.meta.env.VITE_CHAT_MCP_APPS_HOST_ENABLED;
  return value === "true" || value === "1";
}

export function providerFor(value: string): McpAppProvider | undefined {
  return MCP_APP_PROVIDERS[value];
}

function hostMcpUrl(): URL {
  return new URL(apiUrl(EXCALIDRAW_HOST_PATH), window.location.origin);
}

function hostHtmlUrl(): URL {
  return new URL(apiUrl(EXCALIDRAW_HOST_HTML_PATH), window.location.origin);
}

class BoundedProviderClient {
  private readonly client = new Client({ name: "pwc-chat-mcp-app-host", version: "1" });
  private readonly transport = new StreamableHTTPClientTransport(hostMcpUrl(), {
    requestInit: { credentials: "include" },
  });
  private connected: Promise<void> | undefined;
  private bytes = 0;
  private closed = false;

  connect(): Promise<void> {
    if (this.closed) return Promise.reject(new Error("App host client is closed"));
    if (!this.connected) {
      this.connected = this.client.connect(this.transport).then(
        () => undefined,
        (error) => {
          this.connected = undefined;
          this.retire();
          throw error;
        },
      );
    }
    return this.connected;
  }

  async readResource(uri: string): Promise<{ text: string; digest: string }> {
    if (uri !== EXCALIDRAW_RESOURCE_URI) throw new Error("Unapproved App resource");
    await this.connect();
    const result = await this.client.readResource({ uri });
    const resource = result.contents[0];
    if (!resource || !("text" in resource) || typeof resource.text !== "string" || resource.mimeType !== "text/html;profile=mcp-app") {
      throw new Error("Incompatible App resource");
    }
    this.consume(resource.text, MAX_APP_HTML_BYTES);
    const digest = await sha256(resource.text);
    return { text: resource.text, digest };
  }

  async callTool(name: string, args: Record<string, unknown>) {
    if (!EXCALIDRAW_APP_TOOLS.has(name)) throw new Error("Unapproved App tool");
    const body = JSON.stringify(args);
    this.consume(body);
    try {
      await this.connect();
      const result = await this.client.callTool({ name, arguments: args });
      this.consume(JSON.stringify(result));
      return result;
    } catch (error) {
      this.retire();
      throw error;
    }
  }

  close(): void {
    this.closed = true;
    this.connected = undefined;
    void this.transport.close();
  }

  private retire(): void {
    this.close();
    if (providerClient === this) providerClient = undefined;
  }

  private consume(value: string, maximum = MAX_APP_CALL_BYTES): void {
    const bytes = new TextEncoder().encode(value).byteLength;
    if (bytes > maximum || this.bytes + bytes > MAX_APP_SESSION_BYTES) {
      throw new Error("App request exceeds host limit");
    }
    this.bytes += bytes;
  }
}

let providerClient: BoundedProviderClient | undefined;
let htmlCache: string | undefined;

export function excalidrawClient(): BoundedProviderClient {
  providerClient ??= new BoundedProviderClient();
  return providerClient;
}

function closeMcpAppClients(): void {
  providerClient?.close();
  providerClient = undefined;
}

export function resetExcalidrawAppHost(options?: { dropHtmlCache?: boolean }): void {
  closeMcpAppClients();
  if (options?.dropHtmlCache) htmlCache = undefined;
}

export async function loadExcalidrawAppHtml(): Promise<string> {
  if (htmlCache) return htmlCache;
  const response = await fetch(hostHtmlUrl(), {
    method: "GET",
    credentials: "include",
    headers: { Accept: "text/html;profile=mcp-app, text/html" },
  });
  if (!response.ok) throw new Error("Diagram service unavailable");
  const text = await response.text();
  const bytes = new TextEncoder().encode(text).byteLength;
  if (bytes > MAX_APP_HTML_BYTES || (!text.toLowerCase().includes("<html") && !text.toLowerCase().includes("<!doctype html"))) {
    throw new Error("Incompatible App resource");
  }
  htmlCache = text;
  return text;
}

async function sha256(value: string): Promise<string> {
  const encoded = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("");
}
