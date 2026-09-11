import {
  type Api,
  type AssistantMessageEventStream,
  type Context,
  InMemoryCredentialStore,
  type Model,
  type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { streamSimple as streamOpenAIResponses } from "@earendil-works/pi-ai/api/openai-responses";
import { ModelRuntime } from "@earendil-works/pi-coding-agent";
import { type TurnClaimFrame } from "./turn_protocol.js";

export const PROVIDER_ID = "pwc-gateway";
export const PLACEHOLDER_KEY = "sandbox-placeholder-not-a-credential";
const OPENAI_GATEWAY_PAYLOAD_LIMIT_BYTES = 240 * 1024;
const COMPACTION_SYSTEM_PROMPT_PREFIX = "You are a context summarization assistant.";
const COMPACTION_OMISSION_MARKER = "\n\n[...older compaction input omitted to fit the gateway...]\n\n";

export type ProviderProtocol = "anthropic-messages" | "openai-responses";

export interface GatewayContext {
  url: string;
  capability: string;
  sessionId: string;
  turnId: string;
  turnClaim: TurnClaimFrame;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : undefined;
}

function compactionText(
  payload: unknown,
): { payload: Record<string, unknown>; text: string; textPart: Record<string, unknown> } | undefined {
  const record = asRecord(payload);
  const input = record?.input;
  if (!record || !Array.isArray(input)) return undefined;
  const developer = input.map(asRecord).find((entry) => entry?.role === "developer");
  if (
    typeof developer?.content !== "string"
    || !developer.content.startsWith(COMPACTION_SYSTEM_PROMPT_PREFIX)
  ) return undefined;
  const user = input.map(asRecord).find((entry) => entry?.role === "user");
  if (!Array.isArray(user?.content)) return undefined;
  const textPart = user.content
    .map(asRecord)
    .find((entry) => entry?.type === "input_text" && typeof entry.text === "string");
  return textPart && typeof textPart.text === "string"
    ? { payload: record, text: textPart.text, textPart }
    : undefined;
}

function fitCompactionPayload(payload: unknown): unknown {
  const compaction = compactionText(payload);
  if (!compaction) return payload;
  let best: unknown = payload;
  let lower = 0;
  let upper = compaction.text.length;
  while (lower <= upper) {
    const retainedCharacters = Math.floor((lower + upper) / 2);
    const headCharacters = Math.ceil(retainedCharacters / 2);
    const tailCharacters = Math.floor(retainedCharacters / 2);
    const candidate = structuredClone(compaction.payload);
    const candidateCompaction = compactionText(candidate);
    if (!candidateCompaction) return payload;
    candidateCompaction.textPart.text = compaction.text.slice(0, headCharacters)
      + COMPACTION_OMISSION_MARKER
      + compaction.text.slice(compaction.text.length - tailCharacters);
    if (Buffer.byteLength(JSON.stringify(candidate), "utf8") <= OPENAI_GATEWAY_PAYLOAD_LIMIT_BYTES) {
      best = candidate;
      lower = retainedCharacters + 1;
    } else {
      upper = retainedCharacters - 1;
    }
  }
  return best;
}

function boundedOpenAIResponsesStream(
  model: Model<Api>,
  context: Context,
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
        let requestPayload = replacement ?? payload;
        let requestBytes = Buffer.byteLength(JSON.stringify(requestPayload), "utf8");
        if (requestBytes > OPENAI_GATEWAY_PAYLOAD_LIMIT_BYTES) {
          requestPayload = fitCompactionPayload(requestPayload);
          requestBytes = Buffer.byteLength(JSON.stringify(requestPayload), "utf8");
        }
        if (requestBytes > OPENAI_GATEWAY_PAYLOAD_LIMIT_BYTES) {
          // Pi recognizes this provider-style signal and performs its bounded
          // compact-and-retry path before the 256 KiB gateway limit is reached.
          throw new Error("request_too_large: direct OpenAI context requires compaction");
        }
        return requestPayload;
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
    ...(api === "openai-responses"
      ? { streamSimple: boundedOpenAIResponsesStream }
      : {}),
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
        contextWindow: api === "openai-responses" ? 48_000 : 200_000,
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
