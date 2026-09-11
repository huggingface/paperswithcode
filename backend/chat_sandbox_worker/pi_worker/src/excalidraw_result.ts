import {
  INVALID_EXCALIDRAW_ELEMENTS,
  serializeExcalidrawElements,
} from "./mcp_app_registry.js";

const ACK = "Diagram displayed in the chat. Continue with a concise textual explanation.";

export function createViewResult(elements: unknown): {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
  structuredContent?: { checkpointId: string };
} {
  if (serializeExcalidrawElements(elements) === undefined) {
    return {
      content: [{ type: "text", text: INVALID_EXCALIDRAW_ELEMENTS }],
      isError: true,
    };
  }
  return {
    content: [{ type: "text", text: ACK }],
    structuredContent: { checkpointId: "local" },
  };
}
