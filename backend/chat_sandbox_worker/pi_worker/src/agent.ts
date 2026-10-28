import { randomUUID } from "node:crypto";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import {
  createAgentSession,
  DefaultResourceLoader,
  type AgentSession,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { fitPaperContext } from "./paper_context_budget.js";
import { CompactionController, compactionReserveTokens } from "./compaction.js";
import { PiEventAdapter, reasoningIsVisible, type PwCEvent } from "./events.js";
import { createNativeExcalidrawExtension } from "./excalidraw_tools.js";
import { createWebMcpExtension, WEB_SEARCH_TOOL } from "./mcp.js";
import {
  EXCALIDRAW_MODEL_TOOLS,
  assessExcalidrawReadiness,
  excalidrawEnabled,
  isExcalidrawModelTool,
  toolNameDigest,
  type McpReadinessSnapshot,
} from "./mcp_app_registry.js";
import { PolicyController, pwcExtension } from "./policy.js";
import { createProvider, thinkingLevel, type ProviderProtocol } from "./provider.js";
import { type GatewayContext } from "./provider.js";
import { createRemoteToolsExtension, type RemoteToolBridge } from "./external_tools.js";
import { PWC_MCP_TOOL_NAMES, createPwcMcpToolsExtension, pwcMcpEnabled } from "./pwc_mcp_tools.js";
import { CATALOG_TOOL_NAMES, createCatalogToolsExtension } from "./catalog_tools.js";
import { loadPromptAsset, renderPrompt, taskCatalogForPrompt } from "./prompt.js";
import { recoverIncompleteResponse, type RecoverySummary } from "./recovery.js";
import { createOrBind, restoreFile, TranscriptMirror } from "./transcript.js";
import { shouldResetSession } from "./session.js";

export interface RunTurn {
  request_id: string;
  chat_session_id: string;
  prompt: string;
  model: string;
  provider_protocol?: ProviderProtocol;
  resume: string | null;
  agent_session_id?: string;
  web_search_enabled: boolean;
  reader_mode: boolean;
  poster_mode: boolean;
  paper_artifacts_enabled: boolean;
  paper_descriptor?: Record<string, unknown>;
  reasoning_effort: "low" | "medium" | "high" | "max";
  hf_username: string;
}

type TurnFailurePhase =
  | "initialize"
  | "session_bind_restore"
  | "prompt_render"
  | "transcript_initialize"
  | "agent_session"
  | "model_prompt"
  | "transcript_finalize";

export function turnFailureDiagnostic(phase: TurnFailurePhase, error: unknown): string {
  const errorClass = error instanceof TypeError
    ? "TypeError"
    : error instanceof RangeError
      ? "RangeError"
      : error instanceof SyntaxError
        ? "SyntaxError"
        : "Error";
  return `External Pi turn failed phase=${phase} error=${errorClass}\n`;
}

export function externalPiStateEnvironment(stateRoot: string): Record<string, string> {
  return {
    PI_CODING_AGENT_DIR: path.join(stateRoot, "agent"),
    PI_CODING_AGENT_SESSION_DIR: path.join(stateRoot, "sessions"),
  };
}

const externalStateRoot = process.env.PWC_EXTERNAL_PI_STATE_ROOT;
const harnessWorkspace = externalStateRoot
  ? path.join(externalStateRoot, "workspace")
  : "/workspace";
const sessionDirectory = externalStateRoot
  ? path.join(externalStateRoot, "sessions")
  : "/home/pwc-chat/.pi-sessions";
const agentDirectory = externalStateRoot
  ? path.join(externalStateRoot, "agent")
  : "/home/pwc-chat/.pi-disabled";

const RECOVERY_TIMEOUT_MESSAGE = "Recovery exceeded 60 seconds. Your conversation and completed research are saved. Retry, shorten the request, or start a new conversation.";

export class PiWorker {
  private session: AgentSession | undefined;
  private manager: SessionManager | undefined;
  private mirror: TranscriptMirror | undefined;
  private mirroredEntryCount = 0;
  private boundChatSession: string | undefined;
  private boundAgentSession: string | undefined;
  private activeRequest: string | undefined;
  private cancelled = false;
  private readonly compaction = new CompactionController((event) => {
    if (this.activeRequest) this.emit(this.activeRequest, event);
  });
  private initialization: Promise<void> | undefined;
  private promptAsset: string | undefined;
  private prewarmedProvider: Awaited<ReturnType<typeof createProvider>> | undefined;
  private prewarmedModel: string | undefined;
  private prewarmedProtocol: ProviderProtocol | undefined;
  private policyExtension: ReturnType<typeof pwcExtension> | undefined;
  private webMcpExtension: ReturnType<typeof createWebMcpExtension> | undefined;
  private noWebMcpExtension: ReturnType<typeof createWebMcpExtension> | undefined;
  private mcpReadiness: McpReadinessSnapshot | undefined;
  private activeProfile: string | undefined;
  private sessionTaskCatalog: string | undefined;
  private failurePhase: TurnFailurePhase = "initialize";
  private readonly policy: PolicyController;
  private readonly excalidrawAvailable: boolean;

  constructor(
    private readonly emit: (requestId: string, event: PwCEvent) => void,
    private readonly gateway?: GatewayContext,
    private readonly remoteTools?: RemoteToolBridge,
    features: { excalidrawAvailable?: boolean } = {},
  ) {
    this.excalidrawAvailable = features.excalidrawAvailable ?? excalidrawEnabled();
    this.policy = new PolicyController({
      maximumCalls: Number(process.env.PWC_CHAT_MAX_TOOL_CALLS ?? 12),
      maximumRounds: Number(process.env.PWC_CHAT_MAX_TURNS ?? 8) - 2,
      maximumDirectSearches: Number(process.env.PWC_CHAT_MAX_DIRECT_SEARCH_CALLS ?? 4),
      maximumWebSearches: Number(process.env.PWC_CHAT_MAX_WEB_SEARCH_CALLS ?? 3),
      maximumResultBytes: Number(process.env.PWC_CHAT_TOOL_RESULT_MAX_BYTES ?? 24576),
      maximumTurnOutputBytes: Number(process.env.PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES ?? 98304),
      bashTimeoutSeconds: Number(process.env.PWC_CHAT_BASH_TIMEOUT_SECONDS ?? 30),
      excalidrawEnabled: this.excalidrawAvailable,
      catalogEnabled: Boolean(this.gateway && this.remoteTools),
      posterlyMaximumCalls: Number(process.env.PWC_CHAT_POSTERLY_MAX_TOOL_CALLS ?? 40),
      posterlyMaximumRounds: Number(process.env.PWC_CHAT_POSTERLY_MAX_TOOL_ROUNDS ?? 20),
      posterlyMaximumResultBytes: Number(process.env.PWC_CHAT_POSTERLY_TOOL_RESULT_MAX_BYTES ?? 196608),
      posterlyMaximumTurnOutputBytes: Number(process.env.PWC_CHAT_POSTERLY_TURN_TOOL_OUTPUT_MAX_BYTES ?? 1048576),
      posterlyTimeoutSeconds: Number(process.env.PWC_CHAT_POSTERLY_TIMEOUT_SECONDS ?? 600),
      paperMaximumCalls: Number(process.env.PWC_CHAT_LATEX_PAPER_MAX_TOOL_CALLS ?? 30),
      paperMaximumRounds: Number(process.env.PWC_CHAT_LATEX_PAPER_MAX_TOOL_ROUNDS ?? 12),
      paperMaximumDirectSearches: Number(process.env.PWC_CHAT_LATEX_PAPER_MAX_DIRECT_SEARCH_CALLS ?? 8),
      paperTimeoutSeconds: Number(process.env.PWC_CHAT_LATEX_PAPER_TIMEOUT_SECONDS ?? 600),
    });
  }

  initialize(): Promise<void> {
    this.initialization ??= this.initializeImmutableProfile();
    return this.initialization;
  }

  private async initializeImmutableProfile(): Promise<void> {
    if (externalStateRoot) {
      Object.assign(process.env, externalPiStateEnvironment(externalStateRoot));
    }
    await Promise.all([
      mkdir(harnessWorkspace, { recursive: true, mode: 0o700 }),
      mkdir(sessionDirectory, { recursive: true, mode: 0o700 }),
      mkdir(agentDirectory, { recursive: true, mode: 0o700 }),
    ]);
    this.promptAsset = await loadPromptAsset();
    this.policyExtension = pwcExtension(this.policy);
    this.webMcpExtension = createWebMcpExtension(
      process.execPath,
      [new URL("./exa_mcp_server.js", import.meta.url).pathname],
      {
        ...(this.gateway ? { exaEnv: {
          PWC_EXTERNAL_GATEWAY_URL: this.gateway.url,
          PWC_EXTERNAL_GATEWAY_CAPABILITY: this.gateway.capability,
          PWC_EXTERNAL_GATEWAY_SESSION: this.gateway.sessionId,
          PWC_EXTERNAL_GATEWAY_TURN: this.gateway.turnId,
          PWC_EXTERNAL_GATEWAY_TURN_WORKER_ID: this.gateway.turnClaim.workerId,
          PWC_EXTERNAL_GATEWAY_TURN_WORKER_GENERATION: String(
            this.gateway.turnClaim.workerGeneration,
          ),
          PWC_EXTERNAL_GATEWAY_TURN_LEASE_GENERATION: String(
            this.gateway.turnClaim.leaseGeneration,
          ),
        } } : {}),
      },
    );
    this.noWebMcpExtension = createWebMcpExtension(
      process.execPath,
      [new URL("./exa_mcp_server.js", import.meta.url).pathname],
      {
        exa: false,
      },
    );
    if (process.env.PWC_CHAT_PI_PREWARM_ENABLED !== "true") return;
    const model = process.env.PWC_CHAT_PI_PREWARM_MODEL;
    if (!model) throw new Error("Pi prewarm model is missing");
    const protocol = process.env.PWC_CHAT_PI_PREWARM_PROTOCOL === "openai-responses"
      ? "openai-responses"
      : "anthropic-messages";
    this.prewarmedProvider = await createProvider(model, protocol, this.gateway);
    this.prewarmedModel = model;
    this.prewarmedProtocol = protocol;
  }

  async cancel(requestId: string): Promise<void> {
    if (requestId !== this.activeRequest) return;
    this.cancelled = true;
    this.session?.abortCompaction();
    await this.session?.abort();
  }

  async dispose(): Promise<void> {
    await this.disposeSession();
  }

  private async disposeSession(reason: "new" | "resume" = "new"): Promise<void> {
    const session = this.session;
    if (!session) return;
    this.session = undefined;
    this.activeProfile = undefined;
    this.sessionTaskCatalog = undefined;
    try {
      await session.extensionRunner.emit({ type: "session_shutdown", reason });
    } finally {
      session.dispose();
    }
  }

  private async sessionManager(run: RunTurn): Promise<{ manager: SessionManager; initialCount: number; created: boolean }> {
    if (this.boundChatSession && this.boundChatSession !== run.chat_session_id) {
      throw new Error("Pi worker session ownership mismatch");
    }
    if (shouldResetSession(this.boundAgentSession, run.resume)) {
      // An edit atomically activates a prepared native fork for the same chat.
      // A retry of an interrupted initial prompt may instead deliberately
      // activate a blank transcript (run.resume is null). Drop only the
      // harness-local state in both cases; the worker stays pinned to the chat.
      await this.disposeSession("resume");
      this.manager = undefined;
      this.mirror = undefined;
      this.mirroredEntryCount = 0;
      this.boundAgentSession = undefined;
    }
    if (this.manager) {
      return { manager: this.manager, initialCount: this.manager.getEntries().length + 1, created: false };
    }
    if (run.resume) {
      const restored = await restoreFile(run.resume, sessionDirectory, this.gateway);
      const manager = SessionManager.open(restored.file, sessionDirectory, harnessWorkspace);
      if (manager.getSessionId() !== run.resume || manager.getLeafId() !== restored.snapshot.current_leaf_id) {
        throw new Error("Pi restored session identity mismatch");
      }
      this.manager = manager;
      this.boundAgentSession = run.resume;
      return { manager, initialCount: restored.snapshot.entry_count, created: false };
    }
    if (run.agent_session_id) {
      const bound = await createOrBind(run.agent_session_id, this.gateway);
      if (bound.agent_session_id !== run.agent_session_id) {
        throw new Error("Pi prebound session identity mismatch");
      }
      if (bound.entry_count > 0) {
        const restored = await restoreFile(run.agent_session_id, sessionDirectory, this.gateway);
        const manager = SessionManager.open(restored.file, sessionDirectory, harnessWorkspace);
        if (
          manager.getSessionId() !== run.agent_session_id
          || manager.getLeafId() !== restored.snapshot.current_leaf_id
        ) {
          throw new Error("Pi prebound retry restore identity mismatch");
        }
        this.manager = manager;
        this.boundAgentSession = run.agent_session_id;
        return { manager, initialCount: restored.snapshot.entry_count, created: false };
      }
      const manager = SessionManager.create(
        harnessWorkspace,
        sessionDirectory,
        { id: run.agent_session_id },
      );
      this.manager = manager;
      this.boundAgentSession = run.agent_session_id;
      return { manager, initialCount: 0, created: true };
    }
    const id = randomUUID();
    const manager = SessionManager.create(harnessWorkspace, sessionDirectory, { id });
    const bound = await createOrBind(id, this.gateway);
    if (bound.agent_session_id !== id) {
      if (bound.entry_count === 0) {
        const reboundManager = SessionManager.create(
          harnessWorkspace,
          sessionDirectory,
          { id: bound.agent_session_id },
        );
        this.manager = reboundManager;
        this.boundAgentSession = bound.agent_session_id;
        return { manager: reboundManager, initialCount: 0, created: true };
      }
      const restored = await restoreFile(bound.agent_session_id, sessionDirectory, this.gateway);
      const restoredManager = SessionManager.open(
        restored.file,
        sessionDirectory,
        harnessWorkspace,
      );
      if (
        restoredManager.getSessionId() !== bound.agent_session_id ||
        restoredManager.getLeafId() !== restored.snapshot.current_leaf_id
      ) {
        throw new Error("Pi retry restore identity mismatch");
      }
      this.manager = restoredManager;
      this.boundAgentSession = bound.agent_session_id;
      return {
        manager: restoredManager,
        initialCount: restored.snapshot.entry_count,
        created: false,
      };
    }
    if (bound.entry_count !== 0) {
      throw new Error("Pi new session bind contract mismatch");
    }
    this.manager = manager;
    this.boundAgentSession = id;
    return { manager, initialCount: 0, created: true };
  }

  private async open(run: RunTurn): Promise<void> {
    await this.initialize();
    const phaseStarted = performance.now();
    this.failurePhase = "session_bind_restore";
    const statePromise = this.sessionManager(run);
    const protocol = run.provider_protocol ?? "anthropic-messages";
    const coldProviderPromise = !this.session
      && !(this.prewarmedModel === run.model
        && this.prewarmedProtocol === protocol
        && this.prewarmedProvider)
      ? createProvider(run.model, protocol, this.gateway).then(
        (provider) => ({ provider }),
        (error: unknown) => ({ error }),
      )
      : undefined;
    let state: Awaited<typeof statePromise>;
    try {
      state = await statePromise;
    } catch (error) {
      await coldProviderPromise;
      throw error;
    }
    this.emit(run.request_id, { type: "_latency", phase: "session_bind_restore", elapsed_ms: Math.round(performance.now() - phaseStarted) });
    this.failurePhase = "prompt_render";
    // A new session takes the last live task index (refreshed in the
    // background at most every five minutes, never blocking) or keeps the
    // deploy-time snapshot when none is cached yet. An open session keeps the
    // index it started with: policy re-applies the rendered prompt every turn,
    // and a mid-conversation change would invalidate the prompt cache.
    const taskCatalog = this.session ? this.sessionTaskCatalog : taskCatalogForPrompt();
    const prompt = await renderPrompt({
      model: run.model,
      hfUsername: run.hf_username,
      webSearchEnabled: run.web_search_enabled,
      readerMode: run.reader_mode,
      posterlyEnabled: run.poster_mode,
      paperArtifactsEnabled: run.paper_artifacts_enabled,
      catalogToolsEnabled: Boolean(this.gateway && this.remoteTools),
      ...(run.paper_descriptor === undefined ? {} : { paperDescriptor: run.paper_descriptor }),
      ...(taskCatalog === undefined ? {} : { taskCatalog }),
      source: this.promptAsset!,
    });
    const coldProviderResult = await coldProviderPromise;
    if (coldProviderResult && "error" in coldProviderResult) {
      throw coldProviderResult.error;
    }
    const coldProvider = coldProviderResult?.provider;
    this.policy.reset(run.web_search_enabled, prompt, run.poster_mode);
    const profile = JSON.stringify({
      model: run.model,
      providerProtocol: run.provider_protocol ?? "anthropic-messages",
      reasoningEffort: run.reasoning_effort,
      webSearchEnabled: run.web_search_enabled,
      readerMode: run.reader_mode,
      posterMode: run.poster_mode,
      paperArtifactsEnabled: run.paper_artifacts_enabled,
      hfUsername: run.hf_username,
      promptProfile: "compact-pi-v1",
      catalogToolsEnabled: Boolean(this.gateway && this.remoteTools),
    });
    let mirrorInitialization: Promise<void> = Promise.resolve();
    if (!this.mirror) {
      this.failurePhase = "transcript_initialize";
      // The remote count includes the session header; getEntries() contains
      // only tree entries.
      this.mirroredEntryCount = Math.max(0, state.initialCount - 1);
      this.mirror = new TranscriptMirror(
        state.manager.getSessionId(),
        state.initialCount,
        state.manager.getLeafId(),
        this.gateway,
      );
      if (state.created) {
        const header = state.manager.getHeader();
        if (!header) throw new Error("Pi native session header is missing");
        this.mirror.append(header as unknown as Record<string, unknown>);
        if (!run.agent_session_id) mirrorInitialization = this.mirror.flush();
      }
    }
    if (this.session && this.activeProfile === profile) {
      this.emit(run.request_id, { type: "_latency", phase: "agent_session_ready", elapsed_ms: Math.round(performance.now() - phaseStarted) });
      return;
    }
    await this.disposeSession();
    this.failurePhase = "agent_session";
    const provider = this.prewarmedModel === run.model
      && this.prewarmedProtocol === protocol
      && this.prewarmedProvider
      ? this.prewarmedProvider
      : coldProvider ?? await createProvider(run.model, protocol, this.gateway);
    const settings = SettingsManager.inMemory({
      compaction: { enabled: true, reserveTokens: compactionReserveTokens(provider.model.contextWindow) },
      retry: { enabled: false },
    });
    const loader = new DefaultResourceLoader({
      cwd: harnessWorkspace,
      agentDir: agentDirectory,
      settingsManager: settings,
      noExtensions: true,
      noSkills: true,
      noPromptTemplates: true,
      noThemes: true,
      noContextFiles: true,
      systemPrompt: prompt,
      extensionFactories: [
        { name: "pwc-compaction", factory: this.compaction.extension(provider), hidden: true },
        { name: "pwc-policy", factory: this.policyExtension!, hidden: true },
        {
          name: "pwc-mcp",
          factory: run.web_search_enabled
            ? this.webMcpExtension!
            : this.noWebMcpExtension!,
          hidden: true,
        },
        ...(this.excalidrawAvailable ? [{
          name: "pwc-excalidraw",
          factory: createNativeExcalidrawExtension(),
          hidden: true,
        }] : []),
        ...(this.remoteTools ? [{
          name: "pwc-remote-tools",
          factory: createRemoteToolsExtension(this.remoteTools),
          hidden: true,
        }] : []),
        ...(this.gateway && this.remoteTools ? [{
          name: "pwc-catalog",
          factory: pwcMcpEnabled() ? createPwcMcpToolsExtension(this.gateway) : createCatalogToolsExtension(this.gateway),
          hidden: true,
        }] : []),
      ],
    });
    await Promise.all([loader.reload(), mirrorInitialization]);
    this.emit(run.request_id, { type: "_latency", phase: "resource_loading", elapsed_ms: Math.round(performance.now() - phaseStarted) });
    const created = await createAgentSession({
      cwd: harnessWorkspace,
      agentDir: agentDirectory,
      modelRuntime: provider.runtime,
      model: provider.model,
      thinkingLevel: thinkingLevel(run.reasoning_effort),
      // MCP research turns have no sandbox tools; poster and paper authoring keep them.
      tools: [
        ...(this.gateway && this.remoteTools && pwcMcpEnabled() && !run.poster_mode && run.paper_artifacts_enabled !== true ? [] : ["read", "bash"]),
        ...(run.web_search_enabled ? [WEB_SEARCH_TOOL] : []),
        ...(this.gateway && this.remoteTools ? (pwcMcpEnabled() ? PWC_MCP_TOOL_NAMES : CATALOG_TOOL_NAMES) : []),
        ...(this.excalidrawAvailable ? [...EXCALIDRAW_MODEL_TOOLS] : []),
      ],
      excludeTools: ["edit", "write", "grep", "find", "ls", "ask_question"],
      resourceLoader: loader,
      settingsManager: settings,
      sessionManager: state.manager,
    });
    await created.session.bindExtensions({ mode: "print" });
    created.extensionsResult.runtime.refreshTools();
    if (this.gateway && this.remoteTools && pwcMcpEnabled()) {
      // Catalog research depends on these tools alone; never continue without them.
      const active = new Set(created.session.getActiveToolNames());
      const missing = PWC_MCP_TOOL_NAMES.filter((name) => !active.has(name));
      if (missing.length) {
        const reasons = created.extensionsResult.errors.map((item) => item.error).join("; ");
        throw new Error(`PwC MCP tools are unavailable (${missing.length} of ${PWC_MCP_TOOL_NAMES.length} missing)${reasons ? `: ${reasons}` : ""}`);
      }
    }
    this.mcpReadiness = assessExcalidrawReadiness({
      enabled: this.excalidrawAvailable,
      connectionMode: "lazy",
      activeTools: created.session.getActiveToolNames(),
      createViewDefinition: created.session.getToolDefinition("create_view") as
        { parameters?: unknown } | undefined,
    });
    if (this.excalidrawAvailable && !this.mcpReadiness.ready) {
      const withoutExcalidraw = () =>
        created.session.getActiveToolNames().filter((name) => !isExcalidrawModelTool(name));
      created.session.setActiveToolsByName(withoutExcalidraw());
      created.extensionsResult.runtime.refreshTools();
      created.session.setActiveToolsByName(withoutExcalidraw());
      const registered = [...created.session.getActiveToolNames()].sort();
      this.mcpReadiness = {
        ...this.mcpReadiness,
        registered_tool_names: registered,
        registered_tool_digest: toolNameDigest(registered),
      };
    }
    this.emit(run.request_id, { type: "_mcp_readiness", ...this.mcpReadiness });
    this.session = created.session;
    this.activeProfile = profile;
    this.sessionTaskCatalog = taskCatalog;
    this.emit(run.request_id, { type: "_latency", phase: "agent_session_ready", elapsed_ms: Math.round(performance.now() - phaseStarted) });
  }

  private mirrorNativeEntries(): void {
    if (!this.manager || !this.mirror) throw new Error("Pi transcript mirror is unavailable");
    const entries = this.manager.getEntries();
    if (entries.length < this.mirroredEntryCount) {
      throw new Error("Pi native transcript moved backwards");
    }
    for (const entry of entries.slice(this.mirroredEntryCount)) {
      this.mirror.append(entry as unknown as Record<string, unknown>);
    }
    this.mirroredEntryCount = entries.length;
  }

  async run(run: RunTurn): Promise<void> {
    if (this.activeRequest) throw new Error("Pi worker already has an active turn");
    this.activeRequest = run.request_id;
    this.cancelled = false;
    const turnTimeoutSeconds = run.poster_mode
      ? Number(process.env.PWC_CHAT_POSTERLY_TIMEOUT_SECONDS ?? 600)
      : run.paper_artifacts_enabled
        ? Number(process.env.PWC_CHAT_LATEX_PAPER_TIMEOUT_SECONDS ?? 600)
        : Number(process.env.PWC_CHAT_AGENT_TIMEOUT_SECONDS ?? 180);
    this.compaction.reset(turnTimeoutSeconds * 1000, () => {
      this.session?.abortCompaction();
      void this.session?.abort();
    }, run.prompt);
    this.boundChatSession ??= run.chat_session_id;
    this.failurePhase = "initialize";
    try {
      await this.initialize();
      this.emit(run.request_id, { type: "worker_ready" });
      await this.open(run);
      if (this.cancelled) {
        this.emit(run.request_id, { type: "worker_done", status: "stopped" });
        return;
      }
      if (!this.session || !this.manager || !this.mirror || !this.boundAgentSession) {
        throw new Error("Pi worker failed to initialize");
      }
      if (this.session.model) {
        run = { ...run, prompt: fitPaperContext(run.prompt, {
          model: this.session.model,
          systemPrompt: this.session.systemPrompt,
          tools: this.session.agent.state.tools,
        }) };
        this.compaction.setProtectedRequest(run.prompt);
      }
      const adapter = new PiEventAdapter(
        reasoningIsVisible(process.env.PWC_CHAT_SHOW_REASONING),
        (kind) => {
          if (kind === "answer") this.policy.observeAnswer();
        },
      );
      let subscribeFailed = false;
      let pendingAdapterError: PwCEvent | undefined;
      const unsubscribe = this.session.subscribe((event) => {
        if (subscribeFailed || this.cancelled) return;
        try {
          if (event.type === "message_end" && event.message.role === "assistant") {
            if (event.message.stopReason === "length") this.policy.observeIncomplete();
          }
          for (const adapted of adapter.feed(event)) {
            // A terminal event must be the final semantic frame before
            // worker_done. Hold provider/adapter failures until transcript
            // finalization has selected the single authoritative terminal.
            if (adapted.type === "error") {
              if (!pendingAdapterError || pendingAdapterError.code === "context_too_large") pendingAdapterError = adapted;
            } else this.emit(run.request_id, adapted);
          }
        } catch {
          subscribeFailed = true;
          pendingAdapterError = {
            type: "error",
            code: "provider_error",
            message: "The research run failed.",
          };
        }
      });
      this.emit(run.request_id, { type: "_sdk_session", session_id: this.boundAgentSession });
      this.emit(run.request_id, { type: "workspace_ready" });
      this.failurePhase = "model_prompt";
      let mirrorFailed = false;
      let reasoningLowered = false;
      let recovery: RecoverySummary = {
        reason: null,
        attempts: 0,
        outcome: "not_needed",
      };
      try {
        await this.session.prompt(run.prompt, { expandPromptTemplates: false, source: "interactive" });
        recovery = await recoverIncompleteResponse(this.policy, {
          prompt: async (value) => {
            this.compaction.startRecovery();
            // The provider guard and SDK compact only when context is actually
            // crowded. A length-limited answer may have no safe summary boundary.
            await this.session!.prompt(value, {
              expandPromptTemplates: false,
              source: "extension",
            });
          },
          disableTools: () => this.session!.setActiveToolsByName([]),
          lowerReasoning: () => {
            if (run.reasoning_effort !== "max") return;
            reasoningLowered = true;
            this.session!.setThinkingLevel("high");
          },
          canContinue: () => !adapter.failed && !this.compaction.failed && !this.cancelled && !subscribeFailed,
        });
      } finally {
        // The session is reused by later turns on this worker; do not leak the downgrade.
        if (reasoningLowered) this.session?.setThinkingLevel(thinkingLevel(run.reasoning_effort));
        this.compaction.finish();
        unsubscribe();
        this.failurePhase = "transcript_finalize";
        try {
          this.mirrorNativeEntries();
          await this.mirror.flush();
        } catch {
          mirrorFailed = true;
        }
      }
      if (this.cancelled) {
        this.emit(run.request_id, { type: "worker_done", status: "stopped" });
        return;
      }
      if (mirrorFailed) {
        this.emit(run.request_id, { type: "_mirror_error" });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
        return;
      }
      if (this.compaction.timedOut) {
        pendingAdapterError = this.recoveryTimeoutError();
      }
      if (this.compaction.failed && !this.compaction.timedOut && (!pendingAdapterError || pendingAdapterError.code === "context_too_large")) {
        pendingAdapterError = {
          type: "error", code: "context_too_large",
          message: "Earlier context could not be summarized. Your conversation is saved. Retry, or shorten recent messages if it remains too large.",
        };
      }
      if (adapter.failed || subscribeFailed || this.compaction.failed) {
        this.emit(run.request_id, this.executionTelemetry(recovery, true));
        this.emit(run.request_id, pendingAdapterError ?? {
          type: "error",
          code: "provider_error",
          message: "The research run failed.",
        });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
        return;
      }
      if (this.policy.needsFinalAnswer()) {
        this.emit(run.request_id, this.executionTelemetry(recovery));
        this.emit(run.request_id, {
          type: "error",
          code: "provider_error",
          message: "The model provider returned an incomplete response.",
        });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
        return;
      }
      this.emit(run.request_id, this.executionTelemetry(recovery));
      this.emit(run.request_id, { type: "done", finish_reason: "success", followups: [] });
      this.emit(run.request_id, { type: "worker_done", status: "complete" });
    } catch (error) {
      if (this.cancelled) {
        this.emit(run.request_id, { type: "worker_done", status: "stopped" });
      } else {
        process.stderr.write(turnFailureDiagnostic(this.failurePhase, error));
        this.emit(run.request_id, this.compaction.timedOut ? this.recoveryTimeoutError() : {
          type: "error",
          code: "gateway_unavailable",
          message: "The research run failed.",
        });
        this.emit(run.request_id, { type: "worker_done", status: "complete" });
      }
    } finally {
      this.compaction.finish();
      this.activeRequest = undefined;
    }
  }

  private recoveryTimeoutError(): PwCEvent {
    // Incomplete-answer retries share the recovery deadline but need not
    // compact anything. Do not diagnose their timeout as oversized context.
    return {
      type: "error",
      code: this.compaction.attempted ? "context_too_large" : "provider_error",
      message: this.compaction.attempted
        ? RECOVERY_TIMEOUT_MESSAGE
        : "The model did not finish its response within the recovery time limit. Your conversation and completed research are saved. Please retry.",
    };
  }

  private executionTelemetry(recovery: RecoverySummary, failed = false): PwCEvent {
    return {
      type: "_execution_telemetry",
      tool_calls: this.policy.calls,
      tool_rounds_executed: this.policy.rounds,
      direct_search_calls: this.policy.searches,
      web_search_calls: this.policy.webSearches,
      compaction_enabled: true,
      compaction_recovery_outcome: this.compaction.attempted
        ? (failed || this.compaction.failed ? "failed" : "success") : "not_needed",
      execution_limit_reached: this.policy.toolingClosed,
      recovery_reason: recovery.reason,
      recovery_attempts: recovery.attempts,
      recovery_outcome: recovery.outcome,
    };
  }
}
