import {
  type Api,
  type AssistantMessageEventStream,
  type TranscriptContext,
  InMemoryCredentialStore,
  type Model,
  type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { streamSimple as streamOpenAIResponses } from "@earendil-works/pi-ai/api/openai-responses";
import { streamSimple as streamAnthropicMessages } from "@earendil-works/pi-ai/api/anthropic-messages";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { type TurnClaimFrame } from "./turn_protocol.js";

export const PROVIDER_ID = "pwc-gateway";
export const PLACEHOLDER_KEY = "sandbox-placeholder-not-a-credential";
export const GATEWAY_PAYLOAD_LIMIT_BYTES = 7 * 1024 * 1024;

// Use the short-context working window for Luna, GLM and the reviewed
// DeepSeek V4 routes. Their larger model capacity (1M on the Hugging Face
// router) does not require sending larger requests by default, but the 200K
// fallback caps the gateway payload at 240 KB, which long paper reads exceed.
export function modelContextWindow(modelId: string, api: ProviderProtocol): number {
  const model = modelId.split(":")[0]!.split("@")[0]!;
  if ([
    "gpt-6-luna",
    "gpt-5.6-luna",
    "openai/gpt-5.6-luna",
    "zai-org/GLM-5.3-Flash",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "deepseek-ai/DeepSeek-V4.1-Flash-1017",
  ].includes(model)) return 272_000;
  return api === "openai-responses" ? 48_000 : 200_000;
}
export function gatewayPayloadLimit(contextWindow: number): number {
  if (contextWindow >= 1_000_000) return GATEWAY_PAYLOAD_LIMIT_BYTES;
  return contextWindow >= 272_000 ? 2 * 1024 * 1024 : 240 * 1024;
}

export type ProviderProtocol = "anthropic-messages" | "openai-responses";

export interface GatewayContext {
  url: string;
  capability: string;
  sessionId: string;
  turnId: string;
  turnClaim: TurnClaimFrame;
}

export function boundedGatewayPayload(payload: unknown, limit = GATEWAY_PAYLOAD_LIMIT_BYTES): unknown {
  if (Buffer.byteLength(JSON.stringify(payload), "utf8") >= limit) {
    throw new Error("request_too_large: provider context requires compaction");
  }
  return payload;
}

function boundedOpenAIResponsesStream(
  model: Model<Api>,
  context: TranscriptContext,
  options?: SimpleStreamOptions,
): AssistantMessageEventStream {
  const callerPayload = options?.onPayload;
  return streamOpenAIResponses(
    model as Model<"openai-responses">,
    context,
    {
      ...options,
      onPayload: async (payload, payloadModel) => {
        const replacement = await callerPayload?.(payload, payloadModel);
        const bounded = boundedGatewayPayload(replacement ?? payload, gatewayPayloadLimit(model.contextWindow));
        // Use the SDK's final allowance: it accounts for system text, tools,
        // messages and its context safety margin. Never send a starved request.
        const limit = (bounded as Record<string, unknown>)[model.api === "openai-responses" ? "max_output_tokens" : "max_tokens"];
        const required = Math.min(options?.maxTokens ?? model.maxTokens, model.maxTokens);
        if (typeof limit === "number" && limit < required) {
          throw new Error(`request_too_large: insufficient_output_budget available=${limit} required=${required}`);
        }
        return bounded;
      },
    },
  );
}

function boundedAnthropicMessagesStream(
  model: Model<Api>,
  context: TranscriptContext,
  options?: SimpleStreamOptions,
): AssistantMessageEventStream {
  const callerPayload = options?.onPayload;
  return streamAnthropicMessages(
    model as Model<"anthropic-messages">,
    context,
    {
      ...options,
      onPayload: async (payload, payloadModel) => {
        const replacement = await callerPayload?.(payload, payloadModel);
        const bounded = boundedGatewayPayload(replacement ?? payload, gatewayPayloadLimit(model.contextWindow));
        // Use the SDK's final allowance: it accounts for system text, tools,
        // messages and its context safety margin. Never send a starved request.
        const limit = (bounded as Record<string, unknown>)[model.api === "openai-responses" ? "max_output_tokens" : "max_tokens"];
        const required = Math.min(options?.maxTokens ?? model.maxTokens, model.maxTokens);
        if (typeof limit === "number" && limit < required) {
          throw new Error(`request_too_large: insufficient_output_budget available=${limit} required=${required}`);
        }
        return bounded;
      },
    },
  );
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
    streamSimple: api === "openai-responses"
      ? boundedOpenAIResponsesStream
      : boundedAnthropicMessagesStream,
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
          medium: "medium",
          high: "high",
          xhigh: "max",
          max: "max",
        },
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: modelContextWindow(modelId, api),
        maxTokens: 8000,
        compat: api === "anthropic-messages"
          ? {
              supportsEagerToolInputStreaming: true,
              supportsCacheControlOnTools: true,
              supportsTemperature: false,
            }
          : {
              sessionAffinityFormat: "openai-nosession",
            },
      },
    ],
  });
  const model = runtime.getModel(PROVIDER_ID, modelId);
  if (!model) throw new Error("PwC Pi model registration failed");
  return { runtime, model };
}

export function thinkingLevel(effort: string): "low" | "medium" | "high" | "max" {
  if (effort === "low") return "low";
  if (effort === "medium") return "medium";
  if (effort === "max") return "max";
  return "high";
}
