import { randomUUID } from "node:crypto";
import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import {
  createBashTool,
  createReadTool,
  type BashOperations,
  type ReadOperations,
} from "@earendil-works/pi-coding-agent";

const MAX_REMOTE_READ_BYTES = 1024 * 1024;

export interface RemoteToolRequest {
  type: "tool_request";
  operation_id: string;
  tool_call_id: string;
  operation: "exec" | "read";
  command?: string;
  timeout_ms?: number;
  path?: string;
  offset?: number;
  max_bytes?: number;
}

export interface RemoteToolResult {
  type: "tool_result";
  operation_id: string;
  ok: boolean;
  outputs?: { stream: "stdout" | "stderr"; data: string }[];
  terminal?: { status: string; exit_code: number | null; error: string | null };
  data_base64?: string;
  eof?: boolean;
  error?: string;
}

export interface RemoteToolChannel {
  request(frame: RemoteToolRequest): Promise<RemoteToolResult>;
}

export class RemoteToolBridge {
  constructor(private readonly channel: RemoteToolChannel) {}

  async exec(
    toolCallId: string,
    command: string,
    timeoutMs: number,
    onData: (data: Buffer) => void,
  ): Promise<{ exitCode: number | null }> {
    const result = await this.exchange({
      type: "tool_request",
      operation_id: randomUUID(),
      tool_call_id: toolCallId,
      operation: "exec",
      command,
      timeout_ms: timeoutMs,
    });
    for (const output of result.outputs ?? []) onData(Buffer.from(output.data, "utf8"));
    if (!result.ok) {
      throw new Error(`remote execution failed:${result.error ?? result.terminal?.error ?? "unknown"}`);
    }
    if (!result.terminal) throw new Error("invalid remote execution result");
    if (result.terminal.status === "failed") {
      throw new Error(`remote execution failed:${result.terminal.error ?? result.error ?? "unknown"}`);
    }
    return { exitCode: result.terminal.exit_code };
  }

  async read(toolCallId: string, path: string): Promise<Buffer> {
    const workspacePrefix = "/workspace/";
    const remotePath = path.startsWith(workspacePrefix)
      ? path.slice(workspacePrefix.length)
      : path;
    const result = await this.exchange({
      type: "tool_request",
      operation_id: randomUUID(),
      tool_call_id: toolCallId,
      operation: "read",
      path: remotePath,
      offset: 0,
      max_bytes: MAX_REMOTE_READ_BYTES,
    });
    if (!result.ok || typeof result.data_base64 !== "string") {
      throw new Error(`remote read failed:${result.error ?? "unknown"}`);
    }
    return Buffer.from(result.data_base64, "base64");
  }

  private async exchange(frame: RemoteToolRequest): Promise<RemoteToolResult> {
    const result = await this.channel.request(frame);
    if (result.type !== "tool_result" || result.operation_id !== frame.operation_id) {
      throw new Error("uncorrelated remote tool result");
    }
    return result;
  }
}

export function createRemoteToolsExtension(bridge: RemoteToolBridge): ExtensionFactory {
  return (pi) => {
    const localBash = createBashTool("/workspace");
    pi.registerTool({
      ...localBash,
      async execute(id, params, signal, onUpdate) {
        const operations: BashOperations = {
          exec: async (command, _cwd, options) => {
            if (signal?.aborted || options.signal?.aborted) throw new Error("aborted");
            const timeoutMs = Math.max(1, Math.round((options.timeout ?? 30) * 1000));
            return bridge.exec(id, command, timeoutMs, options.onData);
          },
        };
        return createBashTool("/workspace", { operations }).execute(
          id, params, signal, onUpdate,
        );
      },
    });

    const localRead = createReadTool("/workspace");
    pi.registerTool({
      ...localRead,
      async execute(id, params, signal, onUpdate) {
        let prefetched: { path: string; data: Buffer } | undefined;
        const operations: ReadOperations = {
          readFile: (path) => {
            if (prefetched?.path === path) {
              const data = prefetched.data;
              prefetched = undefined;
              return Promise.resolve(data);
            }
            return bridge.read(id, path);
          },
          access: (path) => bridge.read(id, path).then((data) => {
            prefetched = { path, data };
          }),
          detectImageMimeType: async () => null,
        };
        return createReadTool("/workspace", { operations }).execute(
          id, params, signal, onUpdate,
        );
      },
    });
  };
}
