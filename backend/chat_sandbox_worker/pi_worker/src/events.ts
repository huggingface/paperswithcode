import { serializeExcalidrawElements } from "./mcp_app_registry.js";
import { parsePwcPaperCommand, type PaperReceiptOperation } from "./paper_command.js";

export type PwCEvent = Record<string, unknown> & { type: string };

type UnknownRecord = Record<string, unknown>;
const ARTIFACT_PREFIX = "@@PWC_ARTIFACT@@";
const PAPER_PREFIX = "@@PWC_PAPER@@";
const MAX_TOOL_ARGUMENT_BYTES = 64 * 1024;

function isPaperOperation(value: unknown): value is "create" | "begin-edit" | "draft" | "repair" {
  return value === "create" || value === "begin-edit" || value === "draft" || value === "repair";
}

function record(value: unknown): UnknownRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {};
}

function textContent(value: unknown): string {
  if (typeof value === "string") return value;
  if (!Array.isArray(value)) return JSON.stringify(value ?? null);
  return value
    .map((item) => {
      const part = record(item);
      return part.type === "text" && typeof part.text === "string" ? part.text : "";
    })
    .join("");
}

function publicToolName(value: unknown): string {
  const name = String(value ?? "");
  if (name === "bash") return "Bash";
  if (name === "read") return "Read";
  return name;
}

function excalidrawElements(value: unknown): string | undefined {
  return serializeExcalidrawElements(record(value).elements);
}

function artifactEvents(content: string): PwCEvent[] {
  const line = content.split(/\r?\n/u).find((item) => item.startsWith(ARTIFACT_PREFIX));
  if (!line || Buffer.byteLength(line) > 16_384) return [];
  try {
    const ready = record(JSON.parse(line.slice(ARTIFACT_PREFIX.length)));
    const required = ["publication_id", "artifact_id", "version_id", "identifier", "version", "kind", "title", "preview_mime", "source_language", "gate_status", "total_bytes"];
    if (Object.keys(ready).length !== required.length || required.some((key) => !(key in ready))) return [];
    return [
      { type: "artifact_start", publication_id: ready.publication_id, identifier: ready.identifier, kind: ready.kind, title: ready.title },
      { type: "artifact_ready", ...ready },
    ];
  } catch {
    return [];
  }
}

function paperEvents(content: string): PwCEvent[] {
  const line = content.split(/\r?\n/u).find((item) => item.startsWith(PAPER_PREFIX));
  if (!line || Buffer.byteLength(line) > 16_384) return [];
  try {
    const value = record(JSON.parse(line.slice(PAPER_PREFIX.length)));
    if (!isPaperOperation(value.operation)) return [];
    if (typeof value.activated !== "boolean") return [];
    const descriptor = record(value.paper);
    if (typeof descriptor.artifact_id !== "string" || typeof descriptor.title !== "string") return [];
    return [{ type: "paper_artifact", operation: value.operation, activated: value.activated, descriptor }];
  } catch {
    return [];
  }
}

export function reasoningIsVisible(value: string | undefined): boolean {
  return value === "true";
}

export class PiEventAdapter {
  private reasoningOpen = false;
  private answerStarted = false;
  private terminalFailure = false;
  private readonly toolIds = new Set<string>();
  private readonly resultIds = new Set<string>();
  private readonly toolStartedAt = new Map<string, number>();
  private readonly toolNames = new Map<string, string>();
  private readonly contentTools = new Map<number, { id: string; publicIndex: number }>();
  private nextPublicContentIndex = 0;
  private readonly providerToolIds = new Map<string, string>();
  private readonly argumentBytes = new Map<string, number>();
  private readonly paperCommandIds = new Map<string, PaperReceiptOperation>();

  constructor(
    private readonly showReasoning: boolean,
    private readonly onSemantic?: (kind: "reasoning" | "tool" | "answer") => void,
    private readonly now: () => number = () => performance.now(),
  ) {}

  get failed(): boolean {
    return this.terminalFailure;
  }

  private closeReasoning(): PwCEvent[] {
    if (!this.reasoningOpen) return [];
    this.reasoningOpen = false;
    return this.showReasoning ? [{ type: "reasoning_end" }] : [];
  }

  private streamedTool(update: UnknownRecord): {
    contentIndex: number;
    id: string;
    name: string;
    args: UnknownRecord;
  } | undefined {
    const contentIndex = Number(update.contentIndex);
    if (!Number.isInteger(contentIndex) || contentIndex < 0) return undefined;
    const partial = record(update.partial);
    const content = Array.isArray(partial.content) ? partial.content : [];
    const block = record(content[contentIndex]);
    const existing = this.contentTools.get(contentIndex);
    const providerId = typeof block.id === "string" ? block.id : "";
    const id = existing?.id || providerId || `content:${contentIndex}`;
    const publicIndex = existing?.publicIndex ?? this.nextPublicContentIndex++;
    const name = publicToolName(block.name);
    if (providerId) this.providerToolIds.set(providerId, id);
    this.contentTools.set(contentIndex, { id, publicIndex });
    return { contentIndex: publicIndex, id, name, args: record(block.arguments) };
  }

  private startStreamedTool(tool: ReturnType<PiEventAdapter["streamedTool"]>): PwCEvent[] {
    if (!tool || !tool.name || tool.name === "create_view" || this.toolIds.has(tool.id)) return [];
    this.toolIds.add(tool.id);
    this.toolNames.set(tool.id, tool.name);
    this.onSemantic?.("tool");
    return [
      ...this.closeReasoning(),
      {
        type: "tool_call_start",
        id: tool.id,
        name: tool.name,
        content_index: tool.contentIndex,
      },
    ];
  }

  feed(rawEvent: unknown): PwCEvent[] {
    const event = record(rawEvent);
    const type = event.type;
    if (type === "message_update") {
      const update = record(event.assistantMessageEvent);
      if (update.type === "thinking_delta") {
        this.onSemantic?.("reasoning");
        if (!this.showReasoning) return [];
        const output: PwCEvent[] = [];
        if (!this.reasoningOpen) {
          this.reasoningOpen = true;
          output.push({ type: "reasoning_start" });
        }
        if (typeof update.delta === "string" && update.delta) {
          output.push({ type: "reasoning_delta", text: update.delta });
        }
        return output;
      }
      if (update.type === "text_delta" && typeof update.delta === "string") {
        const output = this.closeReasoning();
        if (update.delta && (this.answerStarted || update.delta.trim())) {
          this.answerStarted = true;
          this.onSemantic?.("answer");
          output.push({ type: "answer_delta", text: update.delta });
        }
        return output;
      }
      if (update.type === "toolcall_start") {
        return this.startStreamedTool(this.streamedTool(update));
      }
      if (update.type === "toolcall_delta") {
        const tool = this.streamedTool(update);
        if (!tool || tool.name === "create_view") return [];
        const output = this.startStreamedTool(tool);
        if (!this.toolIds.has(tool.id) || typeof update.delta !== "string" || !update.delta) return output;
        const bytes = Buffer.byteLength(update.delta);
        const total = (this.argumentBytes.get(tool.id) ?? 0) + bytes;
        if (total > MAX_TOOL_ARGUMENT_BYTES) throw new Error("Streamed tool arguments are too large");
        this.argumentBytes.set(tool.id, total);
        output.push({
          type: "tool_call_arguments_delta",
          id: tool.id,
          name: tool.name,
          delta: update.delta,
          partial_args: tool.args,
        });
        return output;
      }
      if (update.type === "toolcall_end") {
        const contentIndex = Number(update.contentIndex);
        const final = record(update.toolCall);
        const providerId = typeof final.id === "string" ? final.id : "";
        const existing = this.contentTools.get(contentIndex);
        const id = existing?.id || providerId || `content:${contentIndex}`;
        const publicIndex = existing?.publicIndex ?? this.nextPublicContentIndex++;
        if (providerId) this.providerToolIds.set(providerId, id);
        const tool = {
          contentIndex: publicIndex,
          id,
          name: publicToolName(final.name),
          args: record(final.arguments),
        };
        if (tool.name === "create_view") return [];
        const output = this.startStreamedTool(tool);
        if (!this.toolIds.has(id)) return output;
        output.push({ type: "tool_call_arguments_done", id, name: tool.name, args: tool.args });
        return output;
      }
      return [];
    }
    if (type === "tool_execution_start") {
      const providerId = typeof event.toolCallId === "string" ? event.toolCallId : "";
      const id = this.providerToolIds.get(providerId) || providerId;
      if (!id) return [];
      const args = record(event.args);
      const name = String(event.toolName ?? "");
      const paperCommand = name === "bash" && typeof args.command === "string"
        ? parsePwcPaperCommand(args.command)
        : undefined;
      if (paperCommand?.receiptOperation) this.paperCommandIds.set(id, paperCommand.receiptOperation);
      if (name === "create_view") {
        if (this.toolIds.has(id)) return [];
        const elements = excalidrawElements(args);
        if (!elements) return [];
        this.toolIds.add(id);
        this.toolNames.set(id, name);
        this.toolStartedAt.set(id, this.now());
        this.onSemantic?.("tool");
        return [
          ...this.closeReasoning(),
          {
            type: "app_start",
            id,
            instance_id: id,
            provider: "excalidraw",
            server: "excalidraw",
            tool: "create_view",
            resource_uri: "ui://excalidraw/mcp-app.html",
            input: { elements },
          },
        ];
      }
      const output: PwCEvent[] = [];
      if (!this.toolIds.has(id)) {
        this.toolIds.add(id);
        this.toolNames.set(id, name);
        this.onSemantic?.("tool");
        output.push(
          ...this.closeReasoning(),
          { type: "tool_call_start", id, name: publicToolName(name), content_index: -1 },
          { type: "tool_call_arguments_done", id, name: publicToolName(name), args },
        );
      }
      this.toolStartedAt.set(id, this.now());
      return output;
    }
    if (type === "tool_execution_end") {
      const providerId = typeof event.toolCallId === "string" ? event.toolCallId : "";
      const id = this.providerToolIds.get(providerId) || providerId;
      if (!this.toolIds.has(id) || this.resultIds.has(id)) return [];
      this.resultIds.add(id);
      const receiptOperation = this.paperCommandIds.get(id);
      this.paperCommandIds.delete(id);
      const startedAt = this.toolStartedAt.get(id);
      this.toolStartedAt.delete(id);
      const toolName = this.toolNames.get(id);
      this.toolNames.delete(id);
      const result = record(event.result);
      const content = textContent(result.content ?? event.result);
      if (toolName === "create_view") {
        const checkpoint = record(result.structuredContent).checkpointId;
        return [{
          type: "app_result",
          id,
          status: event.isError ? "error" : "ready",
          took_ms: startedAt === undefined ? 0 : Math.max(0, Math.round(this.now() - startedAt)),
          result: {
            content: [{ type: "text", text: content.slice(0, 8_192), truncated: Buffer.byteLength(content) > 8_192 }],
            structuredContent: typeof checkpoint === "string" && checkpoint.length <= 512 ? { checkpointId: checkpoint } : {},
            isError: event.isError === true,
          },
        }];
      }
      const publicContent = content.slice(0, 8_192);
      const publicContentTruncated = publicContent.length < content.length;
      return [
        {
          type: "tool_result",
          id,
          status: event.isError ? "error" : "success",
          took_ms: startedAt === undefined ? 0 : Math.max(0, Math.round(this.now() - startedAt)),
          content: [{ type: "text", text: publicContent, truncated: publicContentTruncated }],
          metadata: { output_truncated: publicContentTruncated },
        },
        ...artifactEvents(content),
        ...(receiptOperation && !event.isError
          ? paperEvents(content).filter((paperEvent) => paperEvent.operation === receiptOperation)
          : []),
      ];
    }
    if (type === "message_end") {
      const message = record(event.message);
      if (message.role !== "assistant") return [];
      // Content indexes are scoped to one provider response. Keeping this map
      // across tool rounds aliases a later call to an earlier call that used
      // the same index, which can suppress its start, arguments, and result.
      this.contentTools.clear();
      if (message.stopReason === "error" || typeof message.errorMessage === "string") {
        this.terminalFailure = true;
        return [
          ...this.closeReasoning(),
          {
            type: "error",
            code: "provider_error",
            message: "The model provider is unavailable.",
          },
        ];
      }
      const usage = record(message.usage);
      return [
        {
          type: "usage",
          usage,
          model_usage: {},
          total_cost_usd: record(usage.cost).total ?? 0,
          provider_requests: 1,
        },
      ];
    }
    if (type === "agent_settled") return this.closeReasoning();
    return [];
  }
}
