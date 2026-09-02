import { McpServer } from "@modelcontextprotocol/server";
import { serveStdio } from "@modelcontextprotocol/server/stdio";
import { pathToFileURL } from "node:url";
import * as z from "zod/v4";

import {
  MAX_EXCALIDRAW_ELEMENTS_BYTES,
} from "./mcp_app_registry.js";
import { createViewResult } from "./excalidraw_result.js";

export { createViewResult } from "./excalidraw_result.js";

export function createExcalidrawViewServer(): McpServer {
  const server = new McpServer({ name: "excalidraw_view", version: "1.0.0" });
  server.registerTool(
    "create_view",
    {
      title: "Create Excalidraw view",
      description:
        "Create an interactive diagram in the chat from a JSON array of Excalidraw elements. Invalid elements JSON is an error; fix the JSON and call create_view again.",
      inputSchema: z.object({
        elements: z.union([z.string().max(MAX_EXCALIDRAW_ELEMENTS_BYTES), z.array(z.unknown())]),
      }),
    },
    async ({ elements }) => createViewResult(elements),
  );
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const handle = serveStdio(createExcalidrawViewServer, {
    legacy: "serve",
    onerror: (error) => console.error(`Excalidraw view MCP server failed: ${error.message}`),
  });
  for (const signal of ["SIGINT", "SIGTERM"] as const) {
    process.on(signal, () => void handle.close().finally(() => process.exit(0)));
  }
}
