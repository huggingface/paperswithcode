import { chatApi } from "@/lib/api/chat";
import { ApiError } from "@/lib/apiTransport";
import { DEFAULT_REASONING_EFFORT, type ChatBlock, type ChatCitation, type ChatMessage, type PaperMentionDraft, type PaperSelectionDraft, type ReasoningEffort } from "@/lib/chat";

export interface ChatSession {
  id: string;
  title: string;
  selected_model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  is_busy: boolean;
  web_search_enabled: boolean;
  reasoning_effort?: ReasoningEffort;
  primary_paper?: {
    id: string;
    route_id: string;
    title: string;
    arxiv_id: string | null;
  } | null;
}

export interface ChatSessionDetail extends ChatSession {
  transcript_status: string;
  latex_paper?: LatexPaperArtifactDescriptor | null;
  messages: Array<{
    id: string;
    turn_id: string;
    sequence: number;
    role: "user" | "assistant";
    content: string;
    paper_mentions?: Array<Omit<PaperMentionDraft, "key"> & { occurrence_id: string }>;
    paper_selection?: {
      route_id: string;
      paper_version: string;
      page: number;
      text: string;
      text_sha256?: string;
      included_bytes?: number;
      page_verified?: boolean;
    } | null;
    viewer_context?: { page: number } | null;
    revision: number;
    status: string;
    display_blocks: ChatBlock[];
    citations: ChatCitation[];
    followups: string[];
    finish_reason?: string | null;
    error_code: string | null;
    reasoning_effort?: ReasoningEffort;
  }>;
}

export interface LatexPaperVersionDescriptor {
  version_id: string;
  version: number;
  source_digest: string;
  compile_status: "queued" | "compiling" | "succeeded" | "failed";
  created_at?: string | null;
  actor_type?: "ai" | "human" | "restore";
  parent_version_id?: string | null;
  preview_head_version_id?: string | null;
  compile_diagnostics?: Array<{
    severity: "error" | "warning";
    phase?: string | null;
    file?: string | null;
    line?: number | null;
    message: string;
  }>;
  repair_attempts_remaining?: number;
  repair_exhausted?: boolean;
  generation_provenance?: Record<string, unknown> | null;
  display_metadata: {
    summary?: string | null;
    unresolved_todo_count: number;
    warning_count: number;
  };
  provenance?: {
    action: "human_save" | "ai_draft" | "ai_repair" | "restore";
    model_identity?: string | null;
    change_summary?: string | null;
    changed_files: string[];
    reference_changes: string[];
    restored_from_version_id?: string | null;
  };
}

export interface LatexPaperHistoryPage {
  items: LatexPaperVersionDescriptor[];
  next_cursor?: string | null;
}

export interface LatexPaperArtifactDescriptor {
  artifact_id: string;
  title: string;
  source_head?: LatexPaperVersionDescriptor | null;
  preview_head?: LatexPaperVersionDescriptor | null;
  editing_enabled?: boolean;
}

export interface ChatShareSummary {
  share_id: string;
  public_path: string;
  created_at: string;
  updated_at: string;
}

interface PublicChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  paper_mentions?: Array<Omit<PaperMentionDraft, "key"> & { occurrence_id: string }>;
  paper_selection?: {
    route_id: string;
    paper_version: string;
    page: number;
    text: string;
    text_sha256?: string;
    included_bytes?: number;
    page_verified?: boolean;
  } | null;
  display_blocks: ChatBlock[];
  citations: ChatCitation[];
  model?: string | null;
  display_state: "complete" | "interrupted" | "failed";
  finish_reason: string | null;
  error: string | null;
}

export type ChatModelProvider = "huggingface" | "openrouter" | "openai";

export interface ChatShareDetail {
  share_id: string;
  created_at: string;
  updated_at: string;
  model: string | null;
  model_label: string | null;
  model_provider: ChatModelProvider | null;
  messages: PublicChatMessage[];
}

export interface ChatModelChoice {
  id: string;
  label: string;
  provider: ChatModelProvider;
  // Billed to the Papers With Code organization, so no user authorization.
  sponsored?: boolean;
  reasoning_efforts?: ReasoningEffort[];
}

// Persisted route ID; it now serves GPT-6 Luna.
export const DEFAULT_CHAT_MODEL = "gpt-5.6-luna@openai";
const DEEPSEEK_CHAT_MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731";
const LEGACY_OPENROUTER_LUNA_MODEL = "openai/gpt-5.6-luna";
// Billed to the organization. Known here so deep links, restored drafts, and
// existing sessions skip HF authorization before discovery loads; when it is
// switched off the backend moves those sessions to Luna, which needs none.
const SPONSORED_CHAT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash-1017";

export function providerForChatModel(
  models: ChatModelChoice[],
  selectedModel: string,
): ChatModelProvider {
  return models.find((model) => model.id === selectedModel)?.provider
    ?? (selectedModel === LEGACY_OPENROUTER_LUNA_MODEL
      ? "openrouter"
      : selectedModel === DEFAULT_CHAT_MODEL
        ? "openai"
        : "huggingface");
}

export function isSponsoredChatModel(
  models: ChatModelChoice[],
  selectedModel: string,
): boolean {
  const model = models.find((choice) => choice.id === selectedModel);
  return model ? model.sponsored === true : selectedModel === SPONSORED_CHAT_MODEL;
}

// Signed-out visitors cannot read discovery, so this list is what they see.
export const PRODUCTION_FALLBACK_CHAT_MODELS: ChatModelChoice[] = [
  {
    id: DEFAULT_CHAT_MODEL,
    label: "GPT-6 Luna",
    provider: "openai",
  },
  {
    id: SPONSORED_CHAT_MODEL,
    label: "DeepSeek V4.1 Flash",
    provider: "huggingface",
    sponsored: true,
  },
];
export const STAGING_FALLBACK_CHAT_MODELS: ChatModelChoice[] = [
  {
    id: DEEPSEEK_CHAT_MODEL,
    label: "DeepSeek V4 Flash",
    provider: "huggingface",
  },
  {
    id: "moonshotai/Kimi-K3",
    label: "Kimi K3",
    provider: "huggingface",
  },
  {
    id: "gpt-5.6-luna@openrouter",
    label: "GPT-5.6 Luna",
    provider: "openrouter",
  },
  {
    id: "gpt-5.6-luna@openai",
    label: "GPT-6 Luna (Direct)",
    provider: "openai",
  },
];
export class ChatRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

export async function listSessions(): Promise<ChatSession[]> {
  const sessions: ChatSession[] = [];
  let cursor: string | null = null;
  do {
    const page = await chatApi.listSessions(cursor);
    sessions.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && sessions.length < 100);
  return sessions;
}

export function createSession(
  selectedModel?: string,
  reasoningEffort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
): Promise<ChatSession> {
  return chatApi.createSession(selectedModel, reasoningEffort);
}

export function getSession(id: string): Promise<ChatSessionDetail> {
  return chatApi.getSession(id);
}

export function updateSession(
  id: string,
  patch: { title?: string; selected_model?: string; reasoning_effort?: ReasoningEffort },
): Promise<ChatSession> {
  return chatApi.updateSession(id, patch);
}

export function removeSession(id: string): Promise<void> {
  return chatApi.removeSession(id);
}

export function archiveOldChats(): Promise<{ archived_count: number }> {
  return chatApi.archiveOldChats();
}

export function archiveOldestChats(): Promise<{ archived_count: number }> {
  return chatApi.archiveOldestChats();
}

export function cancelSession(id: string): Promise<void> {
  return chatApi.cancelSession(id);
}

export function createOrRefreshShare(id: string): Promise<ChatShareSummary> {
  return chatApi.createOrRefreshShare(id);
}

export async function getSharedChat(id: string): Promise<ChatShareDetail> {
  try {
    return await chatApi.getSharedChat(id);
  } catch (error) {
    if (error instanceof ApiError) throw new ChatRequestError(error.message, error.status);
    throw error;
  }
}

export async function getChatModels(): Promise<{ items: ChatModelChoice[]; default_model: string }> {
  return chatApi.getModels();
}

// Older scope-blocked turns stored their refusal only in `content`.
function assistantBlocks(
  message: { content: string; display_blocks: ChatBlock[] },
  expandFailedTools: boolean,
): ChatBlock[] {
  if (message.display_blocks.length === 0 && message.content) {
    return [{ kind: "answer", text: message.content, done: true }];
  }
  return restoreBlocks(message.display_blocks, expandFailedTools);
}

function restoreBlocks(blocks: ChatBlock[], expandFailedTools: boolean): ChatBlock[] {
  const restored = blocks.map((block): ChatBlock => block.kind === "reasoning"
    ? { ...block, active: false, open: false }
    : block.kind === "tool"
      ? {
          ...block,
          status: block.status === "running" ? "error" as const : block.status,
          open: expandFailedTools
            && (block.status === "error" || block.status === "denied" || block.status === "running"),
        }
      : block.kind === "app"
        ? {
            ...block,
            schema_version: 1,
            result: block.result ?? { content: [], structuredContent: {}, isError: false },
            csp: block.csp ?? {},
            permissions: block.permissions ?? { clipboardWrite: true },
            height: block.height || 525,
            public_fork: Boolean(block.public_fork),
          }
        : block.kind === "artifact"
          ? { ...block }
        : { ...block, done: true as const });
  return restored.filter((block, index) => {
    const previous = restored[index - 1];
    return !(
      block.kind === "reasoning"
      && previous?.kind === "reasoning"
      && block.text === previous.text
    );
  });
}

function toPaperSelection(selection?: ChatSessionDetail["messages"][number]["paper_selection"]): PaperSelectionDraft | undefined {
  if (!selection?.text) return undefined;
  return {
    routeId: selection.route_id,
    paperVersion: selection.paper_version,
    page: selection.page,
    text: selection.text,
  };
}

export function toUiMessages(detail: ChatSessionDetail): ChatMessage[] {
  const failureMessage = (code: string | null): string => {
    if (code === "hf_inference_billing_exhausted") {
      return "Hugging Face could not bill this request. Your included credits may be exhausted; enable or review pay-as-you-go billing in Settings.";
    }
    if (code === "hf_inference_credential_expired") {
      return "Your Hugging Face Inference Providers authorization is missing or expired. Re-sign in with Hugging Face to continue.";
    }
    if (code === "provider_rate_limit") return "The selected model is temporarily rate-limited. Try again shortly.";
    if (code === "provider_timeout") return "The model provider timed out. Try again shortly.";
    if (code === "openrouter_monthly_budget_exhausted") return "The remaining shared Papers With Code OpenRouter allowance was not enough to continue this response.";
    if (code === "openrouter_staging_funding_disabled") return "Shared staging credits have ended because chat is now live on paperswithcode.co. Continue there with your included monthly allowance.";
    if (code === "openrouter_unavailable") return "OpenRouter is currently unavailable. However, you can still bring your own key in Settings.";
    if (code === "openrouter_byok_credential_invalid") return "Your OpenRouter API key is no longer valid. Reconnect it in Settings, then try again.";
    if (code === "openrouter_byok_billing_error") return "Your OpenRouter key is connected, but OpenRouter rejected billing for the account behind it. A key spending limit is not an account credit balance. Add credits or enable pay-as-you-go in OpenRouter, then try again.";
    if (code === "openrouter_byok_rate_limit") return "Your OpenRouter API key is temporarily rate-limited.";
    if (code === "openai_budget_exhausted") return "The Papers With Code direct OpenAI allowance is exhausted. Select another model or try again later.";
    if (code === "context_too_large") return "This conversation is too large for the selected model. Start a new chat or shorten the context.";
    if (["provider_error", "provider_unavailable"].includes(code ?? "")) return "The model provider failed before completing the response. You can edit and retry your question.";
    if (code === "persistence_error") return "The response could not be saved. You can edit and retry your question.";
    if (code === "transcript_mirror_error") return "The conversation could not be saved. Please try again in a new chat.";
    if (code === "external_worker_lost") return "The assistant worker lost contact before the response could be saved. You can edit and retry your question.";
    return "The response did not complete. You can edit and retry your question.";
  };
  const userStopped = (code: string | null): boolean => (
    code == null || ["cancelled", "interrupted", "stopped"].includes(code)
  );

  return detail.messages.flatMap((message): ChatMessage[] => {
    if (message.role === "assistant") {
      return [{
        id: message.id,
        role: "assistant",
        blocks: assistantBlocks(message, true),
        followups: message.followups,
        citations: message.citations,
        finishReason: message.finish_reason ?? undefined,
        streaming: false,
      }];
    }
    const userMessage: ChatMessage = {
      id: message.id,
      role: "user",
      text: message.content,
      paperMentions: (message.paper_mentions ?? []).map((mention) => ({
        ...mention,
        key: mention.occurrence_id,
      })),
      paperSelection: toPaperSelection(message.paper_selection),
      revision: message.revision,
      status: message.status,
      error: message.status === "complete" ? undefined : message.error_code || message.status,
    };
    if (!["error", "interrupted"].includes(message.status)) return [userMessage];
    const stoppedEarly = message.status === "interrupted" && userStopped(message.error_code);
    return [userMessage, {
      id: `${message.id}-${message.status === "interrupted" ? "interrupted" : "error"}`,
      role: "assistant",
      blocks: restoreBlocks(message.display_blocks, true),
      streaming: false,
      finishReason: stoppedEarly ? "stopped" : undefined,
      error: stoppedEarly ? undefined : failureMessage(message.error_code),
      errorCode: stoppedEarly ? undefined : message.error_code ?? undefined,
    }];
  });
}

export function publicShareToUiMessages(detail: ChatShareDetail): ChatMessage[] {
  return detail.messages.map((message): ChatMessage => message.role === "user"
    ? {
        id: message.id,
        role: "user",
        text: message.content,
        paperMentions: (message.paper_mentions ?? []).map((mention) => ({
          ...mention,
          key: mention.occurrence_id,
        })),
        paperSelection: toPaperSelection(message.paper_selection),
      }
    : {
        id: message.id,
        role: "assistant",
        blocks: assistantBlocks(message, false),
        citations: message.citations,
        finishReason: message.finish_reason ?? undefined,
        error: message.error ?? undefined,
        streaming: false,
      });
}

export interface ChatSessionGroup { label: string; items: ChatSession[] }

export function groupSessions(sessions: ChatSession[]): ChatSessionGroup[] {
  const now = Date.now();
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const groups: ChatSessionGroup[] = [
    { label: "Today", items: [] },
    { label: "Previous 7 Days", items: [] },
    { label: "Previous 30 Days", items: [] },
    { label: "Older", items: [] },
  ];
  for (const session of [...sessions].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))) {
    const timestamp = Date.parse(session.updated_at);
    const age = now - timestamp;
    if (timestamp >= startOfToday) groups[0].items.push(session);
    else if (age < 7 * 86_400_000) groups[1].items.push(session);
    else if (age < 30 * 86_400_000) groups[2].items.push(session);
    else groups[3].items.push(session);
  }
  return groups.filter((group) => group.items.length > 0);
}
