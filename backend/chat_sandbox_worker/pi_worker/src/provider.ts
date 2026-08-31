import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { type TurnClaimFrame } from "./turn_protocol.js";

export const PROVIDER_ID = "pwc-gateway";
export const PLACEHOLDER_KEY = "sandbox-placeholder-not-a-credential";

export type ProviderProtocol = "anthropic-messages" | "openai-responses";

export interface GatewayContext {
  url: string;
  capability: string;
  sessionId: string;
  turnId: string;
  turnClaim: TurnClaimFrame;
}

export function gatewayHeaders(
  gateway: GatewayContext,
  protocol?: ProviderProtocol,
): Record<string, string> {
  return {
    Authorization: `Bearer ${gateway.capability}`,
    "X-PWC-Session": gateway.sessionId,
    "X-PWC-Turn": gateway.turnId,
    "X-PWC-Turn-Worker-ID": gateway.turnClaim.workerId,
    "X-PWC-Turn-Worker-Generation": String(gateway.turnClaim.workerGeneration),
    "X-PWC-Turn-Lease-Generation": String(gateway.turnClaim.leaseGeneration),
    ...(protocol ? { "X-PWC-Provider-Protocol": protocol } : {}),
  };
}

export async function createProvider(
  modelId: string,
  api: ProviderProtocol = "anthropic-messages",
  gateway?: GatewayContext,
) {
  const gatewayUrl = gateway?.url.replace(/\/$/u, "") ?? "http://127.0.0.1:8765";
  const baseUrl = api === "openai-responses"
    ? `${gatewayUrl}/v1`
    : gatewayUrl;
  const headers = gateway ? gatewayHeaders(gateway, api) : undefined;
  if (headers) delete headers.Authorization;
  const credentials = new InMemoryCredentialStore();
  const runtime = await ModelRuntime.create({
    credentials,
    modelsPath: null,
    allowModelNetwork: false,
    refreshOnCreate: false,
  });
  runtime.registerProvider(PROVIDER_ID, {
    name: "PwC Gateway",
    baseUrl,
    apiKey: gateway?.capability ?? PLACEHOLDER_KEY,
    api,
    authHeader: true,
    ...(headers ? { headers } : {}),
    models: [
      {
        id: modelId,
        name: modelId,
        api,
        baseUrl,
        ...(headers ? { headers } : {}),
        reasoning: true,
        thinkingLevelMap: {
          off: null,
          low: "low",
          medium: "high",
          high: "high",
          xhigh: "max",
          max: "max",
        },
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 200000,
        maxTokens: 8000,
        compat: api === "anthropic-messages"
          ? {
              supportsEagerToolInputStreaming: true,
              supportsCacheControlOnTools: true,
              supportsTemperature: false,
            }
          : {
              supportsTemperature: false,
              sessionAffinityFormat: "openai-nosession",
            },
      },
    ],
  });
  const model = runtime.getModel(PROVIDER_ID, modelId);
  if (!model) throw new Error("PwC Pi model registration failed");
  return { runtime, model };
}

export function thinkingLevel(effort: string): "low" | "high" | "max" {
  if (effort === "low") return "low";
  if (effort === "max") return "max";
  return "high";
}
