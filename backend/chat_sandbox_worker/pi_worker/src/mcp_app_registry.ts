/** Closed release configuration for worker-visible MCP Apps.
 *
 * This is deliberately code, not an environment supplied URL or a database
 * row: adding an App means adding a reviewed provider entry and tests.
 */
import { createHash } from "node:crypto";

export const EXCALIDRAW_ENDPOINT = "https://mcp.excalidraw.com/mcp";
export const EXCALIDRAW_HOSTNAME = "mcp.excalidraw.com";
export const EXCALIDRAW_RESOURCE_URI = "ui://excalidraw/mcp-app.html";
export const EXCALIDRAW_MODEL_TOOLS = ["read_me", "create_view"] as const;
export const EXCALIDRAW_APP_TOOLS = [
  "export_to_excalidraw",
  "save_checkpoint",
  "read_checkpoint",
] as const;
export const MAX_EXCALIDRAW_ELEMENTS_BYTES = 128 * 1024;
export const MAX_EXCALIDRAW_CONTEXT_BYTES = 8 * 1024;
export const EMPTY_EGRESS_POLICY_DIGEST = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945";
export const INVALID_EXCALIDRAW_ELEMENTS =
  "create_view.elements must be a JSON array of diagram elements. Fix the JSON and call create_view again.";
export const EXCALIDRAW_ELEMENTS_TOO_LARGE = "Diagram input is too large. Answer in text.";

export function serializeExcalidrawElements(elements: unknown): string | undefined {
  const serialized = typeof elements === "string" ? elements : JSON.stringify(elements ?? null);
  if (Buffer.byteLength(serialized) > MAX_EXCALIDRAW_ELEMENTS_BYTES) return undefined;
  try {
    if (!Array.isArray(JSON.parse(serialized))) return undefined;
  } catch {
    return undefined;
  }
  return serialized;
}

export function excalidrawElementsTooLarge(elements: unknown): boolean {
  const serialized = typeof elements === "string" ? elements : JSON.stringify(elements ?? null);
  return Buffer.byteLength(serialized) > MAX_EXCALIDRAW_ELEMENTS_BYTES;
}

export interface McpAppProvider {
  id: "excalidraw";
  endpoint: typeof EXCALIDRAW_ENDPOINT;
  hostname: typeof EXCALIDRAW_HOSTNAME;
  resourceUri: typeof EXCALIDRAW_RESOURCE_URI;
  modelTools: readonly (typeof EXCALIDRAW_MODEL_TOOLS)[number][];
  appTools: readonly (typeof EXCALIDRAW_APP_TOOLS)[number][];
}

export const MCP_APP_PROVIDERS: readonly McpAppProvider[] = [{
  id: "excalidraw",
  endpoint: EXCALIDRAW_ENDPOINT,
  hostname: EXCALIDRAW_HOSTNAME,
  resourceUri: EXCALIDRAW_RESOURCE_URI,
  modelTools: EXCALIDRAW_MODEL_TOOLS,
  appTools: EXCALIDRAW_APP_TOOLS,
}];

export function excalidrawEnabled(): boolean {
  return process.env.PWC_CHAT_EXCALIDRAW_ENABLED === "true";
}

export function mcpAppsHostEnabled(): boolean {
  return process.env.PWC_CHAT_MCP_APPS_HOST_ENABLED === "true";
}

export function isExcalidrawModelTool(name: unknown): name is (typeof EXCALIDRAW_MODEL_TOOLS)[number] {
  return typeof name === "string" && (EXCALIDRAW_MODEL_TOOLS as readonly string[]).includes(name);
}

export function enabledWorkerMcpProviders(): readonly McpAppProvider[] {
  return excalidrawEnabled() ? MCP_APP_PROVIDERS : [];
}

export function egressPolicyDigest(providers = enabledWorkerMcpProviders()): string {
  const payload = JSON.stringify(
    [...providers]
      .sort((left, right) => left.id.localeCompare(right.id))
      .map((provider) => ({
        endpoint: provider.endpoint,
        hostname: provider.hostname,
        id: provider.id,
        model_tools: [...provider.modelTools].sort(),
      })),
  );
  return createHash("sha256").update(payload).digest("hex");
}

export type McpProviderFailureClass =
  | "configured_not_connected"
  | "connected_missing_tools"
  | "connected_incompatible"
  | "discovery_timeout";

export type McpProviderReadinessState = "unconfigured" | "ready" | McpProviderFailureClass;

export interface McpReadinessSnapshot {
  enabled_provider_ids: string[];
  providers: Record<string, {
    state: McpProviderReadinessState;
    connected: boolean;
    discovered_tools: string[];
  }>;
  registered_tool_names: string[];
  registered_tool_digest: string;
  failure_class: McpProviderFailureClass | null;
  registration_latency_ms: number;
  egress_policy_digest: string;
  ready: boolean;
}

export function toolNameDigest(names: readonly string[]): string {
  return createHash("sha256").update([...names].sort().join(",")).digest("hex");
}

function createViewLooksCompatible(definition: { parameters?: unknown } | undefined): boolean {
  const parameters = definition?.parameters;
  if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) return false;
  const schema = parameters as Record<string, unknown>;
  const properties = schema.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return false;
  return "elements" in (properties as Record<string, unknown>);
}

export function assessExcalidrawReadiness(options: {
  enabled: boolean;
  connectionMode?: "remote" | "lazy" | undefined;
  serverStatus?: string | undefined;
  activeTools: readonly string[];
  createViewDefinition?: { parameters?: unknown } | undefined;
  latencyMs?: number | undefined;
  timedOut?: boolean | undefined;
}): McpReadinessSnapshot {
  const registered = [...options.activeTools].sort();
  const egress = egressPolicyDigest(options.enabled ? MCP_APP_PROVIDERS : []);
  const base = {
    enabled_provider_ids: options.enabled ? ["excalidraw"] : [],
    registered_tool_names: registered,
    registered_tool_digest: toolNameDigest(registered),
    registration_latency_ms: options.latencyMs ?? 0,
    egress_policy_digest: egress,
  };
  if (!options.enabled) {
    return {
      ...base,
      providers: {},
      failure_class: null,
      ready: false,
    };
  }
  const discovered = registered.filter((name) => (EXCALIDRAW_MODEL_TOOLS as readonly string[]).includes(name));
  const appOnlyPresent = registered.some((name) => (EXCALIDRAW_APP_TOOLS as readonly string[]).includes(name));
  const connected = options.serverStatus === "connected";
  const available = options.connectionMode === "lazy" || connected;
  const expected = EXCALIDRAW_MODEL_TOOLS;
  const hasExpected = expected.every((name) => registered.includes(name));
  let state: McpProviderReadinessState;
  let failure: McpProviderFailureClass | null = null;
  if (options.timedOut && !available) {
    state = "discovery_timeout";
    failure = "discovery_timeout";
  } else if (!available) {
    state = "configured_not_connected";
    failure = "configured_not_connected";
  } else if (appOnlyPresent || (hasExpected && !createViewLooksCompatible(options.createViewDefinition))) {
    state = "connected_incompatible";
    failure = "connected_incompatible";
  } else if (!hasExpected) {
    state = "connected_missing_tools";
    failure = "connected_missing_tools";
  } else {
    state = "ready";
  }
  return {
    ...base,
    providers: {
      excalidraw: {
        state,
        connected,
        discovered_tools: discovered,
      },
    },
    failure_class: failure,
    ready: state === "ready",
  };
}
