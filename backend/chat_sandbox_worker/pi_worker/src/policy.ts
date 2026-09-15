import path from "node:path";
import type { ExtensionFactory } from "@earendil-works/pi-coding-agent";
import {
  EXCALIDRAW_ELEMENTS_TOO_LARGE,
  INVALID_EXCALIDRAW_ELEMENTS,
  excalidrawElementsTooLarge,
  serializeExcalidrawElements,
} from "./mcp_app_registry.js";
import { parsePwcPaperCommand, type PaperReceiptOperation } from "./paper_command.js";

const ANSWER_NOW =
  "Execution limit reached. Do not call more tools. Answer now from the evidence already gathered.";
const SEARCH = /(?:^|[;&|()\n]\s*)(?:pwc|s2)\s+search(?:\s|$)/iu;
const ANSI = /(?:\u001b\][^\u0007]*(?:\u0007|\u001b\\)|\u001b\[[0-?]*[ -/]*[@-~])/gu;
const INLINED_CLI_GUIDES = new Set([
  "/opt/pwc/PWC_CLI_SKILL.md",
  "/opt/pwc/HF_CLI_SKILL.md",
  "/opt/pwc/S2_CLI_SKILL.md",
]);
const READABLE_GUIDES = new Set([
  "/opt/posterly/SKILL.md",
  "/opt/pwc/POSTERLY_PUBLISH.md",
  "/opt/pwc/PAPER_AUTHORING.md",
]);
const PAPER_PREFIX = "@@PWC_PAPER@@";

function isPaperOperation(value: unknown): boolean {
  return value === "create" || value === "begin-edit" || value === "draft" || value === "repair";
}

function isPaperActivation(value: string, expectedOperation: PaperReceiptOperation): boolean {
  const line = value.split(/\r?\n/u).find((item) => item.startsWith(PAPER_PREFIX));
  if (!line || Buffer.byteLength(line) > 16_384) return false;
  try {
    const receipt = JSON.parse(line.slice(PAPER_PREFIX.length)) as Record<string, unknown>;
    return receipt.operation === expectedOperation
      && isPaperOperation(receipt.operation)
      && receipt.activated === true
      && receipt.paper !== null
      && typeof receipt.paper === "object";
  } catch {
    return false;
  }
}

function inside(candidate: string, root: string): boolean {
  const relative = path.relative(root, path.resolve(candidate));
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function clean(value: string, maximum: number): { text: string; truncated: boolean } {
  const normalized = value
    .replace(ANSI, "")
    .split("")
    .filter((character) => character === "\n" || character === "\t" || character.charCodeAt(0) >= 32)
    .join("");
  const encoded = Buffer.from(normalized);
  if (encoded.length <= maximum) return { text: normalized, truncated: false };
  const hint = "\n[output truncated; narrow, filter, or paginate and try again]\n";
  if (maximum <= Buffer.byteLength(hint)) {
    return { text: Buffer.from(hint).subarray(0, maximum).toString("utf8"), truncated: true };
  }
  const prefix = encoded.subarray(0, Math.max(0, maximum - Buffer.byteLength(hint)));
  return { text: `${prefix.toString("utf8").replace(/\uFFFD$/u, "")}${hint}`, truncated: true };
}

export interface PolicyOptions {
  maximumCalls: number;
  maximumRounds: number;
  maximumDirectSearches: number;
  maximumWebSearches: number;
  maximumResultBytes: number;
  maximumTurnOutputBytes: number;
  bashTimeoutSeconds: number;
  excalidrawEnabled?: boolean;
  catalogEnabled?: boolean;
  posterlyMaximumCalls?: number;
  posterlyMaximumRounds?: number;
  posterlyMaximumResultBytes?: number;
  posterlyMaximumTurnOutputBytes?: number;
  posterlyTimeoutSeconds?: number;
  paperMaximumCalls?: number;
  paperMaximumRounds?: number;
  paperMaximumDirectSearches?: number;
  paperTimeoutSeconds?: number;
}

export class PolicyController {
  webSearchEnabled = false;
  calls = 0;
  rounds = 0;
  searches = 0;
  webSearches = 0;
  readMeCalls = 0;
  createViewCalls = 0;
  outputBytes = 0;
  toolingClosed = false;
  answerProduced = false;
  answerAfterClose = false;
  systemPrompt = "";
  posterMode = false;
  paperActivated = false;
  private active = new Set<string>();
  private paperCommandIds = new Map<string, PaperReceiptOperation>();

  constructor(readonly options: PolicyOptions) {}

  reset(webSearchEnabled: boolean, systemPrompt = this.systemPrompt, posterMode = false): void {
    this.webSearchEnabled = webSearchEnabled;
    this.systemPrompt = systemPrompt;
    this.posterMode = posterMode;
    this.paperActivated = false;
    this.calls = 0;
    this.rounds = 0;
    this.searches = 0;
    this.webSearches = 0;
    this.readMeCalls = 0;
    this.createViewCalls = 0;
    this.outputBytes = 0;
    this.toolingClosed = false;
    this.answerProduced = false;
    this.answerAfterClose = false;
    this.active.clear();
    this.paperCommandIds.clear();
  }

  observeAnswer(): void {
    this.answerProduced = true;
    if (this.toolingClosed) this.answerAfterClose = true;
  }

  observeIncomplete(): void {
    this.answerProduced = false;
    this.answerAfterClose = false;
  }

  needsFinalAnswer(): boolean {
    return this.toolingClosed ? !this.answerAfterClose : !this.answerProduced;
  }

  private deny(id: string, reason: string): string {
    this.active.delete(id);
    return reason;
  }

  authorize(id: string, name: string, input: Record<string, unknown>): string | undefined {
    if (!this.active.size) this.rounds += 1;
    this.active.add(id);
    const maximumRounds = this.posterMode ? (this.options.posterlyMaximumRounds ?? 20) : this.paperActivated ? (this.options.paperMaximumRounds ?? 12) : this.options.maximumRounds;
    const maximumCalls = this.posterMode ? (this.options.posterlyMaximumCalls ?? 40) : this.paperActivated ? (this.options.paperMaximumCalls ?? 30) : this.options.maximumCalls;
    if (this.toolingClosed || this.rounds > maximumRounds || this.calls >= maximumCalls) {
      this.toolingClosed = true;
      return this.deny(id, ANSWER_NOW);
    }
    const catalogTool = new Set(["pwc_search", "pwc_paper_info", "pwc_paper_list"]).has(name);
    if (catalogTool && !this.options.catalogEnabled) {
      return this.deny(id, "Catalog tools are not available.");
    }
    if (!catalogTool && !new Set(["bash", "read", "search_web", "read_me", "create_view"]).has(name)) {
      return this.deny(id, "That tool is not available.");
    }
    if ((name === "read_me" || name === "create_view") && !this.options.excalidrawEnabled) {
      return this.deny(id, "Diagram tools are not available.");
    }
    if (name === "read_me") {
      if (this.readMeCalls >= 1) return this.deny(id, "read_me may be called once per turn.");
      this.readMeCalls += 1;
    }
    if (name === "create_view") {
      if (serializeExcalidrawElements(input.elements) === undefined) {
        return this.deny(
          id,
          excalidrawElementsTooLarge(input.elements)
            ? EXCALIDRAW_ELEMENTS_TOO_LARGE
            : INVALID_EXCALIDRAW_ELEMENTS,
        );
      }
      if (this.createViewCalls >= 2) return this.deny(id, "At most two diagrams may be created per turn.");
      this.createViewCalls += 1;
    }
    if (name === "read") {
      const requested = typeof input.path === "string" ? input.path : "";
      const resolved = path.resolve("/workspace", requested);
      if (INLINED_CLI_GUIDES.has(resolved)) {
        return this.deny(
          id,
          "The pwc, s2, and restricted hf CLI skills are already included verbatim in your system prompt. Read that text instead and run the CLI directly.",
        );
      }
      if (!inside(resolved, "/workspace") && !READABLE_GUIDES.has(resolved)) {
        return this.deny(id, "Read may only access /workspace or the approved CLI guides.");
      }
    }
    if (name === "bash") {
      const command = typeof input.command === "string" ? input.command : "";
      if (!command) return this.deny(id, "Invalid Bash command.");
      input.timeout = Math.min(
        this.posterMode ? (this.options.posterlyTimeoutSeconds ?? 600) : this.paperActivated ? (this.options.paperTimeoutSeconds ?? 600) : this.options.bashTimeoutSeconds,
        typeof input.timeout === "number" ? input.timeout : (this.posterMode ? (this.options.posterlyTimeoutSeconds ?? 600) : this.paperActivated ? (this.options.paperTimeoutSeconds ?? 600) : this.options.bashTimeoutSeconds),
      );
      const paperCommand = parsePwcPaperCommand(command);
      if (paperCommand) {
        input.timeout = Math.max(Number(input.timeout), 130);
        if (paperCommand.receiptOperation) {
          this.paperCommandIds.set(id, paperCommand.receiptOperation);
        }
      }
    }
    if (name === "pwc_search" || (name === "bash" && SEARCH.test(String(input.command)))) {
      const maximumSearches = this.paperActivated ? (this.options.paperMaximumDirectSearches ?? 8) : this.options.maximumDirectSearches;
      if (this.searches >= maximumSearches) {
        this.toolingClosed = true;
        return this.deny(id, ANSWER_NOW);
      }
      this.searches += 1;
    }
    if (name === "search_web") {
      const query = input.query;
      if (!this.webSearchEnabled || typeof query !== "string" || !query.trim() || query.length > 500) {
        return this.deny(id, "Web search is not available for this request.");
      }
      if (this.webSearches >= this.options.maximumWebSearches) {
        this.toolingClosed = true;
        return this.deny(id, ANSWER_NOW);
      }
      this.webSearches += 1;
    }
    this.calls += 1;
    return undefined;
  }

  finish(
    id: string,
    content: unknown,
    isError = false,
  ): { content: Array<{ type: "text"; text: string }>; isError?: boolean } {
    this.active.delete(id);
    const raw = Array.isArray(content)
      ? content
          .map((part) =>
            part && typeof part === "object" && "text" in part ? String((part as { text: unknown }).text) : "",
          )
          .join("")
      : String(content ?? "");
    const maximumTurnOutputBytes = this.posterMode
      ? (this.options.posterlyMaximumTurnOutputBytes ?? 1024 * 1024)
      : this.options.maximumTurnOutputBytes;
    const maximumResultBytes = this.posterMode
      ? (this.options.posterlyMaximumResultBytes ?? 192 * 1024)
      : this.options.maximumResultBytes;
    const remaining = Math.max(0, maximumTurnOutputBytes - this.outputBytes);
    const bounded = clean(raw, Math.min(remaining, maximumResultBytes));
    this.outputBytes += Buffer.byteLength(bounded.text);
    const receiptOperation = this.paperCommandIds.get(id);
    this.paperCommandIds.delete(id);
    if (!isError && receiptOperation && isPaperActivation(bounded.text, receiptOperation)) {
      this.paperActivated = true;
    }
    return {
      content: [{ type: "text", text: bounded.text }],
      ...(bounded.truncated ? { isError: false } : {}),
    };
  }
}

export function pwcExtension(policy: PolicyController): ExtensionFactory {
  return (pi) => {
    pi.on("before_agent_start", () => ({ systemPrompt: policy.systemPrompt }));
    pi.on("tool_call", (event) => {
      const reason = policy.authorize(event.toolCallId, event.toolName, event.input as Record<string, unknown>);
      return reason ? { block: true, reason } : undefined;
    });
    pi.on("tool_result", (event) => policy.finish(event.toolCallId, event.content, event.isError));
  };
}

export { ANSWER_NOW };
