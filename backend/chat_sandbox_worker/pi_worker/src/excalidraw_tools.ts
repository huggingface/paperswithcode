import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import Type from "typebox";

import { createViewResult } from "./excalidraw_result.js";
import {
  EXCALIDRAW_ENDPOINT,
  MAX_EXCALIDRAW_ELEMENTS_BYTES,
} from "./mcp_app_registry.js";

const MAX_READ_ME_RESPONSE_BYTES = 128 * 1024;
const READ_ME_TIMEOUT_MS = 8_000;

type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;
type ReadMeLoader = (signal?: AbortSignal) => Promise<string>;

async function boundedResponseText(response: Response): Promise<string> {
  if (!response.ok || !response.body) {
    throw new Error("Excalidraw read_me request failed");
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_READ_ME_RESPONSE_BYTES) {
      await reader.cancel();
      throw new Error("Excalidraw read_me response is too large");
    }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(body);
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new Error("Excalidraw read_me response is invalid");
  }
}

function responsePayloads(body: string, contentType: string): unknown[] {
  if (contentType.toLowerCase().includes("application/json")) {
    return [parseJson(body)];
  }
  const normalized = body.replace(/\r\n?/gu, "\n");
  return normalized.split("\n\n").flatMap((event) => {
    const data = event
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart());
    return data.length ? [parseJson(data.join("\n"))] : [];
  });
}

function parseReadMeResponse(body: string, contentType: string): string {
  const matches = responsePayloads(body, contentType).filter((payload) => (
    payload !== null
    && typeof payload === "object"
    && !Array.isArray(payload)
    && (payload as Record<string, unknown>).jsonrpc === "2.0"
    && (payload as Record<string, unknown>).id === 1
  ));
  if (matches.length !== 1) {
    throw new Error("Excalidraw read_me response is invalid");
  }
  const payload = matches[0];
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Excalidraw read_me response is invalid");
  }
  const result = (payload as Record<string, unknown>).result;
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("Excalidraw read_me response is invalid");
  }
  const content = (result as Record<string, unknown>).content;
  if (!Array.isArray(content) || content.length < 1 || content.length > 8) {
    throw new Error("Excalidraw read_me response is invalid");
  }
  const texts = content.map((item) => {
    if (
      !item
      || typeof item !== "object"
      || Array.isArray(item)
      || (item as Record<string, unknown>).type !== "text"
      || typeof (item as Record<string, unknown>).text !== "string"
    ) {
      throw new Error("Excalidraw read_me response is invalid");
    }
    return (item as Record<string, unknown>).text as string;
  });
  const text = texts.join("\n").trim();
  if (!text || Buffer.byteLength(text) > MAX_READ_ME_RESPONSE_BYTES) {
    throw new Error("Excalidraw read_me response is invalid");
  }
  return text;
}

export async function loadExcalidrawReadMe(
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<string> {
  const timeout = AbortSignal.timeout(READ_ME_TIMEOUT_MS);
  const response = await fetcher(EXCALIDRAW_ENDPOINT, {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name: "read_me", arguments: {} },
    }),
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  return parseReadMeResponse(
    await boundedResponseText(response),
    response.headers.get("content-type") ?? "",
  );
}

export function createNativeExcalidrawExtension(
  loadReadMe: ReadMeLoader = (signal) => loadExcalidrawReadMe(fetch, signal),
): ExtensionFactory {
  return (pi) => {
    pi.registerTool({
      name: "read_me",
      label: "Read Excalidraw guide",
      description:
        "Read the Excalidraw element-format guide before creating an interactive diagram.",
      parameters: Type.Object({}),
      async execute(_id, _params, signal) {
        return {
          content: [{ type: "text" as const, text: await loadReadMe(signal) }],
          details: {},
        };
      },
    });
    pi.registerTool({
      name: "create_view",
      label: "Create Excalidraw view",
      description:
        "Create an interactive diagram in the chat from a JSON array of Excalidraw elements. Invalid elements JSON is an error; fix the JSON and call create_view again.",
      parameters: Type.Object({
        elements: Type.Union([
          Type.String({ maxLength: MAX_EXCALIDRAW_ELEMENTS_BYTES }),
          Type.Array(Type.Unknown()),
        ]),
      }),
      async execute(_id, params) {
        return { ...createViewResult(params.elements), details: {} };
      },
    });
  };
}
