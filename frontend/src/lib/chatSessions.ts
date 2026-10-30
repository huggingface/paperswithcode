import { chatApi } from "@/lib/api/chat";
import type {
  ChatBlock,
  ChatModelChoice,
  ChatModelProvider,
  ChatSession,
  ChatSessionDetail,
  ChatShareDetail,
} from "@/lib/api/chat.types";
import { DEFAULT_REASONING_EFFORT, type ChatMessage, type PaperSelectionDraft } from "@/lib/chat";
import { restoredChatErrorMessage } from "@/lib/chatErrors";

export type {
  ChatModelChoice,
  ChatModelProvider,
  ChatSession,
  ChatSessionDetail,
  ChatShareDetail,
  ChatShareSummary,
  LatexPaperArtifactDescriptor,
  LatexPaperHistoryPage,
  LatexPaperVersionDescriptor,
} from "@/lib/api/chat.types";

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

/** Kept for the feed's homepage launcher, which creates sessions at the default effort. */
export function createSession(selectedModel?: string): Promise<ChatSession> {
  return chatApi.createSession(selectedModel, DEFAULT_REASONING_EFFORT);
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
      error: stoppedEarly ? undefined : restoredChatErrorMessage(message.error_code),
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
